import json
import logging
import time

import requests
from openai import OpenAI

from app.config import settings
from app.graph.state import AgentState
from app.services.opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)


def _llm(model: str, prompt: str, content: str) -> str:
    client = OpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)
    t0 = time.monotonic()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )
    duration_ms = int((time.monotonic() - t0) * 1000)
    usage = response.usage
    logger.info(
        "llm_call model=%s duration_ms=%d prompt_tokens=%s completion_tokens=%s",
        model,
        duration_ms,
        usage.prompt_tokens if usage else "?",
        usage.completion_tokens if usage else "?",
    )
    return response.choices[0].message.content or "{}"


def ingestor_node(state: AgentState) -> AgentState:
    """Normalize raw input and extract structured threat data."""
    logger.info("ingestor_node: processing raw content")
    model = state["model_config"].get("triage_model", settings.triage_model)
    prompt = state["model_config"].get("triage_prompt", (
        "You are an OSINT analyst. Analyze the input text. "
        "If it describes a vulnerability, software update, or network attack — return a JSON object with: "
        "title, threat_type, cve_ids (array), severity (low|medium|high|critical), confidence (low|medium|high), "
        "affected_vendors (array), summary. "
        "If the content is irrelevant noise — return {\"ignore\": true}."
    ))
    try:
        result = json.loads(_llm(model, prompt, state["raw_content"]))
        if result.get("ignore"):
            return {**state, "ignore": True, "status": "ignored"}
        return {**state, "threat_profile": result, "ignore": False, "status": "triaged"}
    except Exception as exc:
        logger.error("ingestor_node error: %s", exc)
        return {**state, "error": str(exc), "status": "error"}


def analyst_node(state: AgentState) -> AgentState:
    """Deep analysis + deduplication via OpenSearch vector search."""
    logger.info("analyst_node: analyzing threat profile")
    model = state["model_config"].get("analyst_model", settings.analyst_model)
    prompt = state["model_config"].get("analyst_prompt", (
        "You are a senior CTI analyst. Given the threat profile, provide a deep analysis. "
        "Return JSON with: severity, confidence, attack_vectors (array), "
        "detection_strategies (array), mitigation_steps (array), needs_deep_research (bool)."
    ))
    try:
        analysis = json.loads(_llm(model, prompt, json.dumps(state["threat_profile"])))
        merged = {**state["threat_profile"], **analysis}

        # Try deduplication search
        try:
            os_client = OpenSearchClient()
            similar = os_client.search_similar_threats(state["threat_profile"].get("summary", ""), top_k=3)
            merged["similar_threats_found"] = len(similar)
        except Exception as os_err:
            logger.warning("OpenSearch dedup search failed: %s", os_err)

        return {**state, "threat_profile": merged, "status": "analyzed"}
    except Exception as exc:
        logger.error("analyst_node error: %s", exc)
        return {**state, "error": str(exc), "status": "error"}


def claw_bridge_node(state: AgentState) -> AgentState:
    """Delegate deep research to OpenClaw (if configured)."""
    logger.info("claw_bridge_node: dispatching to OpenClaw")
    try:
        payload = {
            "task_description": (
                f"Research threat: {state['threat_profile'].get('title', 'unknown')}. "
                f"CVEs: {state['threat_profile'].get('cve_ids', [])}. "
                f"Find: PoC exploits, detection signatures, vendor advisories, patches."
            ),
            "depth": "deep",
        }
        response = requests.post(
            f"{settings.openclaw_url}/api/v1/task",
            json=payload,
            timeout=120,
        )
        if response.ok:
            research_data = response.json()
            return {**state, "research_data": research_data, "status": "researched"}
    except Exception as exc:
        logger.warning("OpenClaw not reachable: %s", exc)
    return {**state, "research_data": None, "status": "analyzed"}


def infra_guard_node(state: AgentState) -> AgentState:
    """Correlate threat with asset inventory using local model."""
    logger.info("infra_guard_node: correlating with assets")
    model = state["model_config"].get("infra_model", settings.infra_model)
    prompt = state["model_config"].get("infra_prompt", (
        "You are an infrastructure security auditor. Given the threat and matched assets, "
        "determine exposure. Return JSON with: exposed_assets (array), overall_risk, remediation_priority."
    ))
    affected: list[dict] = []
    try:
        os_client = OpenSearchClient()
        vendors = state["threat_profile"].get("affected_vendors", [])
        for vendor in vendors[:5]:  # limit queries
            matches = os_client.search_assets(vendor=vendor)
            affected.extend(matches)
    except Exception as exc:
        logger.warning("Asset search failed: %s", exc)

    try:
        infra_input = {
            "threat_profile": state["threat_profile"],
            "matched_assets": affected,
        }
        infra_analysis = json.loads(_llm(model, prompt, json.dumps(infra_input)))
        merged_profile = {**state["threat_profile"], **infra_analysis}
        return {**state, "affected_assets": affected, "threat_profile": merged_profile, "status": "correlated"}
    except Exception as exc:
        logger.error("infra_guard_node error: %s", exc)
        return {**state, "affected_assets": affected, "status": "correlated", "error": str(exc)}


def publisher_node(state: AgentState) -> AgentState:
    """Generate Operations and Executive reports."""
    logger.info("publisher_node: generating reports")
    analyst_model = state["model_config"].get("analyst_model", settings.analyst_model)
    ops_prompt = state["model_config"].get("publisher_ops_prompt", (
        "You are a technical security writer. Create a detailed Operations Report in Markdown format. "
        "Include: threat summary, CVEs, affected systems, detection commands, patch status, references."
    ))
    exec_prompt = state["model_config"].get("publisher_exec_prompt", (
        "You are a CISO advisor. Create a concise Executive Summary (max 200 words). "
        "Include: risk level, business impact, recommended actions."
    ))
    full_context = json.dumps({
        "threat_profile": state["threat_profile"],
        "affected_assets": state["affected_assets"],
        "research_data": state.get("research_data"),
    })
    reports: dict[str, str] = {}
    try:
        # Ops report doesn't need JSON mode
        client = OpenAI(base_url=settings.litellm_base_url, api_key=settings.litellm_api_key)
        ops_resp = client.chat.completions.create(
            model=analyst_model,
            messages=[
                {"role": "system", "content": ops_prompt},
                {"role": "user", "content": full_context},
            ],
            temperature=0.2,
        )
        reports["ops"] = ops_resp.choices[0].message.content or ""

        exec_resp = client.chat.completions.create(
            model=analyst_model,
            messages=[
                {"role": "system", "content": exec_prompt},
                {"role": "user", "content": full_context},
            ],
            temperature=0.2,
        )
        reports["executive"] = exec_resp.choices[0].message.content or ""
    except Exception as exc:
        logger.error("publisher_node error: %s", exc)
        reports["error"] = str(exc)

    return {**state, "reports": reports, "status": "reported"}

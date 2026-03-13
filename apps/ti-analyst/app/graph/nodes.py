import json
import logging
import time
import uuid

import openai
import requests
from openai import OpenAI

from app.config import settings
from app.graph.state import AgentState
from app.middleware.trace import request_id_var, trace_id_var
from app.services.opensearch_client import OpenSearchClient

logger = logging.getLogger(__name__)

_SERVICE_NAME = "ti-analyst"
_LLM_TIMEOUT = 300  # seconds; DeepSeek ops reports can take 200s+ for long outputs
_RATE_LIMIT_RETRIES = 1       # retry once on 429 — LiteLLM fallback handles the rest
_RATE_LIMIT_SLEEP = 12        # seconds to wait; just enough for LiteLLM cooldown then retry_after


def _trace_context(feature_name: str) -> tuple[str, str, dict[str, str], str, dict]:
    """Build LiteLLM-compatible trace headers and metadata for a single LLM call."""
    base_request_id = request_id_var.get("") or f"ti-analyst-{uuid.uuid4()}"
    trace_id = trace_id_var.get("")
    effective_trace_id = trace_id or base_request_id
    session_id = effective_trace_id
    headers = {
        "x-request-id": base_request_id,
        "x-service-name": _SERVICE_NAME,
        "x-agent-name": _SERVICE_NAME,
        "x-feature-name": feature_name,
    }
    if trace_id:
        headers["x-trace-id"] = trace_id
    user_tag = f"service={_SERVICE_NAME};feature={feature_name};request_id={base_request_id}"
    metadata = {
        "request_id": base_request_id,
        "trace_id": effective_trace_id,
        "trace_name": f"{_SERVICE_NAME}.{feature_name}",
        "session_id": session_id,
        "generation_name": feature_name,
        "tags": [f"agent:{_SERVICE_NAME}", f"method:{feature_name}"],
        "trace_user_id": user_tag,
        "trace_metadata": {
            "request_id": base_request_id,
            "session_id": session_id,
            "agent_name": _SERVICE_NAME,
            "feature_name": feature_name,
        },
    }
    return base_request_id, trace_id, headers, user_tag, metadata


def _llm(model: str, prompt: str, content: str, feature_name: str, json_mode: bool = True,
         max_tokens: int | None = None) -> str:
    """Call LiteLLM with automatic retry on rate-limit (429) errors."""
    client = OpenAI(
        base_url=settings.litellm_base_url,
        api_key=settings.litellm_api_key,
        timeout=_LLM_TIMEOUT,
    )
    request_id, trace_id, llm_headers, user_tag, metadata = _trace_context(feature_name)
    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content},
        ],
        "temperature": 0.1,
        "user": user_tag,
        "metadata": metadata,
        "extra_headers": llm_headers,
        "extra_body": {"tags": [f"agent:{_SERVICE_NAME}", f"method:{feature_name}"]},
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

    for attempt in range(_RATE_LIMIT_RETRIES + 1):
        t0 = time.monotonic()
        try:
            response = client.chat.completions.create(**kwargs)
            duration_ms = int((time.monotonic() - t0) * 1000)
            usage = response.usage
            logger.info(
                "llm_call model=%s feature=%s duration_ms=%d prompt_tokens=%s completion_tokens=%s"
                " trace_id=%s request_id=%s",
                model, feature_name, duration_ms,
                usage.prompt_tokens if usage else "?",
                usage.completion_tokens if usage else "?",
                metadata["trace_id"], request_id,
            )
            return response.choices[0].message.content or ("{}" if json_mode else "")
        except (openai.RateLimitError, openai.APIConnectionError, json.JSONDecodeError) as exc:
            if isinstance(exc, openai.APITimeoutError):
                raise  # Timeouts: fail fast, don't retry with same long timeout
            if attempt < _RATE_LIMIT_RETRIES:
                # Short wait for transient decode errors; longer for rate limits
                wait = 5 if isinstance(exc, json.JSONDecodeError) else _RATE_LIMIT_SLEEP * (attempt + 1)
                logger.warning(
                    "LLM error model=%s feature=%s attempt=%d/%d (%s) — waiting %ds",
                    model, feature_name, attempt + 1, _RATE_LIMIT_RETRIES + 1,
                    type(exc).__name__, wait,
                )
                time.sleep(wait)
            else:
                raise
    return "{}" if json_mode else ""  # unreachable but satisfies type checker


def _report_agent(name: str) -> None:
    try:
        from app.services.progress import update as _pu
        _pu(current_agent=name)
    except Exception:
        pass


def ingestor_node(state: AgentState) -> AgentState:
    """Normalize raw input and extract structured threat data."""
    _report_agent("ingestor")
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
        result = json.loads(_llm(model, prompt, state["raw_content"], "ti.pipeline.ingestor"))
        if result.get("ignore"):
            return {**state, "ignore": True, "status": "ignored"}
        return {**state, "threat_profile": result, "ignore": False, "status": "triaged"}
    except Exception as exc:
        logger.error(
            "ingestor_node error trace_id=%s request_id=%s: %s",
            trace_id_var.get(""), request_id_var.get(""), exc,
        )
        return {**state, "error": str(exc), "status": "error"}


def analyst_node(state: AgentState) -> AgentState:
    """Deep analysis + deduplication via OpenSearch vector search."""
    _report_agent("analyst")
    logger.info("analyst_node: analyzing threat profile")
    model = state["model_config"].get("analyst_model", settings.analyst_model)
    prompt = state["model_config"].get("analyst_prompt", (
        "You are a senior CTI analyst. Given the threat profile, provide a deep analysis. "
        "Return JSON with: severity, confidence, attack_vectors (array), "
        "detection_strategies (array), mitigation_steps (array), needs_deep_research (bool)."
    ))
    try:
        analysis = json.loads(_llm(model, prompt, json.dumps(state["threat_profile"]), "ti.pipeline.analyst"))
        merged = {**state["threat_profile"], **analysis}

        # Try deduplication search
        try:
            os_client = OpenSearchClient()
            similar = os_client.search_similar_threats(state["threat_profile"].get("summary", ""), top_k=3)
            merged["similar_threats_found"] = len(similar)
        except Exception as os_err:
            logger.warning("OpenSearch dedup search failed trace_id=%s: %s", trace_id_var.get(""), os_err)

        return {**state, "threat_profile": merged, "status": "analyzed"}
    except Exception as exc:
        logger.error(
            "analyst_node error trace_id=%s request_id=%s: %s",
            trace_id_var.get(""), request_id_var.get(""), exc,
        )
        return {**state, "error": str(exc), "status": "error"}


def claw_bridge_node(state: AgentState) -> AgentState:
    """Delegate deep research to OpenClaw (if configured)."""
    _report_agent("claw_bridge")
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
        logger.warning("OpenClaw not reachable trace_id=%s: %s", trace_id_var.get(""), exc)
    return {**state, "research_data": None, "status": "analyzed"}


def infra_guard_node(state: AgentState) -> AgentState:
    """Correlate threat with asset inventory using local model."""
    _report_agent("infra_guard")
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
        if vendors:
            # Combine all vendor strings into one query so "Microsoft Windows" requires
            # both words to match — prevents "Microsoft" alone matching unrelated assets
            # like "Microsoft Kerberos" when the threat is Windows-specific.
            combined = " ".join(str(v) for v in vendors[:8])
            matches = os_client.search_assets(query=combined)
            # Deduplicate by asset id
            seen: set[str] = set()
            for m in matches:
                if m["id"] not in seen:
                    seen.add(m["id"])
                    affected.append(m)
    except Exception as exc:
        logger.warning("Asset search failed trace_id=%s: %s", trace_id_var.get(""), exc)

    try:
        infra_input = {
            "threat_profile": state["threat_profile"],
            "matched_assets": affected,
        }
        infra_analysis = json.loads(_llm(model, prompt, json.dumps(infra_input), "ti.pipeline.infra_guard"))
        merged_profile = {**state["threat_profile"], **infra_analysis}
        return {**state, "affected_assets": affected, "threat_profile": merged_profile, "status": "correlated"}
    except Exception as exc:
        logger.error(
            "infra_guard_node error trace_id=%s request_id=%s: %s",
            trace_id_var.get(""), request_id_var.get(""), exc,
        )
        return {**state, "affected_assets": affected, "status": "correlated", "error": str(exc)}


def publisher_node(state: AgentState) -> AgentState:
    """Generate Operations and Executive reports."""
    _report_agent("publisher")
    logger.info("publisher_node: generating reports")
    analyst_model = state["model_config"].get("analyst_model", settings.analyst_model)
    ops_prompt = state["model_config"].get("publisher_ops_prompt", (
        "You are a technical security writer. Create a detailed Operations Report in Markdown. "
        "Include: threat summary, CVEs, affected systems, detection commands, patch status, references. "
        "Write the entire report in Ukrainian language. "
        "Target length: 350 words. Always finish the last sentence completely before stopping."
    ))
    exec_prompt = state["model_config"].get("publisher_exec_prompt", (
        "You are a CISO advisor. Create a concise Executive Summary. "
        "Include: risk level, business impact, recommended actions, financial exposure estimate. "
        "Write the entire summary in Ukrainian language. "
        "Target length: 120 words. Always finish the last sentence completely before stopping."
    ))
    full_context = json.dumps({
        "threat_profile": state["threat_profile"],
        "affected_assets": state["affected_assets"],
        "research_data": state.get("research_data"),
    })
    reports: dict[str, str] = {}
    try:
        # max_tokens accounts for Ukrainian Cyrillic (~5 tokens/word) + Markdown overhead (~15%)
        # ops:  500 words × 5 × 1.15 ≈ 2900 tokens  (no word cap in DB prompt → LLM may write more)
        # exec: 200 words × 5 × 1.15 ≈ 1150 tokens
        reports["ops"] = _llm(analyst_model, ops_prompt, full_context, "ti.pipeline.publisher.ops", json_mode=False, max_tokens=3000)
        reports["executive"] = _llm(analyst_model, exec_prompt, full_context, "ti.pipeline.publisher.exec", json_mode=False, max_tokens=1200)
    except Exception as exc:
        logger.error(
            "publisher_node error trace_id=%s request_id=%s: %s",
            trace_id_var.get(""), request_id_var.get(""), exc,
        )
        reports["error"] = str(exc)

    return {**state, "reports": reports, "status": "reported"}

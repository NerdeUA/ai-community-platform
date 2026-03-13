"""Unit tests for LangGraph pipeline nodes — LLM calls are fully mocked."""
import json
from unittest.mock import MagicMock, patch

from app.graph.state import AgentState


def _make_state(**overrides) -> AgentState:
    base: AgentState = {
        "raw_content": "CVE-2024-1234: critical RCE in OpenSSH",
        "metadata": {},
        "threat_profile": {},
        "research_data": None,
        "affected_assets": [],
        "reports": {},
        "model_config": {},
        "status": "new",
        "ignore": False,
        "error": None,
    }
    base.update(overrides)
    return base


def _mock_llm_response(content: dict) -> MagicMock:
    choice = MagicMock()
    choice.message.content = json.dumps(content)
    response = MagicMock()
    response.choices = [choice]
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    return response


@patch("app.graph.nodes.OpenAI")
def test_ingestor_node_returns_triaged(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_llm_response({
        "title": "Critical OpenSSH RCE",
        "threat_type": "rce",
        "cve_ids": ["CVE-2024-1234"],
        "severity": "critical",
        "confidence": "high",
        "affected_vendors": ["OpenSSH"],
        "summary": "Critical remote code execution.",
    })

    from app.graph.nodes import ingestor_node
    result = ingestor_node(_make_state())

    assert result["status"] == "triaged"
    assert result["ignore"] is False
    assert result["threat_profile"]["severity"] == "critical"
    # Verify extra_body with tags was passed
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "extra_body" in call_kwargs
    assert any("agent:ti-analyst" in t for t in call_kwargs["extra_body"].get("tags", []))


@patch("app.graph.nodes.OpenAI")
def test_ingestor_node_ignores_noise(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_llm_response({"ignore": True})

    from app.graph.nodes import ingestor_node
    result = ingestor_node(_make_state(raw_content="Today's weather is sunny."))

    assert result["ignore"] is True
    assert result["status"] == "ignored"


@patch("app.graph.nodes.OpenAI")
def test_ingestor_node_handles_llm_error(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.side_effect = RuntimeError("LLM timeout")

    from app.graph.nodes import ingestor_node
    result = ingestor_node(_make_state())

    assert result["status"] == "error"
    assert "LLM timeout" in result["error"]


@patch("app.graph.nodes.OpenSearchClient")
@patch("app.graph.nodes.OpenAI")
def test_analyst_node_returns_analyzed(mock_openai_cls, mock_os_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_llm_response({
        "severity": "critical",
        "confidence": "high",
        "attack_vectors": ["network"],
        "detection_strategies": ["monitor"],
        "mitigation_steps": ["patch"],
        "needs_deep_research": False,
    })
    mock_os_cls.return_value.search_similar_threats.return_value = []

    from app.graph.nodes import analyst_node
    state = _make_state(
        status="triaged",
        threat_profile={"title": "Test", "summary": "Test threat", "severity": "critical"},
    )
    result = analyst_node(state)

    assert result["status"] == "analyzed"
    assert "attack_vectors" in result["threat_profile"]
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "extra_body" in call_kwargs
    assert any("method:ti.pipeline.analyst" in t for t in call_kwargs["extra_body"].get("tags", []))


@patch("app.graph.nodes.OpenSearchClient")
@patch("app.graph.nodes.OpenAI")
def test_infra_guard_node_correlates(mock_openai_cls, mock_os_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_llm_response({
        "exposed_assets": [],
        "overall_risk": "high",
        "remediation_priority": "immediate",
    })
    mock_os_cls.return_value.search_assets.return_value = []

    from app.graph.nodes import infra_guard_node
    state = _make_state(
        status="analyzed",
        threat_profile={"affected_vendors": ["cisco"], "summary": "Test"},
    )
    result = infra_guard_node(state)

    assert result["status"] == "correlated"
    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "extra_body" in call_kwargs
    assert any("method:ti.pipeline.infra_guard" in t for t in call_kwargs["extra_body"].get("tags", []))


@patch("app.graph.nodes.OpenAI")
def test_publisher_node_generates_reports(mock_openai_cls):
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    ops_choice = MagicMock()
    ops_choice.message.content = "## Ops Report\nDetails here."
    exec_choice = MagicMock()
    exec_choice.message.content = "Executive summary."
    mock_client.chat.completions.create.side_effect = [
        MagicMock(choices=[ops_choice]),
        MagicMock(choices=[exec_choice]),
    ]

    from app.graph.nodes import publisher_node
    state = _make_state(
        status="correlated",
        threat_profile={"title": "Test", "severity": "high"},
        affected_assets=[],
    )
    result = publisher_node(state)

    assert result["status"] == "reported"
    assert result["reports"]["ops"] == "## Ops Report\nDetails here."
    assert result["reports"]["executive"] == "Executive summary."
    assert mock_client.chat.completions.create.call_count == 2
    # Both calls must carry agent tags
    for call in mock_client.chat.completions.create.call_args_list:
        assert "extra_body" in call.kwargs
        assert any("agent:ti-analyst" in t for t in call.kwargs["extra_body"].get("tags", []))


@patch("app.graph.nodes.OpenAI")
def test_llm_passes_metadata_and_headers(mock_openai_cls):
    """Every _llm() call must pass metadata and extra_headers to LiteLLM."""
    mock_client = MagicMock()
    mock_openai_cls.return_value = mock_client
    mock_client.chat.completions.create.return_value = _mock_llm_response({"ignore": True})

    from app.graph.nodes import ingestor_node
    ingestor_node(_make_state())

    call_kwargs = mock_client.chat.completions.create.call_args.kwargs
    assert "metadata" in call_kwargs
    assert "extra_headers" in call_kwargs
    assert "x-service-name" in call_kwargs["extra_headers"]
    assert call_kwargs["extra_headers"]["x-service-name"] == "ti-analyst"
    assert "trace_name" in call_kwargs["metadata"]

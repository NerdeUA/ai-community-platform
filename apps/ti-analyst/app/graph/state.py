from typing import Any, Optional, TypedDict


class AgentState(TypedDict):
    """LangGraph state shared across all nodes in the CTI pipeline."""
    raw_content: str
    metadata: dict[str, Any]
    threat_profile: dict[str, Any]
    research_data: Optional[dict[str, Any]]
    affected_assets: list[dict[str, Any]]
    reports: dict[str, str]
    model_config: dict[str, str]
    status: str
    ignore: bool
    error: Optional[str]

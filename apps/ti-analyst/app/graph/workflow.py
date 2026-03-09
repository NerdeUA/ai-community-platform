from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    analyst_node,
    claw_bridge_node,
    infra_guard_node,
    ingestor_node,
    publisher_node,
)
from app.graph.state import AgentState


def _should_research(state: AgentState) -> str:
    """Conditional edge: decide whether to use ClawBridge."""
    if state.get("ignore") or state.get("status") in ("error", "ignored"):
        return "skip"
    from app.config import settings
    if settings.openclaw_enabled and state["threat_profile"].get("needs_deep_research"):
        return "research"
    return "skip"


def _after_ingestor(state: AgentState) -> str:
    if state.get("ignore") or state.get("status") in ("error", "ignored"):
        return "end"
    return "continue"


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    graph.add_node("ingestor", ingestor_node)
    graph.add_node("analyst", analyst_node)
    graph.add_node("claw_bridge", claw_bridge_node)
    graph.add_node("infra_guard", infra_guard_node)
    graph.add_node("publisher", publisher_node)

    graph.add_edge(START, "ingestor")

    graph.add_conditional_edges(
        "ingestor",
        _after_ingestor,
        {"end": END, "continue": "analyst"},
    )

    graph.add_conditional_edges(
        "analyst",
        _should_research,
        {"research": "claw_bridge", "skip": "infra_guard"},
    )

    graph.add_edge("claw_bridge", "analyst")
    graph.add_edge("infra_guard", "publisher")
    graph.add_edge("publisher", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
    return _compiled_graph

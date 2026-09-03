"""ServiceNow-only RCA workflow.

Seven nodes against the payment pipeline's eleven: there is no knowledge base
and no code repository behind this data, so those stages are absent rather than
stubbed out.
"""

from langgraph.graph import END, StateGraph

from src.agents.incident_clarification_agent import (
    incident_clarification_agent
)

from src.agents.incident_evaluator import incident_evaluator_agent

from src.agents.incident_query_analyzer import (
    incident_query_analyzer_node
)

from src.agents.incident_rca_agent import incident_rca_agent

from src.agents.incident_validation_agent import (
    incident_validation_agent
)

from src.graph.incident_state import IncidentRCAState

from src.nodes.incident_evidence import incident_evidence_node

from src.nodes.incident_retriever import incident_retriever_node


# ---------------------------------
# Routers
# ---------------------------------


def clarification_router(state):

    if state.get("needs_clarification"):
        return "clarification"

    return "retrieve"


def evaluation_router(state):
    """Dead-end only when there is genuinely nothing to analyse.

    Partial evidence still produces a useful analysis - the RCA agent is told to
    lower its confidence rather than invent a cause - so only a complete absence
    of matching records sends the user back for more detail.
    """

    if not state.get("matching_records"):
        return "clarification"

    return "evidence"


def validation_router(state):

    if state.get("needs_human_input"):
        return "clarification"

    return "end"


# ---------------------------------
# Graph
# ---------------------------------


workflow = StateGraph(
    IncidentRCAState
)


workflow.add_node(
    "query_analyzer",
    incident_query_analyzer_node
)

workflow.add_node(
    "clarification",
    incident_clarification_agent
)

workflow.add_node(
    "retrieve",
    incident_retriever_node
)

workflow.add_node(
    "evaluate",
    incident_evaluator_agent
)

workflow.add_node(
    "evidence",
    incident_evidence_node
)

workflow.add_node(
    "rca",
    incident_rca_agent
)

workflow.add_node(
    "validation",
    incident_validation_agent
)


workflow.set_entry_point(
    "query_analyzer"
)


workflow.add_conditional_edges(

    "query_analyzer",

    clarification_router,

    {
        "clarification": "clarification",
        "retrieve": "retrieve"
    }

)


workflow.add_edge(
    "clarification",
    END
)


workflow.add_edge(
    "retrieve",
    "evaluate"
)


workflow.add_conditional_edges(

    "evaluate",

    evaluation_router,

    {
        "clarification": "clarification",
        "evidence": "evidence"
    }

)


workflow.add_edge(
    "evidence",
    "rca"
)


workflow.add_edge(
    "rca",
    "validation"
)


workflow.add_conditional_edges(

    "validation",

    validation_router,

    {
        "clarification": "clarification",
        "end": END
    }

)


graph = workflow.compile()

"""Incident RCA workflow: ticket history first, REMAN documentation second.

Nine nodes against the payment pipeline's eleven. The GitHub stage is absent
rather than stubbed out - there is no code repository behind this data - but
the documentation stage does not.

The payment pipeline escalates to its knowledge base only when ServiceNow falls
short, because there both sources answer the same question. Here they do not:
history establishes what happened and what fixed it, documentation explains the
mechanism underneath. Complementary sources have to be consulted together, so
documentation always runs.

That was not the first design, and the reason for changing it is worth keeping.
Under escalation, "LMS went down, IN001.MST was corrupted" matched eight past
incidents, the evaluator returned enough_information at 0.95, and the documents
were skipped. The RCA then concluded that "IN001.MST/IN0011.MST ... appears to
refer to the same component" at 0.88 confidence. The documentation says
otherwise in as many words: IN0001.MST is the Inventory Master, IN0011.MST is
the Location File. Strong history is exactly when the agent is most confident,
which makes it exactly when an unchecked assumption does the most damage.
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

from src.agents.reman_docs_evaluator import reman_docs_evaluator_agent

from src.nodes.incident_retriever import incident_retriever_node

from src.nodes.reman_docs_retriever import reman_docs_retriever_node


# ---------------------------------
# Routers
# ---------------------------------


def clarification_router(state):

    if state.get("needs_clarification"):
        return "clarification"

    return "retrieve"


def documentation_router(state):
    """The end of the line: there is no third source behind this one.

    Anything worth citing - a matched record or a matched document - is worth
    analysing, because the RCA agent is told to lower its confidence rather
    than invent a cause. Only when both sources come back empty is the honest
    answer that there is not enough information.
    """

    if state.get("matching_records") or state.get("matching_documents"):
        return "evidence"

    return "clarification"


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
    "docs_retrieve",
    reman_docs_retriever_node
)

workflow.add_node(
    "docs_evaluate",
    reman_docs_evaluator_agent
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


workflow.add_edge(
    "evaluate",
    "docs_retrieve"
)


workflow.add_edge(
    "docs_retrieve",
    "docs_evaluate"
)


workflow.add_conditional_edges(

    "docs_evaluate",

    documentation_router,

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

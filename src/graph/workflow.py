from langgraph.graph import (
    StateGraph,
    END
)


from src.graph.state import RCAState


from src.nodes.query_analyzer import (
    query_analyzer_node
)


from src.agents.clarification_agent import (
    clarification_agent
)


from src.nodes.servicenow_retriever import (
    servicenow_retriever_node
)


from src.agents.servicenow_evaluator import (
    servicenow_evaluator_agent
)


from src.nodes.kb_retriever import (
    kb_retriever_node
)


from src.agents.kb_evaluator import (
    kb_evaluator_agent
)


from src.nodes.evidence_aggregator import (
    evidence_aggregator_node
)


from src.agents.rca_agent import (
    rca_agent
)


from src.agents.validation_agent import (
    validation_agent
)



# ---------------------------------
# Router functions
# ---------------------------------


def clarification_router(state):

    if state["needs_clarification"]:

        return "clarification"

    return "servicenow"



def kb_router(state):

    if state["need_kb"]:

        return "kb"

    return "evidence"



def validation_router(state):

    if state["needs_human_input"]:

        return "clarification"

    return "end"



# ---------------------------------
# Build graph
# ---------------------------------


workflow = StateGraph(
    RCAState
)



workflow.add_node(
    "query_analyzer",
    query_analyzer_node
)


workflow.add_node(
    "clarification",
    clarification_agent
)


workflow.add_node(
    "servicenow",
    servicenow_retriever_node
)


workflow.add_node(
    "servicenow_evaluator",
    servicenow_evaluator_agent
)


workflow.add_node(
    "kb_retriever",
    kb_retriever_node
)


workflow.add_node(
    "kb_evaluator",
    kb_evaluator_agent
)


workflow.add_node(
    "evidence",
    evidence_aggregator_node
)


workflow.add_node(
    "rca",
    rca_agent
)


workflow.add_node(
    "validation",
    validation_agent
)



# ---------------------------------
# Edges
# ---------------------------------


workflow.set_entry_point(
    "query_analyzer"
)



workflow.add_conditional_edges(

    "query_analyzer",

    clarification_router,

    {
        "clarification":
            "clarification",

        "servicenow":
            "servicenow"
    }

)



workflow.add_edge(
    "clarification",
    END
)



workflow.add_edge(
    "servicenow",
    "servicenow_evaluator"
)



workflow.add_conditional_edges(

    "servicenow_evaluator",

    kb_router,

    {
        "kb":
            "kb_retriever",

        "evidence":
            "evidence"
    }

)



workflow.add_edge(
    "kb_retriever",
    "kb_evaluator"
)


workflow.add_edge(
    "kb_evaluator",
    "evidence"
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

        "clarification":
            "clarification",

        "end":
            END

    }

)



graph = workflow.compile()
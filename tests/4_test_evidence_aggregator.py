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

from src.nodes.evidence_aggregator import (
    evidence_aggregator_node
)

from src.agents.kb_evaluator import (
    kb_evaluator_agent
)

# ----------------------------------------
# Initial State
# ----------------------------------------

state = {

    "user_query":

    """
    Payment Gateway transactions are failing
    with timeout errors after yesterday deployment
    """

}


# ----------------------------------------
# Query Understanding
# ----------------------------------------

state.update(
    query_analyzer_node(
        state
    )
)


# ----------------------------------------
# Clarification Check
# ----------------------------------------

if state["needs_clarification"]:

    state.update(
        clarification_agent(
            state
        )
    )


    print(
        state["final_response"]
    )


    exit()



# ----------------------------------------
# ServiceNow Retrieval
# ----------------------------------------

state.update(

    servicenow_retriever_node(
        state
    )

)



# ----------------------------------------
# ServiceNow Evaluation
# ----------------------------------------

state.update(

    servicenow_evaluator_agent(
        state
    )

)



# ----------------------------------------
# KB Retrieval if required
# ----------------------------------------

if state["need_kb"]:


    state.update(

        kb_retriever_node(
            state
        )

    )


else:


    state["kb_results"] = []

state.update(
    kb_evaluator_agent(state)
)


# ----------------------------------------
# Evidence Aggregation
# ----------------------------------------

state.update(

    evidence_aggregator_node(
        state
    )

)





# ----------------------------------------
# Print Evidence
# ----------------------------------------

print(
    "\n========== FINAL EVIDENCE =========="
)


for evidence in state["combined_evidence"]:


    print(
        "\nSOURCE:",
        evidence["source_type"]
    )


    print(
        "ID:",
        evidence["source_id"]
    )


    print(
        "CONFIDENCE:",
        evidence["confidence"]
    )


    print(
        "\nCONTENT:"
    )


    print(
        evidence["content"][:500]
    )


    print(
        "-" * 50
    )
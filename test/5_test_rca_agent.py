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


# -----------------------------------------
# Initial State
# -----------------------------------------

state = {

    "user_query":

    """
    Payment Gateway transactions are failing
    with timeout errors after yesterday deployment
    """

}


# -----------------------------------------
# 1. Query Analyzer
# -----------------------------------------

state.update(

    query_analyzer_node(
        state
    )

)



# -----------------------------------------
# 2. Clarification Routing
# -----------------------------------------

if state["needs_clarification"]:


    state.update(

        clarification_agent(
            state
        )

    )


    print(
        "\n===== CLARIFICATION REQUIRED ====="
    )


    print(
        state["final_response"]
    )


    exit()



# -----------------------------------------
# 3. ServiceNow Retrieval
# -----------------------------------------

state.update(

    servicenow_retriever_node(
        state
    )

)



# -----------------------------------------
# 4. ServiceNow Evaluation
# -----------------------------------------

state.update(

    servicenow_evaluator_agent(
        state
    )

)



# -----------------------------------------
# 5. KB Retrieval (Conditional)
# -----------------------------------------

if state["need_kb"]:


    state.update(

        kb_retriever_node(
            state
        )

    )


    # -------------------------------------
    # 6. KB Evaluation
    # -------------------------------------


    state.update(

        kb_evaluator_agent(
            state
        )

    )


else:


    state["filtered_kb_results"] = []



# -----------------------------------------
# 7. Evidence Aggregation
# -----------------------------------------

state.update(

    evidence_aggregator_node(
        state
    )

)



print(
    "\n===== FINAL CONTEXT SENT TO RCA ====="
)


for item in state["combined_evidence"]:


    print(
        "\nSOURCE:",
        item["source_type"]
    )


    print(
        "ID:",
        item["source_id"]
    )


    print(
        item["content"][:300]
    )


    print(
        "-" * 50
    )



# -----------------------------------------
# 8. RCA Agent
# -----------------------------------------

state.update(

    rca_agent(
        state
    )

)



# -----------------------------------------
# Display RCA
# -----------------------------------------

result = state["rca_result"]



print(
    "\n\n=============================="
)

print(
    " FINAL ROOT CAUSE ANALYSIS"
)

print(
    "=============================="
)



print(
    "\nRoot Cause:\n"
)

print(
    result["root_cause"]
)



print(
    "\nEvidence:\n"
)


for evidence in result["evidence"]:


    print(
        "-",
        evidence
    )



print(
    "\nResolution Steps:\n"
)


for step in result["resolution_steps"]:


    print(
        "-",
        step
    )



print(
    "\nPreventive Actions:\n"
)


for action in result["preventive_actions"]:


    print(
        "-",
        action
    )



print(
    "\nConfidence Score:"
)

print(
    result["confidence_score"]
)



if result["requires_more_information"]:


    print(
        "\nAdditional Information Required:"
    )


    for item in result["missing_information"]:


        print(
            "-",
            item
        )
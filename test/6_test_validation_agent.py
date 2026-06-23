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


# ---------------------------------------------------
# Initial State
# ---------------------------------------------------

state = {

    "user_query":

    """
    Payment Gateway transactions are failing
    with timeout errors after yesterday deployment
    """

}


# ---------------------------------------------------
# 1. Query Understanding
# ---------------------------------------------------

state.update(

    query_analyzer_node(
        state
    )

)


# ---------------------------------------------------
# 2. Initial Clarification Check
# ---------------------------------------------------

if state[
    "needs_clarification"
]:


    state.update(

        clarification_agent(
            state
        )

    )


    print(
        "\n========== NEED USER INPUT =========="
    )


    print(
        state["final_response"]
    )


    exit()



# ---------------------------------------------------
# 3. ServiceNow Retrieval
# ---------------------------------------------------

state.update(

    servicenow_retriever_node(
        state
    )

)



# ---------------------------------------------------
# 4. ServiceNow Evidence Evaluation
# ---------------------------------------------------

state.update(

    servicenow_evaluator_agent(
        state
    )

)



# ---------------------------------------------------
# 5. Conditional KB Retrieval
# ---------------------------------------------------

if state[
    "need_kb"
]:


    state.update(

        kb_retriever_node(
            state
        )

    )


    state.update(

        kb_evaluator_agent(
            state
        )

    )


else:


    state[
        "filtered_kb_results"
    ] = []



# ---------------------------------------------------
# 6. Evidence Aggregation
# ---------------------------------------------------

state.update(

    evidence_aggregator_node(
        state
    )

)



print(
    "\n========== EVIDENCE SENT TO RCA =========="
)


for item in state[
    "combined_evidence"
]:


    print(
        "\nSOURCE:",
        item[
            "source_type"
        ]
    )


    print(
        "ID:",
        item[
            "source_id"
        ]
    )


    print(
        item[
            "content"
        ][:300]
    )


    print(
        "-" * 60
    )



# ---------------------------------------------------
# 7. RCA Generation
# ---------------------------------------------------

state.update(

    rca_agent(
        state
    )

)



# ---------------------------------------------------
# 8. RCA Validation
# ---------------------------------------------------

state.update(

    validation_agent(
        state
    )

)



# ---------------------------------------------------
# Final Output Handling
# ---------------------------------------------------

validation = state[
    "validation_result"
]


print(
    "\n\n================================"
)

print(
    " RCA VALIDATION RESULT"
)

print(
    "================================"
)



print(
    "\nValid RCA:"
)

print(
    validation[
        "is_valid"
    ]
)



print(
    "\nValidation Confidence:"
)

print(
    validation[
        "confidence_score"
    ]
)



print(
    "\nDecision:"
)

print(
    validation[
        "final_decision"
    ]
)



print(
    "\nIssues Found:"
)


if validation[
    "issues_found"
]:


    for issue in validation[
        "issues_found"
    ]:


        print(
            "-",
            issue
        )


else:


    print(
        "None"
    )



# ---------------------------------------------------
# Either Final RCA or Clarification
# ---------------------------------------------------

if state[
    "needs_human_input"
]:


    print(
        "\n========== NEED MORE INFORMATION =========="
    )


    for item in state[
        "final_missing_information"
    ]:


        print(
            "-",
            item
        )



else:


    rca = state[
        "rca_result"
    ]


    print(
        "\n\n================================"
    )

    print(
        " FINAL APPROVED RCA"
    )

    print(
        "================================"
    )


    print(
        "\nRoot Cause:\n"
    )


    print(
        rca[
            "root_cause"
        ]
    )


    print(
        "\nEvidence:\n"
    )


    for item in rca[
        "evidence"
    ]:


        print(
            "-",
            item
        )



    print(
        "\nResolution Steps:\n"
    )


    for step in rca[
        "resolution_steps"
    ]:


        print(
            "-",
            step
        )



    print(
        "\nPreventive Actions:\n"
    )


    for action in rca[
        "preventive_actions"
    ]:


        print(
            "-",
            action
        )



    print(
        "\nRCA Confidence:"
    )


    print(
        rca[
            "confidence_score"
        ]
    )
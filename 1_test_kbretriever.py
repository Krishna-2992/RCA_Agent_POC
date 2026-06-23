from src.nodes.query_analyzer import (
    query_analyzer_node
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


state = {

"user_query":

"""
Payment Gateway transactions are failing
with timeout errors after yesterday deployment
"""

}


state.update(
    query_analyzer_node(state)
)


state.update(
    servicenow_retriever_node(state)
)


state.update(
    servicenow_evaluator_agent(state)
)


if state["need_kb"]:

    state.update(
        kb_retriever_node(state)
    )


print("\n===== KB RESULTS =====")



for doc in state.get(
    "kb_results",
    []
):

    print(
        "\nDocument:",
        doc["document_name"]
    )

    print(
        "Score:",
        doc["score"]
    )

    print(
        doc["content"][:500]
    )

    print("--------------------")
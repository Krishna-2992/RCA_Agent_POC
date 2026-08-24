from src.nodes.query_analyzer import (
    query_analyzer_node
)

from src.agents.clarification_agent import (
    clarification_agent
)


state = {

"user_query":

"""
Something is not working properly
"""

}


state.update(
    query_analyzer_node(state)
)


if state["needs_clarification"]:

    state.update(
        clarification_agent(state)
    )


print(
    state["final_response"]
)
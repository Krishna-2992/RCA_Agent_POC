from src.utils.llm import llm


def clarification_agent(state):

    print("\n--- Clarification Agent ---")

    missing = state.get(
        "missing_information",
        []
    )

    user_query = state["user_query"]


    prompt = f"""

You are an incident RCA assistant.

The user provided this incident:

{user_query}


However, some critical information required to begin investigation is missing:

{missing}


Generate a short and clear follow-up question.

Rules:

- Ask only for missing critical information
- Do not ask for logs
- Do not ask for metrics
- Do not ask unnecessary debugging details
- Maximum 3 questions

"""


    response = llm.invoke(
        prompt
    )


    return {

        "final_response":
            response.content
    }
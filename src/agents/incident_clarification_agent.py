"""Asks for what is actually missing, as a list the UI can render.

The payment pipeline's clarification agent returns one free-text blob. Here the
questions are returned individually so the app can present them as a checklist
and so the same node can serve both entry points - a report too vague to search,
and an analysis the validator would not approve.
"""

from typing import List

from pydantic import BaseModel, Field

from src.utils.llm import llm


class ClarificationQuestions(BaseModel):

    questions: List[str] = Field(
        description=(
            "At most three short, specific questions. Each asks for one thing "
            "the reporter can reasonably answer."
        )
    )


structured_llm = llm.with_structured_output(
    ClarificationQuestions
)


def incident_clarification_agent(state):

    print("\n--- Clarification Agent ---")

    missing = (
        state.get("final_missing_information")
        or state.get("missing_information")
        or []
    )

    searched = state.get("servicenow_results") or []

    prompt = f"""
You are a production support engineer who cannot yet investigate an incident.

Incident as reported:
{state["user_query"]}

What is missing or unresolved:
{missing}

Historical records were searched and {len(searched)} were returned, none of
which matched closely enough to explain this incident.

Write at most three short questions that would let the search succeed.

Rules:
- Ask only for what a person reporting the problem would plausibly know:
  the system or screen affected, what they saw, an error or abend code shown,
  the job, program or file named in the message, when it started.
- Do not ask for logs, metrics, traces or stack dumps.
- Do not ask for a ticket number.
- One thing per question, in plain language.
"""

    response = structured_llm.invoke(
        prompt
    )

    questions = response.questions[:3]

    print(f"questions={questions}")

    return {
        "clarification_questions": questions,
        "needs_human_input": True
    }

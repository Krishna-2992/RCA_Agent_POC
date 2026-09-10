"""Asks for what is actually missing, as a list the UI can render.

The payment pipeline's clarification agent returns one free-text blob. Here the
questions are returned individually so the app can present them as a checklist
and so the same node can serve both entry points - a report too vague to search,
and an analysis the validator would not approve.

What it asks is grounded in the REMAN digest rather than left to the model.
Ungrounded, it asked the questions any support engineer would ask of any system,
and some of them could not be answered at all: "LMS is not working" came back
with a request for the page URL, of a COBOL application running on a terminal.
A question the reporter can answer in the documents' own vocabulary is worth
several that merely sound diligent.

Two rules follow from the digest and neither is obvious. The application is
usually already known from the report, so asking for it wastes the one question
the reporter will reliably answer; what is worth asking is the screen they were
on, because that maps to a menu section the documentation describes. And the
file name is almost never derivable from the application - Inventory and LMS
share IN0011.MST - so "which application" does not identify the file, whereas
the error text on screen names it outright.
"""

from typing import List

from pydantic import BaseModel, Field

from src.domain.reman_digest import (
    digest_for_prompt,
    estate_summary,
    resolve_application,
    resolve_error_family
)

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


def known_context(state):
    """What the report already settled, so the agent does not ask again.

    Reads the analyser's entities where they exist and falls back to the raw
    query, because this node also serves the post-validation entry point where
    extraction ran long before the questions are written.
    """

    entities = state.get("extracted_entities") or {}

    haystack = " ".join(
        str(value)
        for value in (
            state.get("user_query"),
            entities.get("service"),
            entities.get("component"),
            entities.get("symptom"),
            entities.get("error_code")
        )
        if value
    )

    applications = (
        state.get("rewrite_applications")
        or resolve_application(haystack)
    )

    return {
        "applications": applications,
        "error_family": resolve_error_family(haystack),
        "component": entities.get("component"),
        "digest": digest_for_prompt(applications)
    }


def incident_clarification_agent(state):

    print("\n--- Clarification Agent ---")

    missing = (
        state.get("final_missing_information")
        or state.get("missing_information")
        or []
    )

    searched = state.get("servicenow_results") or []

    context = known_context(state)

    applications = context["applications"]

    family = context["error_family"]

    # Spelled out rather than left implicit: the model is being asked not to
    # re-ask these, and it obeys a stated fact more reliably than an omission.
    settled = []

    if applications:

        settled.append(
            "Application already identified from the report: "
            + ", ".join(applications)
        )

    if family:

        settled.append(
            "Error code already reported, and it belongs to the "
            f"{family['means'].lower()} family"
        )

    if context["component"]:

        settled.append(
            f"Program or file already named: {context['component']}"
        )

    prompt = f"""
You are a production support engineer who cannot yet investigate a REMAN
incident.

Incident as reported:
{state["user_query"]}

What is missing or unresolved:
{missing}

Already established, so do not ask for it again:
{settled or "nothing - the report is too vague to place"}

Historical records were searched and {len(searched)} were returned, none of
which matched closely enough to explain this incident.

The REMAN estate:
{estate_summary()}

Reference for the applications in play - their screens, the data files they
open, and how each recovers a damaged file:

{context["digest"]}

Write at most three short questions that would let the search succeed.

Rules:
- These are COBOL applications on terminals. There is no web page, no URL, no
  browser and no stack trace. Never ask for any of those.
- Aim each question at something the reference above can be matched against:
  the application, the screen or menu option they were on, the file named in
  the error message, the error number shown.
- If the application is already established, do not ask which application. Ask
  which screen or menu option instead.
- Several applications open the same data files, so the application never
  identifies the file. If a file may be damaged and none is named, ask the
  reporter to read the file name out of the error message.
- Ask only for what a person at a terminal can see and answer.
- Do not ask for logs, metrics, traces or stack dumps.
- Do not ask for a ticket number.
- One thing per question, in plain language.
"""

    response = structured_llm.invoke(
        prompt
    )

    questions = response.questions[:3]

    print(
        f"applications={applications} "
        f"error_family={family['means'] if family else None}"
    )

    print(f"questions={questions}")

    return {
        "clarification_questions": questions,
        "needs_human_input": True
    }

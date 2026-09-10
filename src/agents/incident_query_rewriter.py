"""Turns a reported incident into a question the corpus can answer.

Measured, this is the stage that decides retrieval quality. Searching the
documentation with "file is corrupted and giving error code 98, what do I need
for recovery for inventory system" returns fifty estate-catalogue one-liners in
the top sixty and nothing about the recovery screen. Searching it with the same
incident restated in the documents' own vocabulary - the program name, the file
name, the section that performs recovery - returns zero catalogue entries in the
top twenty and puts the recovery screen at rank three.

The corpus did not change between those two searches. Only the question did.

That is why this runs before retrieval rather than after, and why the earlier
attempt at fixing the same symptom downstream - excluding the catalogue by
payload filter, adding a second procedural query - was treating a shadow. A
specific question does not need those defences; a vague one is not saved by
them.

Two responsibilities, in order:

Sufficiency. A report that names no system the estate contains, or names one but
describes nothing that happened, cannot be rewritten into anything useful and
should go to clarification instead. Judged against the digest rather than in the
abstract, so "the printer is jammed" is insufficient for a different reason than
"it is broken" - one is out of scope, the other is contentless.

Rewriting. What survives is restated using the names the documents use, with the
reporter's own words kept alongside rather than replaced. Kept because the ticket
history is searched with the same text and it speaks the reporter's language, not
the documentation's: "can not load lms" matches past incidents precisely because
it is how people write.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from src.domain.reman_digest import (
    DATA_FILES,
    canonical_file,
    digest_for_prompt,
    estate_summary,
    resolve_application,
    resolve_error_family
)

from src.utils.llm import llm


class RewrittenQuery(BaseModel):

    is_sufficient: bool = Field(
        description=(
            "True when the report names a REMAN system in the estate and "
            "describes something observable that happened to it."
        )
    )

    rewritten_query: Optional[str] = Field(
        description=(
            "The incident restated in the documentation's vocabulary - "
            "application, program, data file, section names. Empty when the "
            "report is not sufficient."
        )
    )

    applications: List[str] = Field(
        description="Applications the report concerns, from the estate list."
    )

    data_files: List[str] = Field(
        description=(
            "Only data files the report itself names, e.g. IN0011.MST. Empty "
            "when the report names none - do not list candidates."
        )
    )

    missing_information: List[str] = Field(
        description=(
            "What a reporter would have to add to make this investigable. "
            "Empty when the report is sufficient."
        )
    )

    reasoning: str = Field(
        description="One or two sentences on the sufficiency judgement."
    )


structured_llm = llm.with_structured_output(
    RewrittenQuery
)


def incident_query_rewriter_node(state):

    print("\n--- Query Rewriter ---")

    # A reporter who has read the rewrite and corrected it has more context
    # than this node does - they can see the screen. Their wording is used as
    # given and the model is not consulted, because re-deriving it would throw
    # away the correction they came here to make.
    if state.get("rewrite_locked") and state.get("rewritten_query"):

        print("using the reporter's own rewrite; skipping the model")

        return {
            "missing_information": [],
            "needs_clarification": False
        }

    entities = state.get("extracted_entities") or {}

    query = state["user_query"]

    haystack = " ".join(
        str(value)
        for value in (
            query,
            entities.get("service"),
            entities.get("component"),
            entities.get("symptom"),
            entities.get("error_code")
        )
        if value
    )

    # Resolved before the model is asked, so the prompt states what is already
    # known rather than inviting it to re-derive - and so a digest that resolves
    # nothing is visible in the logs as an alias gap rather than a model error.
    applications = resolve_application(haystack)

    family = resolve_error_family(haystack)

    prompt = f"""
You are a REMAN support engineer preparing an incident for investigation.

Incident as reported:
{query}

Extracted so far:
  service: {entities.get('service')}
  symptom: {entities.get('symptom')}
  error code: {entities.get('error_code')}
  component: {entities.get('component')}

Applications matched from the report: {applications or 'none'}
Error family matched: {family['means'] if family else 'none'}

The REMAN estate:
{estate_summary()}

Reference for the applications in play:
{digest_for_prompt(applications)}

First decide whether this report is sufficient to investigate.

It is sufficient when it names, or unambiguously implies, one of the estate's
applications AND describes something observable - an error, a failure, a screen
that will not load, a file that will not open.

It is not sufficient when:
- no application in the estate can be identified, or
- the only symptom is contentless: "not working", "is down", "broken",
  "will not open", with no error number, no file name, and no named screen.

"LMS is not working" is NOT sufficient: the application is clear but nothing
observable is described, and every LMS outage in the history looks like this
until someone reads the error off the screen.

If it is not sufficient, list what the reporter would need to add and stop.

If it is sufficient, rewrite it for searching documentation. The rewrite must:
- name the application and its program and program id
- name the data files involved, using the real file names from the reference
- name what is being asked for - the mechanism of the failure, the recovery
  procedure, the operator's steps - in the documents' terms
- keep the reporter's own wording for the symptom alongside the formal terms
- state only what the report and the reference support; invent no file name,
  no error code and no section that is not given above

Where the reference shows a file is opened by more than one application, say so
rather than assuming the reporter's application owns it.

When the reporter is asking how to fix or recover something - not only what
went wrong - the rewrite must also ask for the operator's path: which menu
option and function key reach the screen, what access or security level it
needs, and what the program leaves behind afterwards. Without that, retrieval
returns the program's general error-handling prose and never the screen, because
nothing asked for it: adding the request moves the chunk naming the recovery key
from rank nine to rank five.

Return data_files ONLY for files the report actually names. If the reporter did
not say which file, return an empty list and say so in the rewrite. Listing every
file the application might open is worse than listing none: it is used to scope
the search, and a list of candidates widens it to the whole estate.
"""

    response = structured_llm.invoke(prompt)

    files = [
        canonical_file(name)
        for name in response.data_files
    ]

    # Widening is allowed but has to be earned. An application the report never
    # mentions belongs in the search only when it opens a file the report named
    # - which is the IN0011.MST case, where an LMS outage is recovered from
    # Inventory. Checking the model's list against its own names instead let
    # anything through: a query about inventory corruption came back scoped to
    # Inventory and Reporting, and the Reporting half was noise.
    resolved = list(applications)

    for name in files:

        for application in DATA_FILES.get(name, {}).get("used_by", []):

            if application not in resolved:
                resolved.append(application)

    resolved = resolved or applications

    print(
        f"sufficient={response.is_sufficient} "
        f"applications={resolved} files={files}"
    )

    print(f"reasoning={response.reasoning}")

    if not response.is_sufficient:

        print(f"missing={response.missing_information}")

        return {
            "rewritten_query": None,
            "rewrite_applications": resolved,
            "rewrite_data_files": files,
            "missing_information": response.missing_information,
            "needs_clarification": True
        }

    print(f"rewritten={response.rewritten_query}")

    return {
        "rewritten_query": response.rewritten_query,
        "rewrite_applications": resolved,
        "rewrite_data_files": files,
        "missing_information": [],
        "needs_clarification": False
    }

"""Checks the RCA against the evidence it claims to rest on."""

from typing import List

from pydantic import BaseModel, Field

from src.agents.incident_rca_agent import format_evidence_for_prompt
from src.utils.llm import llm


class IncidentValidationResult(BaseModel):

    is_valid: bool = Field(
        description="Whether the RCA is supported by the cited evidence"
    )

    confidence_score: float = Field(
        description="Confidence in this validation, between 0 and 1"
    )

    issues_found: List[str] = Field(
        description="Unsupported claims, wrong citations, or overreach"
    )

    missing_information: List[str] = Field(
        description="What is still needed for a dependable analysis"
    )

    final_decision: str = Field(
        description="APPROVE or REJECT"
    )


structured_llm = llm.with_structured_output(
    IncidentValidationResult
)


def incident_validation_agent(state):

    print("\n--- Validation Agent ---")

    rca = state.get("rca_result", {})

    catalog = state.get("evidence_catalog", {})

    # The validator must see exactly what the RCA agent saw. Showing it less -
    # the first version omitted record dates - makes it reject correct claims
    # as unsupported simply because the supporting field was withheld from it.
    evidence = format_evidence_for_prompt(
        state.get("combined_evidence", [])
    )

    prompt = f"""
You are reviewing a root cause analysis before it is shown to an engineer.

Incident:
{state["user_query"]}

Proposed RCA:
{rca}

Evidence catalogue the RCA was allowed to use, exactly as it was given to the
RCA agent:
{evidence}

Valid evidence IDs:
{list(catalog.keys())}

Check that:
- every cited evidence_id exists in the catalogue
- every claim in the root cause is supported by the evidence cited for it
- the analysis does not attribute the incident to a code change or deployment
  unless a change record supports it
- resolution steps reflect actions that actually resolved the cited records
- confidence is proportionate; thin evidence stated confidently is a defect
- a service request has not been used to establish a root cause

Judge claims against the whole evidence record shown above, including its
dates, record types and resolution times - not only the narrative text.

Record everything you find in issues_found. Then decide separately:

final_decision is APPROVE unless acting on this analysis would mislead or
endanger the engineer reading it. REJECT only for:
- a cited evidence_id that is not in the list of valid IDs
- a root cause contradicted by the evidence, or resting on a record that does
  not support it
- a resolution step no cited record supports, which could be unsafe to perform
- a root cause established from a service request alone

Everything else is a caveat, not a veto: wording broader than its record, a
confidence score you would have set differently, an unstated assumption, or a
statement that something was not found. Note these in issues_found and still
APPROVE. issues_found is expected to be non-empty on an approved analysis - it
is reviewer commentary that will be shown alongside the RCA.
"""

    response = structured_llm.invoke(
        prompt
    )

    print(response)

    needs_human = (
        response.final_decision.upper() == "REJECT"
    )

    return {
        "validation_result": response.model_dump(),
        "rca_valid": response.is_valid,
        "needs_human_input": needs_human,
        "final_missing_information": response.missing_information
    }

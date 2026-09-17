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


from src.domain.reman_digest import (
    equivalent_symptoms_for_prompt,
    playbooks_for_prompt
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

    # The RCA agent is given these, so the reviewer must be given them too.
    # Without them it saw steps attributed to "Reman support team procedure",
    # could not find that procedure in the catalogue, and rejected the two best
    # analyses in the set for citing a source it had been denied. A reviewer
    # judging against a smaller evidence base than the author is not a stricter
    # reviewer, it is a miscalibrated one.
    playbooks = playbooks_for_prompt(
        state.get("user_query")
    )

    equivalences = equivalent_symptoms_for_prompt()

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

Support-team procedures the RCA agent was also given. These are a legitimate
source for the OPERATOR DETAIL of a resolution step - the menu option, the
function key, the security level, the utility - and a step drawn from one is
supported, provided the analysis says the detail came from the support team
rather than from the documentation. They are NOT evidence that this incident
occurred or what caused it.

{playbooks or "None matched this incident."}

Check that:
- every cited evidence_id exists in the catalogue
- every claim in the root cause is supported by the evidence cited for it
- the analysis does not attribute the incident to a code change or deployment
  unless a change record supports it
- resolution steps reflect actions that actually resolved the cited records
- confidence is proportionate; thin evidence stated confidently is a defect
- a service request has not been used to establish a root cause
- a record cited as the CAUSE matches this incident's symptom, not merely its
  file name, program or application. A record about a different fault that
  happens to name the same file is background, and using it as the cause is a
  defect however well the identifiers line up. Judge that against the groupings
  below, NOT against the wording: a ticket saying "file lock" and one saying
  "invalid file structure" are the same fault, and rejecting an analysis for
  citing one to explain the other is a miscalibration, not a catch.

{equivalences}
- `escalation` matches the analysis. A fault in what a program computes or
  writes cannot be resolved by operator steps and should be 'code_change'; an
  analysis that names no supported cause should not be 'none'.

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

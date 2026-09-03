"""Writes the root cause analysis from ServiceNow evidence alone.

There is no code repository and no knowledge base behind this pipeline, so the
prompt is explicit that the only admissible evidence is historical records. It
must not reason about deployments or code unless a change record says so.
"""

from typing import List

from pydantic import BaseModel, Field

from src.utils.llm import llm


class RCAEvidenceItem(BaseModel):

    statement: str = Field(
        description="A concise evidence statement supporting the RCA"
    )

    evidence_ids: List[str] = Field(
        description="Evidence IDs from the provided catalogue that support this statement"
    )


class IncidentRCAResult(BaseModel):

    root_cause: str = Field(
        description="Most probable root cause, stated plainly, with its uncertainty"
    )

    evidence: List[RCAEvidenceItem] = Field(
        description="Evidence statements paired with the evidence IDs that support them"
    )

    resolution_steps: List[str] = Field(
        description="Ordered steps to resolve, drawn from what previously worked"
    )

    preventive_actions: List[str] = Field(
        description="Actions that would stop this recurring"
    )

    confidence_score: float = Field(
        description="Confidence between 0 and 1"
    )

    requires_more_information: bool = Field(
        description="Whether more information is needed for a dependable RCA"
    )

    missing_information: List[str] = Field(
        description="What would raise confidence, if anything"
    )


structured_llm = llm.with_structured_output(
    IncidentRCAResult
)


def format_evidence_for_prompt(evidence_items):

    blocks = []

    for item in evidence_items:

        metadata = item.get("metadata", {})

        blocks.append(
            {
                "evidence_id": item.get("evidence_id"),
                "record_type": metadata.get("record_type"),
                "title": metadata.get("title"),
                "service": metadata.get("service"),
                "opened_at": metadata.get("opened_at"),
                "resolution_hours": metadata.get("resolution_hours"),
                "content": item.get("content")
            }
        )

    return blocks


def format_recurrence(recurrence):

    if not recurrence or not recurrence.get("repeat_count"):
        return "No repeated cause identified among the matched records."

    return (
        f"The most common cause among the matched records is "
        f"\"{recurrence['dominant_cause']}\", appearing in "
        f"{recurrence['repeat_count']} of them "
        f"({', '.join(recurrence['tickets'])}), "
        f"between {recurrence.get('first_seen')} and {recurrence.get('last_seen')}."
    )


def incident_rca_agent(state):

    print("\n--- RCA Agent ---")

    evidence = format_evidence_for_prompt(
        state.get("combined_evidence", [])
    )

    changes = state.get("related_changes", []) or "None found."

    prompt = f"""
You are a senior production support engineer writing a root cause analysis.

Incident:
{state["user_query"]}

Evidence catalogue (historical ServiceNow records):
{evidence}

Recurrence:
{format_recurrence(state.get("recurrence"))}

Change records touching the same programs or jobs:
{changes}

Assessment of the retrieved records:
{state.get("servicenow_analysis")}

Write the analysis under these rules:

- Use ONLY the evidence above. There is no code repository and no knowledge
  base available for this incident.
- Do not attribute the incident to a deployment or code change unless one of
  the change records above supports it. A change record that merely touches the
  same program is a possible link, not a cause - say so in those words.
- Every evidence statement must cite one or more evidence_id values from the
  catalogue. Never cite an evidence_id that is not listed.
- Draw resolution steps from the actions that actually resolved the matched
  records, and say which record each step comes from.
- When the matched records show a repeating cause, say so plainly and treat the
  recurrence itself as a finding: a fault seen many times needs a permanent fix,
  not another restart.
- Service requests record that a symptom occurred. They do not establish a
  cause. Do not lean on them for the root cause.
- If the evidence is thin, say so and lower the confidence rather than filling
  the gap with a plausible-sounding explanation.
"""

    response = structured_llm.invoke(
        prompt
    )

    print(response)

    return {
        "rca_result": response.model_dump()
    }

"""Decides which retrieved ServiceNow records genuinely bear on the incident.

Record types carry very different weight, and the prompt says so explicitly:
incidents carry an investigated root cause, service requests are mostly a record
that a symptom occurred, and changes say what was deliberately altered.
"""

from typing import List

from pydantic import BaseModel, Field

from src.utils.llm import llm


class RecordEvaluation(BaseModel):

    confidence_score: float = Field(
        description="Confidence between 0 and 1 that these records explain the incident"
    )

    matching_records: List[str] = Field(
        description=(
            "Ticket numbers that genuinely relate to this incident. "
            "Include a record only when the affected system matches AND the "
            "symptom, failure mode or named component matches. Do not include a "
            "record merely because it concerns the same system."
        )
    )

    reasoning: str = Field(
        description="Why these records are or are not useful for this incident"
    )

    enough_information: bool = Field(
        description="Whether these records support a root cause analysis"
    )


structured_llm = llm.with_structured_output(
    RecordEvaluation
)


def compact_records(records):
    """Only the fields the evaluator reasons over.

    The stored note text is largely an effort-tracking template, so the
    extracted root cause and action are passed instead of the raw notes.
    """

    compacted = []

    for record in records:

        compacted.append(
            {
                "ticket_id": record.get("ticket_id"),
                "record_type": record.get("record_type"),
                "similarity_score": round(
                    record.get("score") or 0.0,
                    4
                ),
                "service": record.get("service"),
                "priority": record.get("priority"),
                "reported_problem": record.get("short_description"),
                "details": record.get("description"),
                "root_cause": record.get("root_cause") or None,
                "action_taken": record.get("action_taken") or None,
                "error_codes": record.get("error_codes") or [],
                "programs": record.get("programs") or []
            }
        )

    return compacted


def incident_evaluator_agent(state):

    print("\n--- ServiceNow Record Evaluator ---")

    records = compact_records(
        state.get("servicenow_results", [])
    )

    prompt = f"""
You are a senior production support engineer.

Decide which of these historical ServiceNow records genuinely relate to the
incident being investigated, and whether they are enough to explain it.

Incident being investigated:
{state["user_query"]}

Retrieved ServiceNow records:
{records}

How to weigh each record type:
- incident: has an investigated root cause and the action that resolved it.
  This is the strongest evidence.
- service_request: a user-reported symptom. Useful for confirming that a
  symptom recurs and how users describe it, but its notes are often only an
  acknowledgement and rarely explain a cause. Never treat one as proof of a
  root cause.
- change: what was deliberately changed and when. Useful only when it touches
  the same program, job or system as the incident.

Include a record in matching_records only when the affected system matches AND
the symptom, failure mode, or a named job, program or file matches. A shared
system alone is not a match.

Confidence:
- above 0.75: several records share the failure mode and at least one incident
  records a root cause that plausibly explains this one
- 0.4 to 0.75: related records exist but the cause is partial or uncertain
- below 0.4: nothing retrieved genuinely matches

Set enough_information to true only when at least one matching incident carries
a root cause that could explain the reported problem. Symptom-only matches, or
matches consisting solely of service requests, are not enough.
"""

    response = structured_llm.invoke(
        prompt
    )

    print(response)

    return {
        "matching_records": response.matching_records,
        "servicenow_confidence": response.confidence_score,
        "servicenow_analysis": response.reasoning,
        "enough_information": response.enough_information
    }

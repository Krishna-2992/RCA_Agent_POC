"""Writes the root cause analysis from the assembled evidence.

Two kinds of evidence reach this agent and they are not interchangeable.
ServiceNow records say what happened and what fixed it. REMAN documentation,
generated from the COBOL source, says how a program works and how it fails by
design - it is evidence of mechanism, never of an event. The prompt draws that
line explicitly, because the failure mode it guards against is a confident root
cause synthesised from a design document with no incident behind it.

There is still no code repository behind this pipeline, so deployments and code
changes remain off-limits unless a change record says otherwise.
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

        block = {
            "evidence_id": item.get("evidence_id"),
            "evidence_kind": (
                "documentation"
                if item.get("source_type") == "reman_documentation"
                else "servicenow_record"
            ),
            "title": metadata.get("title"),
            "content": item.get("content")
        }

        if item.get("source_type") == "reman_documentation":

            block.update(
                {
                    "program": metadata.get("program"),
                    "application": metadata.get("application"),
                    "document_type": metadata.get("document_type"),
                    "describes": "how the software works, not what happened"
                }
            )

        else:

            block.update(
                {
                    "record_type": metadata.get("record_type"),
                    "service": metadata.get("service"),
                    "opened_at": metadata.get("opened_at"),
                    "resolution_hours": metadata.get("resolution_hours")
                }
            )

        blocks.append(block)

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

Evidence catalogue:
{evidence}

Each item is one of two kinds. `servicenow_record` is a historical ticket: what
happened, and what resolved it. `documentation` is an extract generated from
the REMAN COBOL source: what a program does, what a data file holds, how a
failure is handled or recovered.

Recurrence:
{format_recurrence(state.get("recurrence"))}

Change records touching the same programs or jobs:
{changes}

Assessment of the retrieved records:
{state.get("servicenow_analysis")}

Assessment of the retrieved documentation:
{state.get("docs_analysis") or "Documentation was not consulted for this incident."}

Write the analysis under these rules:

- Use ONLY the evidence above. There is no code repository available for this
  incident.
- The two kinds of evidence do different jobs, and the difference matters more
  than any other rule here. A `servicenow_record` can establish what happened
  and what caused it. A `documentation` item can only explain a mechanism: what
  a file holds, which programs read it, how a failure of that kind is handled
  or repaired. Never state or imply that a documentation item shows this
  incident occurred, or that it establishes the cause.
- Where documentation is the only evidence for the cause, say plainly that the
  cause is not established by the record, give the mechanism as the likely
  explanation, and keep the confidence below 0.4.
- Documentation is at its most useful for explaining a cause the records
  already show, for naming the affected data, and for supplying a recovery
  procedure. Use it that way.
- Do not attribute the incident to a deployment or code change unless one of
  the change records above supports it. A change record that merely touches the
  same program is a possible link, not a cause - say so in those words.
- Every evidence statement must cite one or more evidence_id values from the
  catalogue. Never cite an evidence_id that is not listed.
- Draw resolution steps from the actions that actually resolved the matched
  records, and say which record each step comes from. A documented recovery
  procedure may be offered as a step only when it is labelled as coming from
  documentation rather than from a past fix.
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

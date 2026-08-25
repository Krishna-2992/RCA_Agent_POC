from pydantic import BaseModel, Field
from typing import List

from src.utils.llm import llm


class IncidentEvaluation(BaseModel):

    confidence_score: float = Field(
        description="Overall confidence between 0 and 1"
    )

    matching_incidents: List[str] = Field(
        description="""
Only strongly relevant incident IDs.

Include incidents only if:
- same application
AND
- similar symptom/failure

Do not include incidents merely because application matches.
    """
    )

    reasoning: str = Field(
        description="Why these incidents are useful or not"
    )

    enough_information: bool = Field(
        description="Can RCA be generated only using ServiceNow?"
    )


structured_llm = llm.with_structured_output(
    IncidentEvaluation
)


def compact_incidents(incidents):
    """Projects retrieved incidents down to the fields the evaluator reasons over.

    The stored `content` field restates issue_description, resolution_notes,
    product and category in prose, so passing the raw record made roughly three
    quarters of this prompt a repeat of the other keys.
    """

    compacted = []

    for incident in incidents:

        compacted.append(
            {
                "ticket_id": incident.get(
                    "ticket_id"
                ),
                "similarity_score": round(
                    incident.get("score") or 0.0,
                    4
                ),
                "product": incident.get(
                    "product"
                ),
                "category": incident.get(
                    "category"
                ),
                "priority": incident.get(
                    "priority"
                ),
                "issue_description": incident.get(
                    "issue_description"
                ) or incident.get("content"),
                "resolution_notes": incident.get(
                    "resolution_notes"
                )
            }
        )

    return compacted


def servicenow_evaluator_agent(state):

    print(
        "\n--- ServiceNow Evaluation Agent ---"
    )


    query = state["user_query"]

    incidents = compact_incidents(
        state["servicenow_results"]
    )


    prompt = f"""

You are a senior production support engineer.

Your task:

Determine whether retrieved historical ServiceNow incidents
are enough to perform Root Cause Analysis.


Current Incident:

{query}


Retrieved Historical Incidents:

{incidents}



Evaluate based on:

1. Same application/service
2. Similar symptoms
3. Similar failure pattern
4. Useful resolution information


Rules:

High confidence (>0.75):
- Same service
- Same symptoms
- Clear previous resolution


Medium confidence (0.4-0.75):
- Same service
- Partial symptom match


Low confidence (<0.4):
- Different problem
- Generic resolution


Return whether RCA can continue using only ServiceNow.

IMPORTANT:

For matching_incidents:

Do NOT include incidents only because service name matches.

Example:

Current:
Payment Gateway timeout

Historical:
Payment Gateway authentication failure

Result:
NOT MATCHING


Only include incidents with similar failure behavior.

"""


    response = structured_llm.invoke(
        prompt
    )


    print(
        response
    )


    return {

        "servicenow_confidence":
            response.confidence_score,

        "servicenow_analysis":
            response.reasoning,

        "matching_incidents":
            response.matching_incidents,

        "need_kb":
            not response.enough_information

    }
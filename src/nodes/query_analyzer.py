from typing import Optional
from pydantic import BaseModel, Field

from src.utils.llm import llm


class QueryUnderstanding(BaseModel):

    service: Optional[str] = Field(
        description="Affected application/service"
    )

    symptom: Optional[str] = Field(
        description="Observed failure symptom"
    )

    category: Optional[str] = Field(
        description="High level incident category"
    )

    priority: Optional[str] = Field(
        description="Incident priority if mentioned"
    )

    deployment_related: bool = Field(
        description="Whether deployment/change is suspected"
    )

    missing_critical_information: list[str] = Field(
        description="Only information without which investigation cannot start"
    )


structured_llm = llm.with_structured_output(
    QueryUnderstanding
)


def query_analyzer_node(state):

    print("\n--- Query Analyzer Node ---")

    prompt = f"""
You are an SRE triage agent.

Your job is ONLY to decide whether RCA investigation can begin.

Incident:
{state["user_query"]}


Extract:
- affected service/application
- symptoms
- category
- priority
- deployment relation


IMPORTANT:

Do NOT request:
- logs
- metrics
- timestamps
- deployment details
- previous incidents
- impact percentage
- PII data

These are investigation artifacts and will be collected later.

A symptom must describe an observable failure.

Valid symptoms:
- timeout errors
- login failures
- API returning HTTP 500
- slow response time
- transactions failing

Invalid symptoms:
- not working
- broken
- issue happening
- problem exists

If symptom is generic, mark symptom as missing.

Only add missing critical information if:

1. The affected service/application is unknown.

OR

2. No failure symptom is provided.


Examples:

Input:
"Payment Gateway timeout errors"

missing_critical_information:
[]


Input:
"Something is broken"

missing_critical_information:
[
"affected service",
"specific symptom"
]

"""


    response = structured_llm.invoke(
        prompt
    )


    data = response.model_dump()


    return {

        "extracted_entities": data,

        "missing_information":
            data["missing_critical_information"],

        "needs_clarification":
            len(
                data["missing_critical_information"]
            ) > 0
    }
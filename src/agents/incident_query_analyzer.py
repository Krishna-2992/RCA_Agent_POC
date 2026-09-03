"""Reads the incident description before anything is searched.

Tuned to mainframe and application-support incidents: what matters here is the
service, the observed failure, and any abend code, job or program named. The
payment-gateway pipeline's analyser asks whether a deployment is suspected,
which is not a useful question against this data.
"""

from typing import Optional

from pydantic import BaseModel, Field

from src.utils.llm import llm


class IncidentUnderstanding(BaseModel):

    service: Optional[str] = Field(
        description="Affected application, system or service"
    )

    symptom: Optional[str] = Field(
        description="Observed failure behaviour, in the reporter's terms"
    )

    error_code: Optional[str] = Field(
        description="Abend or error code if one is mentioned, e.g. S0C7, U4005, AJS002E"
    )

    component: Optional[str] = Field(
        description="Job, program or file named, e.g. F8RH0920, IN001.MST"
    )

    missing_critical_information: list[str] = Field(
        description=(
            "Only information without which a search cannot start. "
            "An incident naming a system and a symptom is enough; do not ask "
            "for error codes, timestamps or ticket numbers as a matter of course."
        )
    )


structured_llm = llm.with_structured_output(
    IncidentUnderstanding
)


def incident_query_analyzer_node(state):

    print("\n--- Incident Query Analyzer ---")

    prompt = f"""
You are a production support engineer triaging an incident report.

Incident as reported:
{state["user_query"]}

Extract what is stated. Do not infer a service or a cause that is not there.

The systems in scope are mainframe and application-support systems such as a
job scheduler, an inventory/material system and a warehouse management system.
Failures are typically batch job abends, corrupted or locked data files, missing
upstream files, or users unable to use an application.

Treat the report as sufficient when it names, or clearly implies, both an
affected system or component and an observed problem. Only list missing
information when the report is so vague that no search could begin - for
example "something is broken" or "it is not working".

Do not ask for an LPAR, a job name, a date and time, a ticket number, a user
name or an error code when the report already says what failed and where. A
search runs on the symptom, and asking a reporter for details they are unlikely
to know wastes their time.
"""

    response = structured_llm.invoke(
        prompt
    )

    entities = response.model_dump()

    missing = response.missing_critical_information or []

    # The model asks for more detail more readily than is warranted - an abend
    # code and an affected system are plenty to search on. Searching is cheap
    # and the evaluator is the real gate: if nothing matches, the workflow comes
    # back for clarification anyway. So only genuinely contentless reports stop
    # here, whatever the model listed as missing.
    has_target = bool(
        entities.get("service")
        or entities.get("component")
    )

    has_problem = bool(
        entities.get("symptom")
        or entities.get("error_code")
    )

    if has_target and has_problem:
        missing = []

    print(
        f"service={entities.get('service')} symptom={entities.get('symptom')} "
        f"code={entities.get('error_code')} component={entities.get('component')} "
        f"missing={missing}"
    )

    return {
        "extracted_entities": entities,
        "missing_information": missing,
        "needs_clarification": bool(missing)
    }

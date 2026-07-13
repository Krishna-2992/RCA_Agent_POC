from typing import List

from pydantic import BaseModel, Field

from src.utils.llm import llm



class RCAResult(BaseModel):

    root_cause: str = Field(
        description="Most probable technical root cause"
    )


    evidence: List[str] = Field(
        description="Evidence supporting the RCA"
    )


    resolution_steps: List[str] = Field(
        description="Immediate actions to fix the issue"
    )


    preventive_actions: List[str] = Field(
        description="Long term preventive improvements"
    )


    confidence_score: float = Field(
        description="RCA confidence between 0 and 1"
    )


    requires_more_information: bool = Field(
        description="Whether more user information is required"
    )


    missing_information: List[str] = Field(
        description="Additional information required if RCA is incomplete"
    )



structured_llm = llm.with_structured_output(
    RCAResult
)



def rca_agent(state):


    print(
        "\n--- RCA Agent ---"
    )


    query = state["user_query"]


    evidence = state.get(
        "combined_evidence",
        []
    )


    prompt = f"""

You are a senior production incident RCA engineer.

Generate a Root Cause Analysis.

Current Production Incident:

{query}


Available Evidence:

{evidence}



Your task:

Identify:

1. Most probable root cause

2. Evidence supporting the conclusion

3. Immediate recovery steps

4. Long-term preventive actions



Important rules:

- Use ONLY provided evidence
- Do not invent systems/components
- Mention uncertainty if evidence is incomplete
- Prefer specific technical causes over generic answers
- Correlate historical incidents, KB documents,
  and GitHub changes when available


Output should be suitable for a production incident report.

"""


    response = structured_llm.invoke(
        prompt
    )


    print(
        response
    )


    return {

        "rca_result": response.model_dump()

    }

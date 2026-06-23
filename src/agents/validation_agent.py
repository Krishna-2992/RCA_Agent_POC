from typing import List

from pydantic import BaseModel, Field

from src.utils.llm import llm


class ValidationResult(BaseModel):

    is_valid: bool = Field(
        description="Whether RCA is reliable"
    )

    confidence_score: float = Field(
        description="Validation confidence between 0 and 1"
    )

    issues_found: List[str] = Field(
        description="Problems found in RCA"
    )

    missing_information: List[str] = Field(
        description="Information required from user"
    )

    final_decision: str = Field(
        description="APPROVE or NEED_MORE_INFO"
    )


structured_llm = llm.with_structured_output(
    ValidationResult
)


def validation_agent(state):

    print(
        "\n--- Validation Agent ---"
    )


    rca = state.get(
        "rca_result"
    )


    evidence = state.get(
        "combined_evidence",
        []
    )


    query = state[
        "user_query"
    ]


    prompt = f"""

You are an RCA quality reviewer.

Your job is to verify whether the RCA is trustworthy.


Original Incident:

{query}


Available Evidence:

{evidence}


Generated RCA:

{rca}



Validate:


1. Is root cause supported by evidence?

2. Are resolution steps derived from evidence?

3. Are there hallucinated facts?

4. Is confidence justified?

5. Is additional information required?



Rules:

- Be strict.
- Do not approve unsupported RCA.
- Missing logs/metrics are acceptable if RCA evidence is strong.
- Reject RCA if root cause is guessed.


Return APPROVE only when RCA is production ready.

"""


    response = structured_llm.invoke(
        prompt
    )


    print(
        response
    )


    return {

        "validation_result":
            response.model_dump(),

        "rca_valid":
            response.is_valid,

        "needs_human_input":
            response.final_decision
            ==
            "NEED_MORE_INFO",

        "final_missing_information":
            response.missing_information

    }
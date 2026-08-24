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


1. Is the root cause supported by the evidence actually available?

2. Are resolution steps derived from that evidence?

3. Are there hallucinated facts that contradict the evidence?



Decision rule:


Distinguish between two very different problems:


(a) UNSUPPORTED - the RCA asserts something the evidence does not
    show, contradicts the evidence, or guesses at a cause.
    This is a real defect. Reject it.

(b) UNCORROBORATED - the RCA is well supported by the evidence
    available, but cannot be cross-checked against sources this
    system does not have access to, such as production logs,
    metrics, traces, deployment manifests, or runtime environment
    configuration.
    This is NOT a defect. It is the expected condition of this
    system, which only has ServiceNow, SharePoint KB, and GitHub.


Return NEED_MORE_INFO only for case (a).


Never return NEED_MORE_INFO merely because:

- production logs, metrics, or traces are unavailable
- deployment or release manifests are unavailable
- runtime configuration or environment overrides cannot be read
- the confidence score seems slightly high or low
- the conclusion is conditional on a documented default value


If the code-level evidence establishes a coherent, specific
mechanism that explains the reported symptom, return APPROVE.


Record any residual caveats in issues_found so they stay visible
to the engineer, but do not let caveats alone block approval.

Populate missing_information with what would strengthen the RCA
further, regardless of the decision.

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

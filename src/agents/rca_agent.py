from typing import List

from pydantic import BaseModel, Field

from src.utils.llm import llm


class RCAEvidenceItem(BaseModel):

    statement: str = Field(
        description="A concise evidence statement supporting the RCA"
    )

    evidence_ids: List[str] = Field(
        description="Evidence IDs from the provided evidence catalog that support this statement"
    )


class RCAResult(BaseModel):

    root_cause: str = Field(
        description="Most probable technical root cause"
    )

    evidence: List[RCAEvidenceItem] = Field(
        description="Evidence statements paired with supporting evidence IDs"
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


def format_evidence_for_prompt(evidence_items):

    prompt_blocks = []

    for item in evidence_items:
        metadata = item.get(
            "metadata",
            {}
        )

        prompt_blocks.append(
            {
                "evidence_id": item.get(
                    "evidence_id"
                ),
                "source_type": item.get(
                    "source_type"
                ),
                "confidence": item.get(
                    "confidence"
                ),
                "title": metadata.get("title"),
                "location": metadata.get(
                    "location"
                ),
                "content": item.get("content"),
                "metadata": metadata
            }
        )

    return prompt_blocks


def rca_agent(state):

    print(
        "\n--- RCA Agent ---"
    )

    query = state["user_query"]

    evidence = format_evidence_for_prompt(
        state.get(
            "combined_evidence",
            []
        )
    )

    prompt = f"""

You are a senior production incident RCA engineer.

Generate a Root Cause Analysis.

Current Production Incident:

{query}


Available Evidence Catalog:

{evidence}


Your task:

Identify:

1. Most probable root cause
2. Evidence supporting the conclusion, using the exact evidence_id values from the catalog
3. Immediate recovery steps
4. Long-term preventive actions


Important rules:

- Use ONLY provided evidence
- Do not invent systems/components
- Mention uncertainty if evidence is incomplete
- Prefer specific technical causes over generic answers
- Correlate historical incidents, KB documents, and GitHub changes when available
- Every evidence statement must cite one or more evidence_ids from the evidence catalog
- Never cite an evidence_id that is not present in the catalog


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

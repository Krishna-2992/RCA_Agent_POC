from typing import List

from pydantic import BaseModel, Field

from src.utils.llm import llm


class RelevantChunk(BaseModel):

    chunk_id: str = Field(
        description=
        "Unique chunk identifier"
    )

    relevance_reason: str

    relevance_reason: str = Field(
        description="Why this document helps RCA"
    )


class KBEvaluation(BaseModel):

    relevant_chunks: List[RelevantChunk] = Field(
        description="Only KB documents relevant for RCA"
    )

    reasoning: str = Field(
        description="Overall evaluation reasoning"
    )


structured_llm = llm.with_structured_output(
    KBEvaluation
)


def kb_evaluator_agent(state):

    print(
        "\n--- KB Evaluation Agent ---"
    )


    query = state["user_query"]

    documents = state.get(
        "kb_results",
        []
    )


    prompt = f"""

You are a senior SRE engineer.

Your task:

Filter retrieved knowledge base documents before RCA generation.

Current Incident:

{query}


Retrieved KB Documents:

{documents}


Select ONLY documents that help identify:

- probable root cause
- failure pattern
- troubleshooting steps
- resolution procedure
- preventive actions


Rules:

Relevant:
- same application/service
- same failure symptom
- same technical failure pattern
- useful troubleshooting information


Not Relevant:
- same company/application but unrelated issue
- generic operational information
- unrelated SOPs


Return only strongly useful documents.

"""


    response = structured_llm.invoke(
        prompt
    )


    relevant_chunks = {
        doc.chunk_id
        for doc in response.relevant_chunks
    }


    filtered_docs = []


    for doc in documents:

        if doc["chunk_id"] in relevant_chunks:

            filtered_docs.append(
                doc
            )


    print(
        f"Filtered KB docs: {len(filtered_docs)}"
    )


    return {

        "filtered_kb_results":
            filtered_docs,

        "kb_evaluation_reasoning":
            response.reasoning

    }
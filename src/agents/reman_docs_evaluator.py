"""Decides which retrieved documentation genuinely explains the incident.

The distinction this agent has to hold is the whole reason documentation is
kept in a separate collection from ticket history: these documents describe how
the REMAN programs are built and how they fail by design. They are evidence of
mechanism, never evidence that a particular failure occurred. A document can
say that a corrupted index file is repaired by RECOVER1.EXE; it cannot say that
a file was corrupted last night.

So `enough_information` here does not mean "the cause is established". It means
"these documents explain the failure well enough to be worth citing".
"""

from typing import List

from pydantic import BaseModel, Field

from src.utils.llm import llm


class DocumentEvaluation(BaseModel):

    confidence_score: float = Field(
        description=(
            "Confidence between 0 and 1 that these documents explain the "
            "mechanism behind the incident"
        )
    )

    matching_documents: List[str] = Field(
        description=(
            "chunk_id values that genuinely bear on this incident. Include one "
            "only when it describes the affected program, a named file, or the "
            "failure mode itself. Do not include a chunk merely because it "
            "concerns REMAN."
        )
    )

    reasoning: str = Field(
        description="What these documents do and do not explain about this incident"
    )

    enough_information: bool = Field(
        description=(
            "Whether these documents add a real explanation of the failure "
            "mechanism, recovery procedure or affected data"
        )
    )


structured_llm = llm.with_structured_output(
    DocumentEvaluation
)


def compact_documents(documents):

    compacted = []

    for document in documents:

        compacted.append(
            {
                "chunk_id": document.get("chunk_id"),
                "program": document.get("program"),
                "program_id": document.get("program_id"),
                "application": document.get("application"),
                "source_type": document.get("source_type"),
                "section": document.get("section"),
                "similarity_score": round(
                    document.get("score") or 0.0,
                    4
                ),
                "data_files": document.get("data_files") or [],
                "content": document.get("content")
            }
        )

    return compacted


def reman_docs_evaluator_agent(state):

    print("\n--- REMAN Documentation Evaluator ---")

    documents = compact_documents(
        state.get("docs_results", [])
    )

    if not documents:

        reason = (
            "The documentation search could not be reached."
            if state.get("docs_unavailable")
            else "No documentation matched this incident."
        )

        print(reason)

        return {
            "matching_documents": [],
            "docs_confidence": 0.0,
            "docs_analysis": reason,
            "docs_enough_information": False
        }

    prompt = f"""
You are a senior production support engineer for the REMAN applications.

The ticket history did not explain this incident on its own. Decide which of
these REMAN documentation extracts genuinely help explain it.

Incident being investigated:
{state["user_query"]}

What the ticket history showed:
{state.get("servicenow_analysis") or "No useful historical records were found."}

Retrieved documentation extracts:
{documents}

What these documents are:
They were generated from the REMAN COBOL source code. They describe what each
program does, which data files it reads and writes, how it handles errors, and
what its known operational risks are. The support team supports three
applications: Reman Index (security and sign-on), Inventory, and LMS
(warehouse locations).

How to weigh each source_type:
- program_summary_docx: written by engineers, includes error handling, recovery
  procedures and operational risks. The most useful.
- technical_xml: the program's file inventory and decision logic. Best for
  "what is this file" and "what reads it".
- business_rule: a single Given/When/Then statement of behaviour. Useful only
  when it names the failure or validation at issue.
- estate_catalogue: one sentence about a program elsewhere in the estate. Only
  useful for identifying an unfamiliar program.
- program_overview / general_doc: background context.

Include a chunk_id in matching_documents only when the extract describes the
affected program, a data file named in the incident, or the specific failure
mode. Sharing the REMAN system alone is not a match.

Critical boundary:
These documents describe how the software is built and how it fails by design.
They are NOT a record of events. Never treat a document as evidence that this
particular failure occurred, or as proof of what caused it. Judge only whether
they explain the mechanism.

Confidence:
- above 0.75: the documents describe the affected file or program and the way
  this kind of failure arises or is recovered
- 0.4 to 0.75: relevant background on the right system, but not the specific
  failure
- below 0.4: nothing retrieved genuinely bears on this incident

Set enough_information to true only when the documents add a real explanation
of the mechanism, the affected data, or the recovery procedure.
"""

    response = structured_llm.invoke(
        prompt
    )

    print(response)

    return {
        "matching_documents": response.matching_documents,
        "docs_confidence": response.confidence_score,
        "docs_analysis": response.reasoning,
        "docs_enough_information": response.enough_information
    }

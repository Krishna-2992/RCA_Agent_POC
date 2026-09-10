from typing import Any, Dict, List, TypedDict


class IncidentRCAState(TypedDict):
    """State for the incident workflow.

    Two evidence sources, consulted in order. ServiceNow history establishes
    what happened and what fixed it; the REMAN documentation explains the
    mechanism behind it, and is reached only when history alone falls short.
    There is no code repository behind this pipeline, so that stage is absent
    rather than stubbed out.
    """

    # user input
    user_query: str

    # query understanding
    extracted_entities: Dict[str, Any]

    missing_information: List[str]

    needs_clarification: bool

    # the incident restated in the documentation's vocabulary, and what the
    # digest resolved while doing it
    rewritten_query: str

    rewrite_applications: List[str]

    rewrite_data_files: List[str]

    # set when the reporter overrode the rewrite by hand, which stops the
    # rewriter replacing their wording on the next pass
    rewrite_locked: bool

    # retrieval
    search_identifiers: Dict[str, List[str]]

    servicenow_results: List[Dict[str, Any]]

    # evaluation
    matching_records: List[str]

    servicenow_confidence: float

    servicenow_analysis: str

    enough_information: bool

    # documentation retrieval, reached only when history is not enough
    docs_identifiers: Dict[str, List[str]]

    docs_applications: List[str]

    docs_results: List[Dict[str, Any]]

    matching_documents: List[str]

    docs_confidence: float

    docs_analysis: str

    docs_enough_information: bool

    docs_unavailable: bool

    # evidence
    recurrence: Dict[str, Any]

    related_changes: List[Dict[str, Any]]

    combined_evidence: List[Dict[str, Any]]

    evidence_catalog: Dict[str, Dict[str, Any]]

    # output
    rca_result: Dict[str, Any]

    validation_result: Dict[str, Any]

    rca_valid: bool

    needs_human_input: bool

    final_missing_information: List[str]

    clarification_questions: List[str]

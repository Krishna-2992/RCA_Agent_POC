from typing import Any, Dict, List, TypedDict


class IncidentRCAState(TypedDict):
    """State for the ServiceNow-only workflow.

    Deliberately smaller than RCAState: there is no knowledge base and no code
    repository in this pipeline, so every field here is about ServiceNow records.
    """

    # user input
    user_query: str

    # query understanding
    extracted_entities: Dict[str, Any]

    missing_information: List[str]

    needs_clarification: bool

    # retrieval
    search_identifiers: Dict[str, List[str]]

    servicenow_results: List[Dict[str, Any]]

    # evaluation
    matching_records: List[str]

    servicenow_confidence: float

    servicenow_analysis: str

    enough_information: bool

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

from typing import TypedDict, List, Dict, Any


class RCAState(TypedDict):

    # user input
    user_query: str


    # query understanding
    extracted_entities: Dict[str, Any]

    missing_information: List[str]

    needs_clarification: bool


    # ServiceNow

    servicenow_results: List[Dict[str, Any]]

    servicenow_confidence: float

    servicenow_analysis: str

    matching_incidents: List[str]

    need_kb: bool


    # Knowledge Base

    kb_results: List[Dict[str, Any]]

    filtered_kb_results: List[Dict[str, Any]]

    kb_evaluation_reasoning: str


    # GitHub

    need_github: bool

    github_decision_reasoning: str

    github_results: List[Dict[str, Any]]

    filtered_github_results: List[Dict[str, Any]]

    github_analysis: str


    # Evidence

    combined_evidence: List[Dict[str, Any]]

    evidence_catalog: Dict[str, Dict[str, Any]]


    # RCA

    rca_result: Dict[str, Any]


    # Validation

    validation_result: Dict[str, Any]

    rca_valid: bool

    needs_human_input: bool

    final_missing_information: List[str]


    # final output

    final_response: str

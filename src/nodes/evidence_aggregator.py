def build_servicenow_evidence(incident):

    evidence_id = f"sn::{incident['ticket_id']}"

    content = (
        "Issue Description:\n"
        f"{incident.get('issue_description') or incident.get('content')}\n\n"
        "Resolution Notes:\n"
        f"{incident.get('resolution_notes') or 'Not Available'}"
    )

    metadata = {
        "title": incident.get(
            "source_title"
        ) or f"ServiceNow Incident {incident['ticket_id']}",
        "location": incident.get(
            "source_location"
        ) or f"ServiceNow incident {incident['ticket_id']}",
        "source_type_label": incident.get(
            "source_type_label"
        ) or "ServiceNow Incident",
        "ticket_id": incident.get(
            "ticket_id"
        ),
        "product": incident.get(
            "product"
        ),
        "category": incident.get(
            "category"
        ),
        "priority": incident.get(
            "priority"
        ),
        "region": incident.get(
            "region"
        ),
        "excerpt": incident.get(
            "issue_description"
        ) or incident.get("content"),
        "resolution_notes": incident.get(
            "resolution_notes"
        )
    }

    return {
        "evidence_id": evidence_id,
        "source_type": "servicenow",
        "source_id": incident["ticket_id"],
        "confidence": incident["score"],
        "content": content,
        "metadata": metadata
    }


def build_kb_evidence(document):

    evidence_id = f"kb::{document['chunk_id']}"

    metadata = {
        "title": document.get(
            "source_title"
        ) or document.get("document_name"),
        "location": document.get(
            "source_location"
        ) or (
            f"{document.get('document_name')} - page {document.get('page')}"
        ),
        "source_type_label": document.get(
            "source_type_label"
        ) or "SharePoint Document",
        "document_name": document.get(
            "document_name"
        ),
        "document_path": document.get(
            "document_path"
        ),
        "page": document.get("page"),
        "service": document.get(
            "service"
        ),
        "document_type": document.get(
            "document_type"
        ),
        "chunk_id": document.get(
            "chunk_id"
        ),
        "excerpt": document.get("content")
    }

    return {
        "evidence_id": evidence_id,
        "source_type": "knowledge_base",
        "source_id": document["document_name"],
        "confidence": document["score"],
        "content": document["content"],
        "metadata": metadata
    }


def build_github_evidence(artifact):

    evidence_id = f"github::{artifact['artifact_id']}"
    references = artifact.get(
        "references",
        []
    )

    reference_summaries = []

    for reference in references:
        path = reference.get("path")
        start_line = reference.get(
            "start_line"
        )
        end_line = reference.get(
            "end_line"
        )

        if path and start_line and end_line:
            location = f"{path}:{start_line}-{end_line}"
        elif path and start_line:
            location = f"{path}:{start_line}"
        else:
            location = path or reference.get(
                "title"
            ) or "GitHub reference"

        reference_summaries.append(
            {
                "type": reference.get(
                    "reference_type"
                ),
                "location": location,
                "evidence": reference.get(
                    "evidence"
                ),
                "title": reference.get("title"),
                "commit_sha": reference.get(
                    "commit_sha"
                ),
                "pull_request": reference.get(
                    "pull_request"
                )
            }
        )

    metadata = {
        "title": f"GitHub Investigation - {artifact.get('repo')}",
        "location": artifact.get("repo"),
        "source_type_label": "GitHub Repository",
        "repo": artifact.get("repo"),
        "summary": artifact.get(
            "summary"
        ),
        "root_cause": artifact.get(
            "root_cause"
        ),
        "confidence_label": artifact.get(
            "confidence_label"
        ),
        "limitations": artifact.get(
            "limitations"
        ),
        "references": reference_summaries,
        "excerpt": artifact.get("summary")
    }

    return {
        "evidence_id": evidence_id,
        "source_type": "github",
        "source_id": artifact["artifact_id"],
        "confidence": 0.8,
        "content": artifact.get("summary"),
        "metadata": metadata
    }


def evidence_aggregator_node(state):

    print("\n--- Evidence Aggregator Node ---")

    evidence = []
    evidence_catalog = {}

    matching_ids = state.get(
        "matching_incidents",
        []
    )

    for incident in state.get(
        "servicenow_results",
        []
    ):

        if incident["ticket_id"] not in matching_ids:
            continue

        item = build_servicenow_evidence(
            incident
        )
        evidence.append(item)
        evidence_catalog[item["evidence_id"]] = item

    for document in state.get(
        "filtered_kb_results",
        []
    ):

        item = build_kb_evidence(
            document
        )
        evidence.append(item)
        evidence_catalog[item["evidence_id"]] = item

    for artifact in state.get(
        "filtered_github_results",
        []
    ):

        item = build_github_evidence(
            artifact
        )
        evidence.append(item)
        evidence_catalog[item["evidence_id"]] = item

    print(
        f"Prepared {len(evidence)} evidence items"
    )

    return {
        "combined_evidence": evidence,
        "evidence_catalog": evidence_catalog
    }

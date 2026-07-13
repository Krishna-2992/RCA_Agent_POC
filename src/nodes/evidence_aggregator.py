def evidence_aggregator_node(state):

    print("\n--- Evidence Aggregator Node ---")

    evidence = []


    # -----------------------------
    # ServiceNow Evidence
    # -----------------------------

    matching_ids = state.get(
        "matching_incidents",
        []
    )


    for incident in state.get(
        "servicenow_results",
        []
    ):


        if incident["ticket_id"] in matching_ids:


            evidence.append(

                {

                    "source_type": "servicenow",

                    "source_id": incident["ticket_id"],

                    "confidence":
                        incident["score"],

                    "content":
                        incident["content"]

                }

            )



    # -----------------------------
    # Knowledge Base Evidence
    # -----------------------------

    for document in state.get(
        "filtered_kb_results",
        []
    ):


        evidence.append(

            {

                "source_type": "knowledge_base",

                "source_id":
                    document["document_name"],

                "confidence":
                    document["score"],

                "content":
                    document["content"]

            }

        )


    # -----------------------------
    # GitHub Evidence
    # -----------------------------

    for artifact in state.get(
        "filtered_github_results",
        []
    ):


        evidence.append(

            {

                "source_type": "github",

                "source_id":
                    artifact["artifact_id"],

                "confidence":
                    0.8,

                "content":
                    {
                        "repo":
                            artifact.get("repo"),

                        "artifact_type":
                            artifact.get("artifact_type"),

                        "summary":
                            artifact.get("summary"),

                        "investigation_state":
                            artifact.get(
                                "investigation_state",
                                {}
                            )
                    }

            }

        )



    print(
        f"Prepared {len(evidence)} evidence items"
    )


    return {

        "combined_evidence": evidence

    }

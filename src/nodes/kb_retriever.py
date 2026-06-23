from src.utils.llm import create_embedding
from src.utils.qdrant_client import qdrant_client


COLLECTION_NAME = "sharepoint_kb"


def build_kb_query(state):
    entities = state["extracted_entities"]

    query = f"""
Production RCA Investigation

Application:
{entities.get("service")}

Failure Symptom:
{entities.get("symptom")}

Issue Category:
{entities.get("category")}

Deployment Related:
{entities.get("deployment_related")}

Need troubleshooting steps, possible root causes,
known error patterns, and resolution procedures.
"""

    return query


def kb_retriever_node(state):
    print("\n--- SharePoint KB Retriever Node ---")

    search_query = build_kb_query(state)

    vector = create_embedding(
        search_query
    )

    response = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=5,
        with_payload=True
    )

    documents = []

    for item in response.points:

        documents.append(
            {
                "score": item.score,

                "chunk_id": item.payload.get(
                    "chunk_id"
                ),

                "document_name": item.payload.get(
                    "document_name"
                ),

                "page": item.payload.get(
                    "page"
                ),

                "service": item.payload.get(
                    "service"
                ),

                "document_type": item.payload.get(
                    "document_type"
                ),

                "page": item.payload.get(
                    "page"
                ),

                "content": item.payload.get(
                    "text"
                )
            }
        )

    print(
        f"Retrieved {len(documents)} KB documents"
    )

    return {
        "kb_results": documents
    }
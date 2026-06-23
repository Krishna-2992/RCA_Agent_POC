from src.utils.llm import create_embedding
from src.utils.qdrant_client import qdrant_client


COLLECTION_NAME = "servicenow_incidents"


def build_search_query(state):
    entities = state["extracted_entities"]

    query = f"""
Application:
{entities.get("service")}

Problem:
{entities.get("symptom")}

Category:
{entities.get("category")}
"""

    return query


def servicenow_retriever_node(state):
    print("\n--- ServiceNow Retriever Node ---")

    search_query = build_search_query(state)

    vector = create_embedding(
        search_query
    )

    response = qdrant_client.query_points(
        collection_name=COLLECTION_NAME,
        query=vector,
        limit=5,
        with_payload=True
    )

    incidents = []

    for item in response.points:
        incidents.append(
            {
                "score": item.score,

                "ticket_id": item.payload.get(
                    "ticket_id"
                ),

                "content": item.payload.get(
                    "content"
                ),

                "product": item.payload.get(
                    "product"
                ),

                "category": item.payload.get(
                    "category"
                ),

                "priority": item.payload.get(
                    "priority"
                ),

                "region": item.payload.get(
                    "region"
                )
            }
        )

    print(
        f"Retrieved {len(incidents)} incidents"
    )

    return {
        "servicenow_results": incidents
    }
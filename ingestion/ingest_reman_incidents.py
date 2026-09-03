"""Loads the Reman ServiceNow workbook into its own Qdrant collection.

All three sheets - incidents, service requests and changes - are ServiceNow
records and share one collection, distinguished by `record_type`. The existing
`servicenow_incidents` collection is not touched.

Run:  python -m ingestion.ingest_reman_incidents
"""

import os
import sys
import uuid

from dotenv import load_dotenv

from qdrant_client.models import (
    Distance,
    PayloadSchemaType,
    PointStruct,
    VectorParams
)

from ingestion.reman_records import (
    WORKBOOK_PATH,
    build_embedding_text,
    load_records
)

from src.utils.llm import create_embeddings
from src.utils.qdrant_client import qdrant_client


load_dotenv()


COLLECTION_NAME = os.getenv(
    "REMAN_COLLECTION",
    "reman_incidents"
)


VECTOR_SIZE = 1536

BATCH_SIZE = 100


# Chosen by measurement, not preference. Against five realistic queries,
# relevant records in the top five were:
#     symptom only           13/25
#     symptom + cause        22/25
#     symptom + signals+cause 22/25   <- tied, and keeps error codes searchable
# Embedding the symptom alone loses badly: the diagnostic vocabulary a caller
# uses ("non numeric data", "corrupted") lives in the root cause, not in the
# reported problem.

EMBEDDING_VARIANT = os.getenv(
    "REMAN_EMBEDDING_VARIANT",
    "symptom_signals_cause"
)


# Exact-identifier lookup is filtered, not embedded - vectors are poor at it.
# Searching for "program F8RH0251" semantically returns records that never
# mention it, while a keyword filter returns exactly the two that do.

INDEXED_FIELDS = [
    "record_type",
    "service",
    "programs",
    "error_codes",
    "ticket_id"
]


def create_collection(recreate=False):

    exists = qdrant_client.collection_exists(
        COLLECTION_NAME
    )

    if exists and recreate:

        qdrant_client.delete_collection(
            COLLECTION_NAME
        )

        exists = False

    if not exists:

        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE
            )
        )

        print(f"Created collection: {COLLECTION_NAME}")

    else:
        print(f"Collection already exists: {COLLECTION_NAME}")

    for field in INDEXED_FIELDS:

        try:
            qdrant_client.create_payload_index(
                collection_name=COLLECTION_NAME,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD
            )

        except Exception:
            # Already indexed; Qdrant has no create-if-missing for this.
            pass


def build_points(records):

    points = []

    for start in range(0, len(records), BATCH_SIZE):

        batch = records[start:start + BATCH_SIZE]

        texts = [
            build_embedding_text(record, EMBEDDING_VARIANT)
            for record in batch
        ]

        vectors = create_embeddings(texts)

        for record, text, vector in zip(batch, texts, vectors):

            payload = dict(record)

            payload["content"] = text

            payload["ingestion_source"] = "reman_workbook"

            points.append(
                PointStruct(
                    # Deterministic id, so re-running updates in place.
                    id=str(
                        uuid.uuid5(
                            uuid.NAMESPACE_DNS,
                            record["ticket_id"]
                        )
                    ),
                    vector=vector,
                    payload=payload
                )
            )

        print(f"  embedded {min(start + BATCH_SIZE, len(records))}/{len(records)}")

    return points


def ingest(workbook_path=WORKBOOK_PATH, recreate=False):

    records = load_records(
        workbook_path
    )

    print(f"Loaded {len(records)} records from {workbook_path}")

    create_collection(
        recreate=recreate
    )

    points = build_points(
        records
    )

    for start in range(0, len(points), BATCH_SIZE):

        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=points[start:start + BATCH_SIZE]
        )

    total = qdrant_client.get_collection(
        COLLECTION_NAME
    ).points_count

    print(f"Ingested into '{COLLECTION_NAME}': {total} points")

    return total


if __name__ == "__main__":

    ingest(
        recreate="--recreate" in sys.argv
    )

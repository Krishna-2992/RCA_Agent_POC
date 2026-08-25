import os
import sys
import uuid
import pandas as pd

from tqdm import tqdm
from dotenv import load_dotenv

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct
)

from src.utils.llm import create_embedding

load_dotenv()

# -----------------------------
# Environment Variables
# -----------------------------

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")


COLLECTION_NAME = os.getenv(
    "SERVICENOW_COLLECTION",
    "servicenow_incidents"
)

VECTOR_SIZE = 1536

DEFAULT_CSV_PATH = "customer_support_tickets_1000_poc.csv"


# -----------------------------
# Clients
# -----------------------------

qdrant_client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
    timeout=60
)


# -----------------------------
# CSV
# -----------------------------

def load_incidents_from_csv(csv_path):

    dataframe = pd.read_csv(csv_path)

    # Keep column handling identical to the Snowflake path
    dataframe.columns = dataframe.columns.str.lower()

    print(f"Loaded {len(dataframe)} incidents from {csv_path}")

    return dataframe


# -----------------------------
# Qdrant
# -----------------------------

def create_collection():

    collections = [
        c.name
        for c in qdrant_client.get_collections().collections
    ]

    if COLLECTION_NAME not in collections:

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


def clean_value(value):

    if pd.isna(value):
        return "Not Available"

    return str(value)


def create_embedding_text(row):
    """Text that gets embedded, i.e. what similarity search matches against.

    This previously appended an "Operational RCA Context" paragraph restating
    the product, category and resolution that were already stated above it, so
    the resolution carried twice the weight of the symptom and searches matched
    boilerplate recovery text. Dropping that paragraph moved the one genuinely
    relevant payment incident from rank 2 to rank 1 for the payment-timeout
    query and tripled the number of payment-symptom hits in the top 5.

    Embedding the problem side alone was measurably worse: no incident in this
    corpus describes a timeout symptom, so the resolution text is the only place
    the word appears and removing it lost the relevant incident entirely.
    """

    return f"""
Production Incident Record

Affected Application:
{clean_value(row["product"])}

Issue Category:
{clean_value(row["category"])}

Reported Problem:
{clean_value(row["issue_description"])}

Resolution Applied:
{clean_value(row["resolution_notes"])}
"""


def create_point(row):

    embedding_text = create_embedding_text(row)

    embedding = create_embedding(
        embedding_text
    )

    ticket_id = clean_value(
        row["ticket_id"]
    )

    payload = {

        "content": embedding_text,

        "source": "servicenow",

        "ticket_id": ticket_id,

        "issue_description": clean_value(
            row["issue_description"]
        ),

        "resolution_notes": clean_value(
            row["resolution_notes"]
        ),

        "product": clean_value(row["product"]),
        "category": clean_value(row["category"]),
        "priority": clean_value(row["priority"]),
        "status": clean_value(row["status"]),
        "region": clean_value(row["region"]),
        "sla_breached": clean_value(row["sla_breached"]),
        "escalated": clean_value(row["escalated"]),
        "resolution_time_hours": clean_value(row["resolution_time_hours"]),
        "issue_complexity_score": clean_value(row["issue_complexity_score"]),

        "source_title": f"ServiceNow Incident {ticket_id}",

        "source_location": f"ServiceNow incident {ticket_id}",

        "source_type_label": "ServiceNow Incident",

        "ingestion_source": "csv"
    }

    return PointStruct(
        id=str(
            uuid.uuid5(
                uuid.NAMESPACE_DNS,
                ticket_id
            )
        ),
        vector=embedding,
        payload=payload
    )


def ingest_incidents(csv_path=DEFAULT_CSV_PATH, batch_size=50):

    dataframe = load_incidents_from_csv(csv_path)

    batch = []

    total_uploaded = 0

    for _, row in tqdm(
        dataframe.iterrows(),
        total=len(dataframe),
        desc="Creating embeddings"
    ):

        point = create_point(row)

        batch.append(point)

        if len(batch) >= batch_size:

            qdrant_client.upsert(
                collection_name=COLLECTION_NAME,
                points=batch
            )

            total_uploaded += len(batch)

            print(f"Uploaded {total_uploaded} incidents")

            batch = []

    if batch:

        qdrant_client.upsert(
            collection_name=COLLECTION_NAME,
            points=batch
        )

        total_uploaded += len(batch)

    print(f"CSV ingestion completed. Total records: {total_uploaded}")


if __name__ == "__main__":

    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV_PATH

    create_collection()

    ingest_incidents(path)

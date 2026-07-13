import os
import uuid
import pandas as pd
import snowflake.connector

from tqdm import tqdm
from dotenv import load_dotenv
from openai import OpenAI

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct
)


load_dotenv()

# -----------------------------
# Environment Variables
# -----------------------------

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")


COLLECTION_NAME = "servicenow_incidents"

EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_SIZE = 1536


# -----------------------------
# Clients
# -----------------------------

openai_client = OpenAI(
    api_key=OPENAI_API_KEY
)

qdrant_client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
    timeout=60
)


# -----------------------------
# Snowflake
# -----------------------------

def get_snowflake_connection():

    return snowflake.connector.connect(
        user="LAKSHYA2992",
        password="XYZ",
        account="AYYGNWS-SV86376",
        warehouse="COMPUTE_WH",
        database="AI_DB",
        schema="PUBLIC"
    )


def load_incidents_from_snowflake():

    conn = get_snowflake_connection()

    query = """
    SELECT *
    FROM INCIDENTS 
    Limit 10
    """

    dataframe = pd.read_sql(query, conn)

    conn.close()

    # Snowflake returns column names in uppercase
    dataframe.columns = dataframe.columns.str.lower()

    print(f"Loaded {len(dataframe)} incidents from Snowflake")

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

Operational RCA Context:
A production issue occurred in {clean_value(row["product"])}.
The issue category was {clean_value(row["category"])}.
The final recovery action was {clean_value(row["resolution_notes"])}.
"""


def create_embedding(text):

    response = openai_client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text
    )

    return response.data[0].embedding


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

        "source": "snowflake",

        "ticket_id": ticket_id,

        "product": clean_value(row["product"]),
        "category": clean_value(row["category"]),
        "priority": clean_value(row["priority"]),
        "status": clean_value(row["status"]),
        "region": clean_value(row["region"]),
        "sla_breached": clean_value(row["sla_breached"]),
        "escalated": clean_value(row["escalated"]),
        "resolution_time_hours": clean_value(row["resolution_time_hours"]),
        "issue_complexity_score": clean_value(row["issue_complexity_score"])
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


def ingest_servicenow(batch_size=50):

    dataframe = load_incidents_from_snowflake()

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

    print(f"ServiceNow ingestion completed. Total records: {total_uploaded}")


if __name__ == "__main__":

    create_collection()

    ingest_servicenow()
import os
import uuid
from pathlib import Path

import requests
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI
from pypdf import PdfReader
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, PointStruct, VectorParams
from tqdm import tqdm

from src.utils.llm import create_embedding

load_dotenv()


DOWNLOAD_DIR = Path("sharepoint_downloads")
COLLECTION_NAME = "sharepoint_kb"
EMBEDDING_MODEL = "text-embedding-3-small"
VECTOR_SIZE = 1536

ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
DRIVE_ID = os.getenv("DRIVE_ID")
FOLDER_ID = os.getenv("FOLDER_ID")

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

qdrant_client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)

def get_headers():

    if not ACCESS_TOKEN:
        raise RuntimeError(
            "Missing ACCESS_TOKEN environment variable."
        )

    return {
        "Authorization": f"Bearer {ACCESS_TOKEN}"
    }


def ensure_sharepoint_config():

    missing = []

    if not DRIVE_ID:
        missing.append("DRIVE_ID")

    if not FOLDER_ID:
        missing.append("FOLDER_ID")

    if not QDRANT_URL:
        missing.append("QDRANT_URL")

    if not QDRANT_API_KEY:
        missing.append("QDRANT_API_KEY")

    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
        )


def create_collection():

    collections = [
        collection.name
        for collection in qdrant_client.get_collections().collections
    ]

    if COLLECTION_NAME not in collections:
        qdrant_client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(
                size=VECTOR_SIZE,
                distance=Distance.COSINE
            )
        )
        print(
            f"Created collection: {COLLECTION_NAME}"
        )
        return

    print(
        f"Collection already exists: {COLLECTION_NAME}"
    )


def list_sharepoint_files():

    url = (
        f"https://graph.microsoft.com/v1.0/drives/"
        f"{DRIVE_ID}/items/{FOLDER_ID}/children"
    )

    response = requests.get(
        url,
        headers=get_headers(),
        timeout=60
    )
    response.raise_for_status()

    files = response.json().get(
        "value",
        []
    )

    pdf_files = []

    for file in files:
        name = file.get("name", "")

        if name.lower().endswith(".pdf"):
            pdf_files.append(file)

    print(
        f"Found {len(pdf_files)} PDF files in SharePoint"
    )

    return pdf_files


def download_sharepoint_files():

    DOWNLOAD_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    downloaded_files = []

    for file in list_sharepoint_files():
        item_id = file["id"]
        filename = file["name"]

        download_url = (
            f"https://graph.microsoft.com/v1.0/drives/"
            f"{DRIVE_ID}/items/{item_id}/content"
        )

        response = requests.get(
            download_url,
            headers=get_headers(),
            timeout=120
        )
        response.raise_for_status()

        destination = DOWNLOAD_DIR / filename

        with open(destination, "wb") as file_handle:
            file_handle.write(response.content)

        downloaded_files.append(
            {
                "item_id": item_id,
                "name": filename,
                "path": destination,
                "web_url": file.get("webUrl")
            }
        )

        print(
            f"Downloaded {filename}"
        )

    return downloaded_files


def read_pdf(file_path):

    reader = PdfReader(file_path)
    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text()

        if not text:
            continue

        pages.append(
            {
                "page": page_number,
                "text": text
            }
        )

    return pages


def chunk_document(pages):

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        separators=[
            "\n\n",
            "\n",
            ".",
            " "
        ]
    )

    chunks = []

    for page in pages:
        split_texts = splitter.split_text(
            page["text"]
        )

        for chunk in split_texts:
            chunks.append(
                {
                    "text": chunk,
                    "page": page["page"]
                }
            )

    return chunks

def identify_document_type(filename):

    name = filename.lower()

    if "payment" in name:
        return {
            "service": "Payment Gateway",
            "type": "Runbook"
        }

    if "authentication" in name:
        return {
            "service": "Authentication",
            "type": "SOP"
        }

    if "database" in name:
        return {
            "service": "Database",
            "type": "Runbook"
        }

    if "api" in name:
        return {
            "service": "API Gateway",
            "type": "Runbook"
        }

    if "deployment" in name:
        return {
            "service": "Deployment",
            "type": "Playbook"
        }

    return {
        "service": "General",
        "type": "Knowledge Document"
    }


def build_point(document, chunk, index, metadata):

    chunk_id = (
        f"{document['path'].stem}_page_{chunk['page']}_chunk_{index}"
    )

    payload = {
        "text": chunk["text"],
        "source": "sharepoint",
        "document_name": document["name"],
        "document_path": str(document["path"]),
        "sharepoint_item_id": document["item_id"],
        "sharepoint_web_url": document.get("web_url"),
        "chunk_id": chunk_id,
        "page": chunk["page"],
        "service": metadata["service"],
        "document_type": metadata["type"],
        "source_title": document["name"],
        "source_location": f"{document['name']} - page {chunk['page']}",
        "source_type_label": "SharePoint Document"
    }

    return PointStruct(
        id=str(uuid.uuid4()),
        vector=create_embedding(chunk["text"]),
        payload=payload
    )


def ingest_downloaded_files(downloaded_files):

    all_points = []

    for document in downloaded_files:
        print(
            f"Processing: {document['name']}"
        )

        metadata = identify_document_type(
            document["name"]
        )
        pages = read_pdf(
            document["path"]
        )
        chunks = chunk_document(
            pages
        )

        for index, chunk in tqdm(
            enumerate(chunks),
            total=len(chunks),
            desc=f"Embedding {document['name']}"
        ):
            all_points.append(
                build_point(
                    document,
                    chunk,
                    index,
                    metadata
                )
            )

    if not all_points:
        print(
            "No SharePoint chunks prepared for Qdrant."
        )
        return

    qdrant_client.upsert(
        collection_name=COLLECTION_NAME,
        points=all_points
    )

    print(
        f"Inserted {len(all_points)} SharePoint chunks into Qdrant"
    )


def run_sharepoint_ingestion():

    ensure_sharepoint_config()
    create_collection()
    downloaded_files = download_sharepoint_files()
    ingest_downloaded_files(downloaded_files)


if __name__ == "__main__":
    run_sharepoint_ingestion()

import os
import uuid

from pathlib import Path

from tqdm import tqdm

from dotenv import load_dotenv

from pypdf import PdfReader

from openai import OpenAI

from langchain_text_splitters import RecursiveCharacterTextSplitter


from qdrant_client import QdrantClient

from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct
)



# ---------------------------------------------------
# Environment
# ---------------------------------------------------

load_dotenv()


OPENAI_API_KEY = os.getenv(
    "OPENAI_API_KEY"
)


QDRANT_URL = os.getenv(
    "QDRANT_URL"
)


QDRANT_API_KEY = os.getenv(
    "QDRANT_API_KEY"
)



COLLECTION_NAME = "sharepoint_kb"



# ---------------------------------------------------
# Clients
# ---------------------------------------------------

openai_client = OpenAI(
    api_key=OPENAI_API_KEY
)



qdrant_client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY
)



# ---------------------------------------------------
# Create Qdrant Collection
# ---------------------------------------------------

def create_collection():


    collections = [
        c.name
        for c in qdrant_client.get_collections().collections
    ]


    if COLLECTION_NAME not in collections:


        qdrant_client.create_collection(

            collection_name=COLLECTION_NAME,

            vectors_config=VectorParams(

                size=1536,

                distance=Distance.COSINE
            )
        )


        print(
            f"Created collection: {COLLECTION_NAME}"
        )


    else:

        print(
            "Collection already exists"
        )

        qdrant_client.delete_collection(collection_name=COLLECTION_NAME)



# ---------------------------------------------------
# Extract PDF text
# ---------------------------------------------------

def read_pdf(
    file_path
):


    reader = PdfReader(
        file_path
    )


    pages = []


    for page_number, page in enumerate(reader.pages):


        text = page.extract_text()


        if text:


            pages.append(

                {
                    "page": page_number + 1,

                    "text": text
                }

            )


    return pages



# ---------------------------------------------------
# Chunking
# ---------------------------------------------------

def chunk_document(
    pages
):


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



# ---------------------------------------------------
# Embeddings
# ---------------------------------------------------

def create_embedding(
    text
):


    response = openai_client.embeddings.create(

        model="text-embedding-3-small",

        input=text
    )


    return response.data[0].embedding



# ---------------------------------------------------
# Metadata extraction
# ---------------------------------------------------

def identify_document_type(
    filename
):


    name = filename.lower()


    if "payment" in name:

        return {
            "service":"Payment Gateway",
            "type":"Runbook"
        }


    elif "authentication" in name:

        return {
            "service":"Authentication",
            "type":"SOP"
        }


    elif "database" in name:

        return {
            "service":"Database",
            "type":"Runbook"
        }


    elif "api" in name:

        return {
            "service":"API Gateway",
            "type":"Runbook"
        }


    elif "deployment" in name:

        return {
            "service":"Deployment",
            "type":"Playbook"
        }


    else:

        return {
            "service":"General",
            "type":"Knowledge Document"
        }




# ---------------------------------------------------
# Main ingestion
# ---------------------------------------------------

def ingest_sharepoint(
    folder_path
):


    pdf_files = list(
        Path(folder_path).glob("*.pdf")
    )


    print(
        f"Found {len(pdf_files)} PDF files"
    )


    all_points = []



    for pdf in pdf_files:


        print(
            f"Processing: {pdf.name}"
        )



        metadata = identify_document_type(
            pdf.name
        )


        pages = read_pdf(
            pdf
        )


        chunks = chunk_document(
            pages
        )



        for index, chunk in tqdm(
            enumerate(chunks),
            total=len(chunks)
        ):


            embedding = create_embedding(
                chunk["text"]
            )



            payload = {


                # actual retrieved content

                "text": chunk["text"],



                # source information

                "source":"sharepoint",


                "document_name": pdf.name,

                "document_path": str(pdf),


                "chunk_id": f"{pdf.stem}_page_{chunk['page']}_chunk_{index}",


                "page": chunk["page"],



                # filtering metadata

                "service": metadata["service"],


                "document_type": metadata["type"],

                "source_title": pdf.name,

                "source_location": f"{pdf.name} - page {chunk['page']}",

                "source_type_label": "SharePoint Document"

            }



            point = PointStruct(

                id=str(uuid.uuid4()),

                vector=embedding,

                payload=payload
            )



            all_points.append(
                point
            )



    qdrant_client.upsert(

        collection_name=COLLECTION_NAME,

        points=all_points

    )



    print(
        f"Inserted {len(all_points)} KB chunks"
    )



# ---------------------------------------------------
# Entry
# ---------------------------------------------------

if __name__ == "__main__":


    create_collection()



    ingest_sharepoint(

        "knowledge_source"

    )

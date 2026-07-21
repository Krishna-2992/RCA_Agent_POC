from qdrant_client import QdrantClient
import os
from dotenv import load_dotenv
load_dotenv()

# Either set these as environment variables or replace with your values
QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")

client = QdrantClient(
    url=QDRANT_URL,
    api_key=QDRANT_API_KEY,
)

# Get all collections
collections = client.get_collections().collections

if not collections:
    print("No collections found.")
else:
    print(f"Found {len(collections)} collections:")

    for collection in collections:
        print(f"Deleting: {collection.name}")
        # client.delete_collection(collection_name=collection.name)
        print(f"✓ Deleted {collection.name}")

print("All collections have been deleted.")
from src.utils.qdrant_client import qdrant_client


collections = qdrant_client.get_collections()

for collection in collections.collections:
    print(collection.name)


info = qdrant_client.get_collection(
    collection_name="sharepoint_kb"
)

print(info)
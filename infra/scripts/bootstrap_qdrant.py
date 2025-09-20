import asyncio
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams
import os

QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
COLLECTION = os.getenv("QDRANT_COLLECTION", "chunks__minilm")
DIM = int(os.getenv("QDRANT_DIM", "384"))

async def main():
    client = QdrantClient(url=QDRANT_URL, timeout=10.0)
    exists = client.collection_exists(COLLECTION)
    if not exists:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=DIM, distance=Distance.COSINE),
        )
    print("Qdrant bootstrap OK")

if __name__ == "__main__":
    asyncio.run(main())

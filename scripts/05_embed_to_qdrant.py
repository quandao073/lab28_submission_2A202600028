# scripts/05_embed_to_qdrant.py
import requests
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import os

EMBED_URL = os.environ.get("EMBED_NGROK_URL", "")
qdrant = QdrantClient(host="localhost", port=6333)

# Create (or recreate) collection
if qdrant.collection_exists("documents"):
    qdrant.delete_collection("documents")
qdrant.create_collection(
    collection_name="documents",
    vectors_config=VectorParams(size=384, distance=Distance.COSINE)
)


def get_embeddings(texts: list[str]) -> list[list[float]]:
    """Try remote embedding service first, fall back to local."""
    if EMBED_URL:
        try:
            response = requests.post(f"{EMBED_URL}/embed", json={"texts": texts}, timeout=10)
            if response.ok:
                return response.json()["embeddings"]
        except Exception as e:
            print(f"Remote embedding unavailable ({e}), using local fallback")
    # Local fallback using sentence-transformers
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer("BAAI/bge-small-en-v1.5")
    return model.encode(texts).tolist()


def embed_and_store(records: list[dict]):
    embeddings = get_embeddings([r["text"] for r in records])
    points = [
        PointStruct(id=i, vector=emb, payload=rec)
        for i, (emb, rec) in enumerate(zip(embeddings, records))
    ]
    qdrant.upsert(collection_name="documents", points=points)
    print(f"Integration 5 OK: {len(points)} vectors stored in Qdrant")


embed_and_store([
    {"id": "doc_001", "text": "AI platform integration test"},
    {"id": "doc_002", "text": "Kafka to Airflow pipeline"},
])

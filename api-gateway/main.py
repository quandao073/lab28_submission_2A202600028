# api-gateway/main.py
from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator
from pydantic import BaseModel
import httpx, os, time
from typing import Optional

app = FastAPI(title="AI Platform API Gateway")
Instrumentator().instrument(app).expose(app)  # Integration 9: Prometheus

VLLM_URL = os.environ["VLLM_URL"]
QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")

# LangSmith tracing (Integration 10) — optional, graceful if key not set
try:
    from langsmith import traceable
    _LANGSMITH_ENABLED = True
except Exception:
    _LANGSMITH_ENABLED = False
    def traceable(name=None):
        def decorator(fn):
            return fn
        return decorator


class ChatRequest(BaseModel):
    query: str
    embedding: Optional[list[float]] = None


@app.post("/api/v1/chat")
@traceable(name="chat-endpoint")
async def chat(request: ChatRequest):
    query = request.query
    embedding = request.embedding or [0.0] * 384
    start = time.time()

    # 1. Vector search
    context = []
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            search_resp = await client.post(
                f"{QDRANT_URL}/collections/documents/points/search",
                json={"vector": embedding, "limit": 3}
            )
            if search_resp.status_code == 200:
                context = search_resp.json().get("result", [])
    except Exception:
        pass  # Graceful degradation if vector store unavailable

    # 2. LLM inference
    prompt = f"Context: {context}\n\nQuery: {query}"
    answer = None
    model = "fallback"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            llm_resp = await client.post(f"{VLLM_URL}/v1/chat/completions", json={
                "model": "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4",
                "messages": [{"role": "user", "content": prompt}]
            })
            llm_resp.raise_for_status()
            result = llm_resp.json()
            answer = result["choices"][0]["message"]["content"]
            model = result["model"]
    except Exception:
        # Fallback response when vLLM (Kaggle) is unavailable
        answer = (
            f"[Fallback] The AI platform is operational. "
            f"Your query '{query}' has been received. "
            f"The LLM inference service is currently unavailable — "
            f"please ensure the Kaggle notebook is running and the tunnel URL is configured."
        )

    latency = (time.time() - start) * 1000
    return {
        "answer": answer,
        "latency_ms": round(latency, 2),
        "model": model
    }


@app.get("/health")
def health():
    return {"status": "ok"}

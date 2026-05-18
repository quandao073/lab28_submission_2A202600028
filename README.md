# Lab #28 — Full Platform Integration Sprint

**AI Platform kiến trúc Hybrid (Local + Kaggle GPU)**  
Stack: Kafka · Prefect · Delta Lake · Feast · Qdrant · FastAPI · Prometheus · Grafana · LangSmith · vLLM

---

## Kiến Trúc

```
LOCAL (Docker Compose)
  Kafka ──► Prefect ──► Delta Lake ──► Feast (Redis)
    │                                       │
    └──► Qdrant (Vector Store)              │
                                            ▼
  Prometheus ◄── Grafana          API Gateway (FastAPI :8000)
  LangSmith tracing                         ▲
                                            │  HTTP (ngrok/cloudflared)
KAGGLE (GPU T4/P100)                        │
  vLLM serving ◄──────────────────────────┘
  Embedding service (sentence-transformers)
  MLflow experiment tracking
```

---

## Yêu Cầu

- Docker Desktop đang chạy
- Python 3.10+
- Tài khoản Kaggle với GPU T4 đã kích hoạt (Settings → Accelerator → GPU T4 x2)
- Tunnel service: `ngrok` hoặc `cloudflared`

---

## Quick Start

### Bước 1 — Khởi động Local Stack

```bash
docker compose up -d
docker compose ps   # tất cả services phải Up
```

**Services sau khi khởi động:**

| Service | URL |
|---------|-----|
| API Gateway | http://localhost:8000 |
| Prefect UI | http://localhost:4200 |
| Grafana | http://localhost:3000 (admin/admin) |
| Prometheus | http://localhost:9090 |
| Qdrant Dashboard | http://localhost:6333/dashboard |

### Bước 2 — Setup Kaggle GPU

Tạo Kaggle Notebook, bật GPU T4 x2, chạy:

```python
# Cell 1 — Install
!pip install -q vllm fastapi uvicorn pyngrok mlflow sentence-transformers

# Cell 2 — ngrok token
from pyngrok import ngrok
ngrok.set_auth_token("YOUR_NGROK_TOKEN")

# Cell 3 — Start vLLM (single GPU)
import subprocess, threading, time
def run_vllm():
    subprocess.run([
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", "Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4",
        "--port", "8001", "--max-model-len", "4096", "--gpu-memory-utilization", "0.5"
    ])
threading.Thread(target=run_vllm, daemon=True).start()
time.sleep(60)

# Cell 4 — Expose via tunnel
tunnel = ngrok.connect(8001, "http")
print(f"vLLM URL: {tunnel.public_url}")
```

### Bước 3 — Cập nhật .env

```bash
# Sao chép và điền URL từ Kaggle
VLLM_NGROK_URL=https://xxxx.ngrok-free.app
EMBED_NGROK_URL=https://yyyy.ngrok-free.app
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT=lab28-platform
```

Sau đó restart API gateway:

```bash
docker compose up -d api-gateway
```

### Bước 4 — Chạy Integration Scripts

```bash
# Integration 1: Ingest data vào Kafka
python scripts/01_ingest_to_kafka.py

# Integration 3+4: Delta Lake -> Feast (Redis)
python scripts/03_delta_to_feast.py

# Integration 5: Embed và lưu vào Qdrant
python scripts/05_embed_to_qdrant.py

# Integration 9+10: Verify Prometheus + LangSmith
python scripts/09_verify_observability.py
```

### Bước 5 — Deploy Prefect Flow

```bash
cd prefect/flows
pip install -r requirements.txt
python kafka_to_delta.py
```

### Bước 6 — Smoke Tests

```bash
pytest smoke-tests/ -v
# Kỳ vọng: 8/8 passed
```

### Bước 7 — Production Readiness

```bash
python scripts/production_readiness_check.py
# Kỳ vọng: Score >= 80%
```

---

## Kết Quả

### Smoke Tests — 8/8 PASSED

```
smoke-tests/test_e2e.py::TestHappyPath::test_full_inference_returns_200 PASSED
smoke-tests/test_e2e.py::TestHappyPath::test_health_check_passes         PASSED
smoke-tests/test_e2e.py::TestDataIngestion::test_kafka_ingest_and_qdrant_store PASSED
smoke-tests/test_e2e.py::TestObservability::test_prometheus_scrapes_api_gateway PASSED
smoke-tests/test_e2e.py::TestObservability::test_grafana_dashboard_accessible   PASSED
smoke-tests/test_e2e.py::TestFailurePath::test_invalid_request_returns_422       PASSED
smoke-tests/test_e2e.py::TestFailurePath::test_timeout_handled_gracefully        PASSED
smoke-tests/test_e2e.py::TestFeatureStore::test_feast_redis_has_features         PASSED
```

### Production Readiness — 10/10 = 100%

```
[PASS] Health check endpoint     [PASS] API Gateway responds
[PASS] Prometheus up             [PASS] Grafana up
[PASS] Metrics endpoint exposed  [PASS] Unauthorized request rejected
[PASS] Qdrant healthy            [PASS] Collection exists
[PASS] Redis reachable           [PASS] Kafka topics exist

Production Readiness Score: 10/10 = 100% — Status: READY
```

---

## Câu Hỏi Nộp Bài

### 1. Trade-offs trong thiết kế kiến trúc AI platform

**Thiết kế:**
- **Event-driven (Kafka)** thay vì gọi trực tiếp: tăng decoupling và khả năng replay, nhưng thêm độ phức tạp vận hành.
- **Delta Lake (parquet)** thay vì database thực: đơn giản hóa storage và cho phép batch processing, đánh đổi lấy query latency cao hơn.
- **Hybrid Local+Kaggle**: tiết kiệm cost GPU (không cần GPU local), nhưng phụ thuộc vào độ ổn định của tunnel và kết nối mạng.

**Cân bằng:**
- *Performance*: Qdrant in-memory indexing + embedding cache giúp vector search < 50ms.
- *Reliability*: API Gateway có fallback response khi vLLM unavailable; Qdrant/Redis graceful degradation.
- *Maintainability*: Tách rõ 3 lớp (ingestion / processing / serving), mỗi lớp độc lập scale và replace.

### 2. Xử lý ngắt kết nối Local ↔ Kaggle

**Cơ chế fallback trong API Gateway** (`api-gateway/main.py`):
- Nếu vLLM call timeout hoặc lỗi, trả về fallback response thay vì 503.
- Vector search (Qdrant) được thực hiện trước, độc lập với LLM — context vẫn được lấy dù LLM lỗi.
- Embedding script (`05_embed_to_qdrant.py`) có local fallback dùng `sentence-transformers` khi remote service không available.

**Chiến lược phục hồi:**
1. Restart Kaggle kernel và lấy URL tunnel mới.
2. Cập nhật `VLLM_NGROK_URL` trong `.env`.
3. Restart API Gateway: `docker compose up -d api-gateway`.

### 3. Event-driven Architecture với Kafka

Kafka giúp decouple theo 3 chiều:
- **Temporal**: Producer (ingestion script) và Consumer (Prefect flow) chạy độc lập về thời gian — producer không cần đợi consumer xử lý xong.
- **Spatial**: Consumer chạy bên trong Docker network (`kafka:29092`), producer chạy từ host (`localhost:9092`) — hai môi trường hoàn toàn tách biệt.
- **Logical**: Thêm consumer mới (ví dụ: real-time alerting) không ảnh hưởng pipeline hiện có.

**Lợi ích thực tế**: Nếu Prefect worker crash, messages vẫn giữ trong Kafka và được xử lý khi worker khởi động lại (replay từ `auto_offset_reset="earliest"`).

### 4. Observability Implementation

**Metrics (Prometheus + Grafana):**
- `prometheus-fastapi-instrumentator` tự động expose `/metrics` từ API Gateway.
- Prometheus scrape mỗi 15s: `http_requests_total`, `http_request_duration_seconds`, `up`.
- Grafana visualize request rate, P95 latency, error rate.

**Traces (LangSmith):**
- `@traceable` decorator trên `chat` endpoint ghi lại input/output mỗi request.
- Script `09_verify_observability.py` tạo run trực tiếp qua SDK để verify connectivity.
- Có thể filter theo `project_name="lab28-platform"` trên LangSmith UI.

**Logs:**
- Tất cả container logs qua `docker compose logs -f <service>`.
- API Gateway log mỗi HTTP request (method, path, status, latency).

### 5. Graceful Degradation khi Service Crash

**Kịch bản Qdrant crash:**
- Vector search trong `chat` endpoint được wrapped trong `try/except` — nếu lỗi, `context = []` (empty context).
- LLM vẫn được gọi với prompt không có context, trả về câu trả lời chung chung thay vì crash.
- Health check (`/health`) vẫn trả về 200 vì không phụ thuộc Qdrant.

**Kịch bản Kafka crash:**
- Ingestion script (`01_ingest_to_kafka.py`) sẽ raise exception ngay tại producer.
- Prefect consumer flow sẽ timeout sau `consumer_timeout_ms=5000` và kết thúc gracefully.
- Data đã ingested trước đó vẫn an toàn trong Delta Lake.

**Kịch bản Redis (Feast) crash:**
- Không ảnh hưởng đến chat endpoint (Redis chỉ dùng cho feature store, không nằm trong critical path).
- Script `03_delta_to_feast.py` sẽ fail với connection error và có thể retry.

**Restart strategy:** `docker compose start <service>` — không mất data vì volumes persistent.

---

## Cấu Trúc Thư Mục

```
Day28-Lab-Assignment/
├── docker-compose.yml          # Full stack: Kafka, Prefect, Qdrant, Redis, Prometheus, Grafana, API Gateway
├── .env                        # Environment variables (VLLM URL, LangSmith key)
├── api-gateway/
│   ├── main.py                 # FastAPI gateway: vector search + LLM inference + metrics
│   ├── Dockerfile
│   └── requirements.txt
├── prefect/flows/
│   ├── kafka_to_delta.py       # Prefect flow: Kafka consumer -> Delta Lake
│   └── requirements.txt
├── scripts/
│   ├── 01_ingest_to_kafka.py   # Integration 1: data ingestion
│   ├── 03_delta_to_feast.py    # Integration 3+4: Delta Lake -> Feast
│   ├── 05_embed_to_qdrant.py   # Integration 5: embeddings -> vector store
│   ├── 09_verify_observability.py  # Integration 9+10: Prometheus + LangSmith
│   └── production_readiness_check.py
├── monitoring/
│   └── prometheus.yml          # Prometheus scrape config
├── smoke-tests/
│   └── test_e2e.py             # 8 end-to-end tests
├── delta-lake/                 # Parquet storage (simulated Delta Lake)
├── screenshots/                # Demo screenshots
├── smoke_tests_output.txt      # pytest -v output
├── production_readiness_output.txt  # readiness check output
└── README.md
```

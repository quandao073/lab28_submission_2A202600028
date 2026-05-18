import pandas as pd, os, time
from datetime import datetime

path = "delta-lake/raw"
os.makedirs(path, exist_ok=True)
df = pd.DataFrame([
    {"id": "doc_001", "text": "AI platform integration test", "timestamp": time.time()},
    {"id": "doc_002", "text": "Kafka to Airflow pipeline", "timestamp": time.time()},
])
ts = datetime.now().strftime("%Y%m%d_%H%M%S")
df.to_parquet(f"{path}/batch_{ts}.parquet")
print(f"Seeded delta-lake with {len(df)} records at {path}/batch_{ts}.parquet")

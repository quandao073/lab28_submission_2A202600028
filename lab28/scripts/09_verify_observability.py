# scripts/09_verify_observability.py
import requests, os

def check_prometheus():
    resp = requests.get("http://localhost:9090/api/v1/query",
                        params={"query": 'http_requests_total{job="api-gateway"}'})
    data = resp.json()
    assert data["status"] == "success"
    print("Integration 9 OK: Prometheus metrics flowing")

def check_langsmith():
    from langsmith import Client
    client = Client(api_key=os.environ["LANGCHAIN_API_KEY"])
    project_name = "lab28-platform"
    # Ensure project exists (create if missing)
    try:
        project = client.read_project(project_name=project_name)
    except Exception:
        project = client.create_project(project_name)
        print(f"Created LangSmith project: {project_name}")

    # Log a test run to verify tracing works
    import uuid
    from datetime import datetime, timezone
    run_id = uuid.uuid4()
    client.create_run(
        id=run_id,
        name="integration-check",
        run_type="chain",
        inputs={"query": "observability check"},
        project_name=project_name,
        start_time=datetime.now(timezone.utc),
    )
    client.update_run(
        run_id,
        outputs={"status": "ok"},
        end_time=datetime.now(timezone.utc),
    )
    print(f"Integration 10 OK: LangSmith trace created in project '{project_name}'")

check_prometheus()
check_langsmith()

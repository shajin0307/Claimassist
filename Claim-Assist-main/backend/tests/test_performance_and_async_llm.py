import time
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.database import get_db, SessionLocal, init_db, Base, engine, AuditCacheRecord
from app.llm_service import ASYNC_EXPLANATIONS

@pytest.fixture(autouse=True)
def setup_test_db_and_cache():
    init_db()
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        session.query(AuditCacheRecord).delete()
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()
    yield

client = TestClient(app)


def test_cached_data_quality_and_refresh():
    """Verify Data Quality report uses database cache on repeated requests and refreshes on POST."""
    # First call generates initial report
    resp1 = client.get("/api/data-quality/report?max_chunks=1")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "metadata" in data1
    assert data1["metadata"]["cached"] is False

    # Second call returns cached report immediately
    start_t = time.time()
    resp2 = client.get("/api/data-quality/report?max_chunks=1")
    elapsed_ms = (time.time() - start_t) * 1000
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["metadata"]["cached"] is True
    assert elapsed_ms < 500  # Must be fast (< 500ms)

    # Explicit refresh endpoint recomputes
    resp_refresh = client.post("/api/data-quality/refresh?max_chunks=1")
    assert resp_refresh.status_code == 200
    data_ref = resp_refresh.json()
    assert data_ref["metadata"]["cached"] is False


def test_cached_freshness_response():
    """Verify Freshness report caching."""
    resp1 = client.get("/api/freshness/report?max_chunks=1")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "metadata" in data1
    assert data1["metadata"]["cached"] is False

    resp2 = client.get("/api/freshness/report?max_chunks=1")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["metadata"]["cached"] is True


def test_cached_cross_domain_response():
    """Verify Cross-Domain audit report caching."""
    resp1 = client.get("/api/cross-domain/report")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "metadata" in data1
    assert data1["metadata"]["cached"] is False

    resp2 = client.get("/api/cross-domain/report")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["metadata"]["cached"] is True


def test_cached_care_management_response():
    """Verify Care Management signals caching."""
    resp1 = client.get("/api/care-management/signals")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "metadata" in data1
    assert data1["metadata"]["cached"] is False

    resp2 = client.get("/api/care-management/signals")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["metadata"]["cached"] is True


def test_cached_decision_impact_response():
    """Verify Decision Impact report caching."""
    resp1 = client.get("/api/decision-impact/report")
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert "metadata" in data1
    assert data1["metadata"]["cached"] is False

    resp2 = client.get("/api/decision-impact/report")
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["metadata"]["cached"] is True


def test_async_llm_processing_and_status_polling():
    """Verify async LLM explanation submission returns PROCESSING immediately and status polling works."""
    payload = {
        "issue_type": "AUTHORIZATION_ANOMALY",
        "reference_id": "TEST_AUTH_ASYNC_001",
        "evidence": {
            "auth_id": "TEST_AUTH_ASYNC_001",
            "prediction": "ANOMALY",
            "probability": 0.95,
            "final_priority": "CRITICAL"
        }
    }

    start_t = time.time()
    resp = client.post("/api/llm/explain", json=payload)
    elapsed_ms = (time.time() - start_t) * 1000

    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "PROCESSING"
    assert "request_id" in data
    assert elapsed_ms < 200  # Non-blocking submission (<200ms)

    req_id = data["request_id"]

    # Poll status immediately
    status_resp = client.get(f"/api/llm/explanation/{req_id}")
    assert status_resp.status_code == 200
    status_data = status_resp.json()
    assert status_data["status"] in ["PROCESSING", "SUCCESS", "LLM_UNAVAILABLE"]


def test_llm_unavailable_fallback_structure():
    """Verify LLM_UNAVAILABLE structure when Ollama fails."""
    from app.llm_service import LLMExplanationService
    service = LLMExplanationService(base_url="http://invalid-ollama-host:9999", timeout=1)
    fallback = service._fallback_response("Connection refused")
    assert fallback["status"] == "LLM_UNAVAILABLE"
    assert fallback["confidence"] == 0.0
    assert "unavailable" in fallback["message"].lower()


def test_deterministic_ml_behavior_unaffected():
    """Verify frozen ML model inference and hybrid risk decisions remain strictly deterministic."""
    sample_anomaly = {
        "auth_id": "TEST_FROZEN_001",
        "ml_req_units": 180.0,
        "ml_aprvd_units": 1.0,
        "ml_latency_hours": 780.0,
        "ml_bene_age": 75.0,
        "ml_prov_partd_cost": 25000.0,
    }
    resp = client.post("/api/predict", json=sample_anomaly)
    assert resp.status_code == 200
    data = resp.json()
    assert data["prediction"] == "ANOMALY"
    assert data["probability"] >= 0.81
    assert data["final_priority"] == "CRITICAL"

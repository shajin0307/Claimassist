import io
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, SessionLocal, AuthorizationRecord

# Ensure PostgreSQL tables exist
Base.metadata.create_all(bind=engine)


@pytest.fixture(autouse=True)
def cleanup_api_test_records():
    """Cleanup test records after each test run in PostgreSQL."""
    yield
    try:
        session = SessionLocal()
        session.query(AuthorizationRecord).filter(
            AuthorizationRecord.auth_id.like("AUTH_API_%") |
            AuthorizationRecord.auth_id.like("AUTH_FORBIDDEN_%") |
            AuthorizationRecord.auth_id.like("CSV_%") |
            AuthorizationRecord.auth_id.like("SIM_%")
        ).delete(synchronize_session=False)
        session.commit()
        session.close()
    except Exception:
        pass


client = TestClient(app)


def test_api_health():
    """Test GET /api/health endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["model_loaded"] is True
    assert data["feature_count"] == 25
    assert data["threshold"] == 0.81
    assert data["model_name"] == "Autoencoder + Logistic Regression"


def test_api_predict_valid_input():
    """Test POST /api/predict endpoint with valid payload."""
    payload = {
        "auth_id": "AUTH_API_999",
        "ml_req_units": 5.0,
        "ml_aprvd_units": 5.0,
        "ml_units_diff": 0.0,
        "ml_units_ratio": 1.0,
        "ml_latency_hours": 10.0,
        "ml_bene_carrier_cnt": 2.0,
        "ml_bene_outpatient_cnt": 1.0,
        "ml_bene_pde_cnt": 5.0,
        "ml_bene_total_utilization": 8.0,
        "ml_bene_gender": 1.0,
        "ml_bene_race": 1.0,
        "ml_bene_age": 65.0,
        "ml_prov_partd_clms": 20.0,
        "ml_prov_partd_cost": 500.0,
        "ml_prov_avg_cost_per_clm": 25.0,
        "has_partd_provider_match": 1.0
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["auth_id"] == "AUTH_API_999"
    assert data["prediction"] in ["NORMAL", "ANOMALY"]
    assert 0.0 <= data["probability"] <= 1.0
    assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    assert data["final_priority"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def test_api_predict_forbidden_fields_ignored():
    """Test that ground-truth target fields are stripped and ignored."""
    payload = {
        "auth_id": "AUTH_FORBIDDEN_TEST",
        "EXPECTED_ANOMALY": 1,
        "EXPECTED_TYPE": "FRAUD",
        "IS_ANOMALY": 1,
        "ANOMALY_TYPE": "OVERUTILIZATION",
        "ml_req_units": 5.0,
        "ml_aprvd_units": 5.0,
        "ml_latency_hours": 10.0,
        "ml_bene_age": 65.0,
        "ml_prov_partd_cost": 500.0
    }
    response = client.post("/api/predict", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["auth_id"] == "AUTH_FORBIDDEN_TEST"


def test_api_stream_simulate():
    """Test POST /api/stream/simulate real-time demo endpoint."""
    response = client.post("/api/stream/simulate")
    assert response.status_code == 200
    data = response.json()
    assert data["auth_id"].startswith("SIM_")
    assert data["prediction"] in ["NORMAL", "ANOMALY"]
    assert data["final_priority"] in ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def test_api_batch_predict():
    """Test POST /api/batch-predict CSV file upload endpoint."""
    csv_content = (
        "auth_id,ml_req_units,ml_aprvd_units,ml_latency_hours,ml_bene_age,ml_prov_partd_cost\n"
        "CSV_001,5.0,5.0,10.0,65.0,500.0\n"
        "CSV_002,150.0,1.0,720.0,78.0,25000.0\n"
    )
    file_bytes = csv_content.encode("utf-8")
    files = {"file": ("test_batch.csv", io.BytesIO(file_bytes), "text/csv")}

    response = client.post("/api/batch-predict", files=files)
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "results" in data
    assert data["summary"]["total_records"] == 2
    assert len(data["results"]) == 2


def test_api_predictions_and_stats():
    """Test GET /api/predictions and GET /api/stats endpoints."""
    res_stats = client.get("/api/stats")
    assert res_stats.status_code == 200
    stats_data = res_stats.json()
    assert "total_requests" in stats_data
    assert "normal_count" in stats_data
    assert "anomaly_count" in stats_data

    res_preds = client.get("/api/predictions?page=1&page_size=10")
    assert res_preds.status_code == 200
    preds_data = res_preds.json()
    assert "total" in preds_data
    assert "items" in preds_data


def test_api_data_quality_report():
    """Test GET /api/data-quality/report endpoint."""
    response = client.get("/api/data-quality/report?max_chunks=1")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "datasets" in data
    assert data["summary"]["total_datasets_evaluated"] == 7
    assert data["summary"]["overall_cms_quality_score"] >= 0.0


def test_websocket_live_connection():
    """Test WebSocket /ws/live endpoint."""
    with client.websocket_connect("/ws/live") as websocket:
        data = websocket.receive_json()
        assert data["event_type"] == "CONNECTED"
        websocket.send_text("ping")

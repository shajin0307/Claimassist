import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, BASE_DIR
from app.freshness import CMSFreshnessEngine, LiveLatencyTracker

# Ensure PostgreSQL tables exist
Base.metadata.create_all(bind=engine)

client = TestClient(app)


def test_cms_freshness_engine_single_dataset():
    """Test CMSFreshnessEngine on a single CMS dataset."""
    engine_inst = CMSFreshnessEngine()
    res = engine_inst.evaluate_freshness("Beneficiary 2022", chunksize=10000, max_chunks=None)
    assert res["dataset_name"] == "Beneficiary 2022"
    assert res["freshness_status"] in ["AVAILABLE", "UNAVAILABLE"]
    assert res["rows_available"] >= 0
    assert res["rows_evaluated"] >= 0
    assert res["coverage_percentage"] >= 0.0
    assert res["reporting_period"] == "2022"
    assert res["ingestion_duration_ms"] >= 0.0


def test_cms_freshness_engine_missing_file_handling():
    """Test CMSFreshnessEngine behavior when a dataset is missing."""
    engine_inst = CMSFreshnessEngine()
    engine_inst.registry["NON_EXISTENT_DATASET"] = {"path": BASE_DIR / "missing.csv", "exists": False}
    res = engine_inst.evaluate_freshness("NON_EXISTENT_DATASET")
    assert res["freshness_status"] == "UNAVAILABLE"
    assert res["file_size_bytes"] == 0
    assert res["rows_evaluated"] == 0
    assert res["file_modified_time"] is None


def test_cms_freshness_full_report():
    """Test full freshness report generation across all 7 CMS datasets."""
    engine_inst = CMSFreshnessEngine()
    report = engine_inst.generate_full_freshness_report(chunksize=5000, max_chunks_per_file=1)
    assert report["summary"]["total_datasets"] == 7
    assert report["summary"]["total_ingestion_duration_ms"] >= 0.0
    assert "datasets" in report
    assert "Carrier" in report["datasets"]
    assert "Part D 2023" in report["datasets"]


def test_live_latency_tracker():
    """Test LiveLatencyTracker microsecond timing recording."""
    tracker = LiveLatencyTracker()
    tracker.mark_inference_start()
    tracker.mark_inference_end()
    tracker.mark_db_persisted()
    tracker.mark_ws_broadcast()

    summary = tracker.get_timing_summary()
    assert "request_received_at" in summary
    assert summary["inference_duration_ms"] > 0.0
    assert summary["end_to_end_latency_ms"] > 0.0


def test_api_freshness_report_endpoint():
    """Test GET /api/freshness/report API endpoint."""
    response = client.get("/api/freshness/report?max_chunks=1")
    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
    assert "datasets" in data
    assert data["summary"]["total_datasets"] >= 7
    assert "Outpatient" in data["datasets"]
    assert data["datasets"]["Outpatient"]["freshness_status"] in ["AVAILABLE", "UNAVAILABLE"]


def test_api_stats_extended_freshness():
    """Test that GET /api/stats returns extended freshness metadata."""
    client.get("/api/freshness/report?max_chunks=1")

    res = client.get("/api/stats")
    assert res.status_code == 200
    stats = res.json()
    assert "cms_freshness" in stats
    assert stats["cms_freshness"]["audited_datasets_count"] >= 7
    assert stats["cms_freshness"]["status"] in ["AVAILABLE", "PENDING_AUDIT"]

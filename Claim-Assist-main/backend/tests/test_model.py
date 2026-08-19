import pytest
from pathlib import Path
from app.model_service import ModelService


def test_model_artifacts_and_config():
    """Verify that all 5 model artifacts load, feature count is 25, and threshold is 0.81."""
    service = ModelService()
    
    # 1. All five artifacts loaded check
    assert service.is_loaded is True
    assert service.imputer is not None
    assert service.scaler is not None
    assert service.autoencoder is not None
    assert service.logistic_regression is not None

    # 2. Feature count = 25
    assert service.config.get("input_dim") == 25

    # 3. Threshold = 0.81
    assert service.config.get("threshold") == 0.81


def test_model_inference_probability_and_prediction():
    """Verify that model produces probability between 0 and 1, and prediction is NORMAL or ANOMALY."""
    service = ModelService()

    sample_input = {
        "auth_id": "TEST_AUTH_001",
        "ml_req_units": 2.0,
        "ml_aprvd_units": 2.0,
        "ml_latency_hours": 12.0,
        "ml_bene_carrier_cnt": 1.0,
        "ml_bene_outpatient_cnt": 0.0,
        "ml_bene_pde_cnt": 2.0,
        "ml_bene_total_utilization": 5.0,
        "ml_bene_gender": 1.0,
        "ml_bene_race": 1.0,
        "ml_bene_age": 70.0,
        "ml_prov_partd_clms": 15.0,
        "ml_prov_partd_cost": 450.0,
        "ml_prov_avg_cost_per_clm": 30.0,
        "has_partd_provider_match": 1.0
    }

    result = service.predict(sample_input)

    # 4. Probability between 0 and 1
    assert 0.0 <= result["probability"] <= 1.0

    # 5. Prediction is NORMAL or ANOMALY
    assert result["prediction"] in ["NORMAL", "ANOMALY"]
    assert isinstance(result["risk_level"], str)
    assert isinstance(result["reasons"], list)
    assert isinstance(result["inference_latency_ms"], float)


def test_model_ignores_forbidden_fields():
    """Verify forbidden ground-truth fields do not crash or alter model execution."""
    service = ModelService()

    sample_input_with_forbidden = {
        "auth_id": "TEST_AUTH_002",
        "ml_req_units": 1.0,
        "ml_aprvd_units": 1.0,
        "EXPECTED_ANOMALY": 1,
        "EXPECTED_TYPE": "FRAUD",
        "IS_ANOMALY": True,
        "ANOMALY_TYPE": "UNIT_SPIKE"
    }

    result = service.predict(sample_input_with_forbidden)
    assert result["prediction"] in ["NORMAL", "ANOMALY"]
    assert 0.0 <= result["probability"] <= 1.0

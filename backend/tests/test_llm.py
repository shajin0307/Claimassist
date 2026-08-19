import pytest
import json
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import Base, engine, SessionLocal, AuthorizationRecord, save_authorization_record, init_db
from app.llm_service import LLMExplanationService
from app.llm_prompts import SYSTEM_PROMPT, build_evidence_user_prompt

# Ensure tables exist
init_db()


@pytest.fixture(autouse=True)
def cleanup_llm_test_records():
    """Cleanup test records after each test run."""
    yield
    try:
        session = SessionLocal()
        session.query(AuthorizationRecord).filter(
            AuthorizationRecord.auth_id.like("AUTH_POSTGRES_TEST_%") |
            AuthorizationRecord.auth_id.like("TEST_%")
        ).delete(synchronize_session=False)
        session.commit()
        session.close()
    except Exception:
        pass


client = TestClient(app)


def test_llm_config_and_prompt_construction():
    """Test LLM service initialization and evidence prompt construction."""
    ollama_service = LLMExplanationService(provider="ollama", base_url="http://localhost:11434", model="llama3.2:3b")
    assert ollama_service.model == "llama3.2:3b"
    assert "localhost:11434" in ollama_service.base_url
    assert ollama_service.timeout == 30

    groq_service = LLMExplanationService(provider="groq", api_key="test_key", model="openai/gpt-oss-120b")
    assert groq_service.provider == "groq"
    assert groq_service.model == "openai/gpt-oss-120b"
    assert "api.groq.com" in groq_service.base_url

    # Ensure system prompt contains strict non-override and non-clinical rules
    assert "do not make clinical diagnoses" in SYSTEM_PROMPT.lower()
    assert "do not change ml predictions" in SYSTEM_PROMPT.lower()
    assert "insufficient evidence" in SYSTEM_PROMPT.lower()

    evidence = {"auth_id": "TEST_123", "prediction": "ANOMALY", "probability": 0.95}
    user_prompt = build_evidence_user_prompt("AUTHORIZATION_ANOMALY", evidence)
    assert "TEST_123" in user_prompt
    assert "ANOMALY" in user_prompt


def test_llm_service_successful_parsing():
    """Test LLM service parsing of valid JSON output from Ollama."""
    service = LLMExplanationService()
    
    mock_response_json = {
        "response": '{"status": "SUCCESS", "likely_cause": "Unit mismatch", "business_impact": "Workflow delay", "recommended_fix": "Audit units", "evidence_used": ["Units 180 vs 1"], "confidence": 0.92}'
    }
    
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(mock_response_json).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = service.generate_explanation("AUTHORIZATION_ANOMALY", {"auth_id": "AUTH_1"})
        assert res["status"] == "SUCCESS"
        assert res["likely_cause"] == "Unit mismatch"
        assert res["confidence"] == 0.92
        assert len(res["evidence_used"]) == 1


def test_llm_service_invalid_json_fallback():
    """Test LLM service fallback when Ollama returns non-JSON raw text."""
    service = LLMExplanationService()
    
    mock_response_raw = {
        "response": "The authorization exhibits severe unit discrepancies exceeding approved guidelines."
    }
    
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = json.dumps(mock_response_raw).encode("utf-8")
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        res = service.generate_explanation("AUTHORIZATION_ANOMALY", {"auth_id": "AUTH_1"})
        assert res["status"] == "SUCCESS"
        assert "exhibits severe unit discrepancies" in res["likely_cause"]
        assert res["confidence"] == 0.85


def test_llm_service_offline_fallback():
    """Test LLM service graceful fallback when Ollama is offline or times out."""
    service = LLMExplanationService()

    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
        res = service.generate_explanation("AUTHORIZATION_ANOMALY", {"auth_id": "AUTH_1"})
        assert res["status"] == "LLM_UNAVAILABLE"
        assert res["likely_cause"] is None
        assert "unavailable" in res["message"].lower()


def test_api_explain_endpoint():
    """Test POST /api/llm/explain endpoint returns PROCESSING immediately."""
    payload = {
        "issue_type": "CMS_DATA_QUALITY",
        "evidence": {
            "dataset": "Carrier",
            "overall_quality_score": 91.68,
            "actionable_violations": 0
        }
    }
    response = client.post("/api/llm/explain", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PROCESSING"
    assert "request_id" in data


def test_api_explain_authorization_from_postgres():
    """Test POST /api/llm/explain/authorization/{auth_id} using existing PostgreSQL record returns PROCESSING immediately."""
    db = SessionLocal()
    save_authorization_record(db, {
        "auth_id": "AUTH_POSTGRES_TEST_100",
        "ml_req_units": 100.0,
        "ml_aprvd_units": 1.0,
        "prediction": "ANOMALY",
        "probability": 0.92,
        "risk_level": "HIGH",
        "rule_violations_count": 1,
        "sla_risk": "HIGH",
        "final_priority": "CRITICAL",
        "reasons": ["Requested units (100.0) exceed approved units (1.0)."],
        "inference_latency_ms": 1.8
    })
    db.close()

    response = client.post("/api/llm/explain/authorization/AUTH_POSTGRES_TEST_100")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "PROCESSING"
    assert "request_id" in data


def test_api_explain_authorization_404():
    """Test POST /api/llm/explain/authorization/{auth_id} returns 404 for non-existent auth_id."""
    response = client.post("/api/llm/explain/authorization/NON_EXISTENT_AUTH_999")
    assert response.status_code == 404

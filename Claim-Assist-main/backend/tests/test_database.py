import os
import pytest
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import (
    Base, AuthorizationRecord, save_authorization_record,
    create_db_engine, DATABASE_URL, engine, SessionLocal, init_db
)


@pytest.fixture
def db_session():
    """Provide a clean database session for testing, with automatic test record cleanup."""
    init_db()
    session = SessionLocal()
    yield session
    # Cleanup test records created during testing
    try:
        session.query(AuthorizationRecord).filter(
            AuthorizationRecord.auth_id.like("AUTH_DB_TEST_%") |
            AuthorizationRecord.auth_id.like("SCHEMA_TEST_%")
        ).delete(synchronize_session=False)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def test_db_engine_creation_and_url_handling():
    """Verify PostgreSQL & SQLite engine creation and rejection of unsupported schemes."""
    pg_url = "postgresql+psycopg://postgres:password@localhost:5432/final_anomaly"
    pg_eng = create_db_engine(pg_url)
    assert pg_eng.name == "postgresql"
    assert "psycopg" in pg_eng.driver

    # Test SQLite engine creation
    sqlite_eng = create_db_engine("sqlite:///test.db")
    assert sqlite_eng.name == "sqlite"

    # Reject unsupported schemas
    with pytest.raises(ValueError, match="Invalid DATABASE_URL scheme"):
        create_db_engine("mysql://root:password@localhost:3306/db")

    with pytest.raises(ValueError, match="Invalid DATABASE_URL scheme"):
        create_db_engine("redis://localhost:6379")


def test_database_save_and_retrieve(db_session):
    """Test creating, persisting, and querying AuthorizationRecord ORM instances in PostgreSQL."""
    record_data = {
        "auth_id": "AUTH_DB_TEST_001",
        "ml_req_units": 10.0,
        "ml_aprvd_units": 10.0,
        "ml_latency_hours": 5.0,
        "ml_bene_age": 68.0,
        "ml_prov_partd_cost": 1200.0,
        "prediction": "NORMAL",
        "probability": 0.25,
        "risk_level": "LOW",
        "rule_violations_count": 0,
        "sla_risk": "LOW",
        "final_priority": "LOW",
        "reasons": ["All policy metrics within expected range."],
        "inference_latency_ms": 2.5
    }

    saved = save_authorization_record(db_session, record_data)
    assert saved.id is not None
    assert saved.auth_id == "AUTH_DB_TEST_001"
    assert saved.prediction == "NORMAL"
    assert saved.final_priority == "LOW"

    # Query back from PostgreSQL
    queried = db_session.query(AuthorizationRecord).filter(AuthorizationRecord.auth_id == "AUTH_DB_TEST_001").first()
    assert queried is not None
    assert queried.probability == 0.25
    assert len(queried.reasons) == 1
    assert queried.reasons[0] == "All policy metrics within expected range."


def test_database_schema_fields(db_session):
    """Verify all required ORM fields exist on AuthorizationRecord."""
    rec = AuthorizationRecord(
        auth_id="SCHEMA_TEST_001",
        ml_req_units=5.0,
        ml_aprvd_units=5.0,
        ml_latency_hours=12.0,
        ml_bene_age=70.0,
        ml_prov_partd_cost=500.0,
        prediction="NORMAL",
        probability=0.15,
        ml_risk_level="LOW",
        rule_violations_count=0,
        sla_risk="LOW",
        final_priority="LOW",
        reasons_json='["Test reason"]',
        inference_latency_ms=1.8
    )
    db_session.add(rec)
    db_session.commit()

    retrieved = db_session.query(AuthorizationRecord).filter(AuthorizationRecord.auth_id == "SCHEMA_TEST_001").first()
    assert retrieved is not None
    d = retrieved.to_dict()

    expected_keys = [
        "id", "auth_id", "timestamp", "ml_req_units", "ml_aprvd_units",
        "ml_latency_hours", "ml_bene_age", "ml_prov_partd_cost", "prediction",
        "probability", "risk_level", "rule_violations_count", "sla_risk",
        "final_priority", "reasons", "inference_latency_ms"
    ]
    for key in expected_keys:
        assert key in d

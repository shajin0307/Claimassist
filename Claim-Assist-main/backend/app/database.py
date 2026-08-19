import os
import json
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
try:
    from dotenv import load_dotenv
    _has_dotenv = True
except ImportError:
    _has_dotenv = False

from sqlalchemy import (
    create_engine, Integer, String, Float, DateTime, Text, BigInteger
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

# Load environment variables from .env (project root or final_anomaly_system)
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

if _has_dotenv:
    for env_file in [PROJECT_ROOT / ".env", BASE_DIR / ".env"]:
        if env_file.exists():
            load_dotenv(env_file, override=True)

DEFAULT_PG_URL = "postgresql+psycopg://postgres:password@localhost:5432/final_anomaly"

# Read DATABASE_URL from environment variable
DATABASE_URL = os.getenv("DATABASE_URL", DEFAULT_PG_URL)


def normalize_postgres_url(url: str) -> str:
    """
    Ensure the connection URL uses a supported PostgreSQL dialect for SQLAlchemy + psycopg.
    Normalizes 'postgres://' (common in cloud deployments: Supabase/Neon/Render/Railway) to 'postgresql+psycopg://'.
    """
    cleaned = url.strip()
    if cleaned.startswith("postgres://"):
        cleaned = cleaned.replace("postgres://", "postgresql+psycopg://", 1)
    elif cleaned.startswith("postgresql://") and "+psycopg" not in cleaned:
        cleaned = cleaned.replace("postgresql://", "postgresql+psycopg://", 1)
    return cleaned


def create_db_engine(url: str):
    """Create SQLAlchemy engine with connection pooling and timeouts for PostgreSQL or SQLite."""
    cleaned = url.strip()
    if cleaned.startswith("sqlite"):
        return create_engine(
            cleaned,
            connect_args={"check_same_thread": False},
            echo=False
        )
    normalized_url = normalize_postgres_url(cleaned)
    if not (normalized_url.startswith("postgresql://") or normalized_url.startswith("postgresql+")):
        raise ValueError(f"Invalid DATABASE_URL scheme for '{url}'. Supported schemes are postgresql and sqlite.")

    return create_engine(
        normalized_url,
        connect_args={"connect_timeout": 5},
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        echo=False
    )


# Initialize database engine & SessionLocal
engine = create_db_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class AuthorizationRecord(Base):
    """SQLAlchemy ORM model for authorization predictions & hybrid risk evaluations."""
    __tablename__ = "authorization_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    auth_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    batch_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    timestamp: Mapped[Optional[datetime]] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    # Base input summary
    ml_req_units: Mapped[float] = mapped_column(Float, default=0.0)
    ml_aprvd_units: Mapped[float] = mapped_column(Float, default=0.0)
    ml_latency_hours: Mapped[float] = mapped_column(Float, default=0.0)
    ml_bene_age: Mapped[float] = mapped_column(Float, default=0.0)
    ml_prov_partd_cost: Mapped[float] = mapped_column(Float, default=0.0)

    # ML Inference Results
    prediction: Mapped[str] = mapped_column(String(16), nullable=False)        # "NORMAL" or "ANOMALY"
    probability: Mapped[float] = mapped_column(Float, nullable=False)            # 0.0 to 1.0
    ml_risk_level: Mapped[str] = mapped_column(String(16), nullable=False)      # "LOW", "MEDIUM", "HIGH", "CRITICAL"

    # Business Rules & SLA Evaluation
    rule_violations_count: Mapped[int] = mapped_column(Integer, default=0)
    sla_risk: Mapped[str] = mapped_column(String(16), nullable=False)           # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    final_priority: Mapped[str] = mapped_column(String(16), nullable=False)     # "LOW", "MEDIUM", "HIGH", "CRITICAL"

    # Explanations & Performance
    reasons_json: Mapped[Optional[str]] = mapped_column(Text, default="[]")
    inference_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)

    @property
    def reasons(self) -> List[str]:
        try:
            return json.loads(str(self.reasons_json or "[]"))
        except Exception:
            return []

    @reasons.setter
    def reasons(self, val: List[str]):
        self.reasons_json = json.dumps(val or [])

    def to_dict(self) -> Dict[str, Any]:
        ts_val = self.timestamp
        return {
            "id": self.id,
            "auth_id": self.auth_id,
            "batch_id": self.batch_id,
            "timestamp": ts_val.isoformat() if ts_val is not None else None,
            "ml_req_units": self.ml_req_units,
            "ml_aprvd_units": self.ml_aprvd_units,
            "ml_latency_hours": self.ml_latency_hours,
            "ml_bene_age": self.ml_bene_age,
            "ml_prov_partd_cost": self.ml_prov_partd_cost,
            "prediction": self.prediction,
            "probability": self.probability,
            "risk_level": self.ml_risk_level,
            "rule_violations_count": self.rule_violations_count,
            "sla_risk": self.sla_risk,
            "final_priority": self.final_priority,
            "reasons": self.reasons,
            "inference_latency_ms": self.inference_latency_ms,
        }


class BatchUploadRecord(Base):
    """SQLAlchemy ORM model for distinct file upload analysis batches."""
    __tablename__ = "batch_upload_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    batch_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(256), nullable=False)
    uploaded_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    total_records: Mapped[int] = mapped_column(Integer, default=0)
    normal_count: Mapped[int] = mapped_column(Integer, default=0)
    anomaly_count: Mapped[int] = mapped_column(Integer, default=0)
    anomaly_rate: Mapped[float] = mapped_column(Float, default=0.0)
    priority_low: Mapped[int] = mapped_column(Integer, default=0)
    priority_medium: Mapped[int] = mapped_column(Integer, default=0)
    priority_high: Mapped[int] = mapped_column(Integer, default=0)
    priority_critical: Mapped[int] = mapped_column(Integer, default=0)
    avg_inference_latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    summary_json: Mapped[Optional[str]] = mapped_column(Text, default="{}")

    def to_dict(self) -> Dict[str, Any]:
        ts_val = self.uploaded_at
        return {
            "id": self.id,
            "batch_id": self.batch_id,
            "filename": self.filename,
            "uploaded_at": ts_val.isoformat() if ts_val is not None else None,
            "total_records": self.total_records,
            "normal_count": self.normal_count,
            "anomaly_count": self.anomaly_count,
            "anomaly_rate": self.anomaly_rate,
            "priority_distribution": {
                "LOW": self.priority_low,
                "MEDIUM": self.priority_medium,
                "HIGH": self.priority_high,
                "CRITICAL": self.priority_critical,
            },
            "avg_inference_latency_ms": self.avg_inference_latency_ms,
        }



class CMSFreshnessRecord(Base):
    """SQLAlchemy ORM model for storing CMS raw dataset ingestion and freshness metadata."""
    __tablename__ = "cms_freshness_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    dataset_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_file: Mapped[str] = mapped_column(String(128), nullable=False)
    reporting_period: Mapped[str] = mapped_column(String(32), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, default=0)
    file_modified_time: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    latest_data_date: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    rows_available: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_evaluated: Mapped[int] = mapped_column(BigInteger, default=0)
    coverage_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    ingestion_duration_ms: Mapped[float] = mapped_column(Float, default=0.0)
    freshness_status: Mapped[str] = mapped_column(String(32), nullable=False)
    audited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self) -> Dict[str, Any]:
        aud_val = self.audited_at
        return {
            "id": self.id,
            "dataset_name": self.dataset_name,
            "source_file": self.source_file,
            "reporting_period": self.reporting_period,
            "file_size_bytes": self.file_size_bytes,
            "file_modified_time": self.file_modified_time,
            "latest_data_date": self.latest_data_date,
            "rows_available": self.rows_available,
            "rows_evaluated": self.rows_evaluated,
            "coverage_percentage": self.coverage_percentage,
            "ingestion_duration_ms": self.ingestion_duration_ms,
            "freshness_status": self.freshness_status,
            "audited_at": aud_val.isoformat() if aud_val is not None else None,
        }


class CMSCrossDomainRecord(Base):
    """SQLAlchemy ORM model for storing CMS cross-domain consistency evaluation results."""
    __tablename__ = "cms_cross_domain_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    check_name: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    source_dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    target_dataset: Mapped[str] = mapped_column(String(64), nullable=False)
    key_relationship_used: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(64), default="INFORMATIONAL")
    evaluation_mode: Mapped[str] = mapped_column(String(32), default="SAMPLE")
    rows_available: Mapped[int] = mapped_column(BigInteger, default=0)
    rows_evaluated: Mapped[int] = mapped_column(BigInteger, default=0)
    coverage_percentage: Mapped[float] = mapped_column(Float, default=0.0)
    records_checked: Mapped[int] = mapped_column(BigInteger, default=0)
    actionable_violations: Mapped[int] = mapped_column(BigInteger, default=0)
    expected_differences: Mapped[int] = mapped_column(BigInteger, default=0)
    informational_findings: Mapped[int] = mapped_column(BigInteger, default=0)
    violation_rate: Mapped[float] = mapped_column(Float, default=0.0)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    audited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self) -> Dict[str, Any]:
        aud_val = self.audited_at
        return {
            "id": self.id,
            "check_name": self.check_name,
            "source_dataset": self.source_dataset,
            "target_dataset": self.target_dataset,
            "key_relationship_used": self.key_relationship_used,
            "status": self.status,
            "finding_type": self.finding_type,
            "evaluation_mode": self.evaluation_mode,
            "rows_available": self.rows_available,
            "rows_evaluated": self.rows_evaluated,
            "coverage_percentage": self.coverage_percentage,
            "records_checked": self.records_checked,
            "actionable_violations": self.actionable_violations,
            "expected_differences": self.expected_differences,
            "informational_findings": self.informational_findings,
            "violation_rate": self.violation_rate,
            "severity": self.severity,
            "explanation": self.explanation,
            "audited_at": aud_val.isoformat() if aud_val is not None else None,
        }


class CMSDecisionImpactRecord(Base):
    """SQLAlchemy ORM model for decision impact mapping results."""
    __tablename__ = "decision_impact_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    impact_area: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    source_issue: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    recommended_action: Mapped[str] = mapped_column(Text, nullable=False)
    audited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self) -> Dict[str, Any]:
        aud_val = self.audited_at
        return {
            "id": self.id,
            "impact_area": self.impact_area,
            "severity": self.severity,
            "source_issue": self.source_issue,
            "reason": self.reason,
            "confidence_score": self.confidence_score,
            "recommended_action": self.recommended_action,
            "audited_at": aud_val.isoformat() if aud_val is not None else None,
        }


class CMSCareManagementSignalRecord(Base):
    """SQLAlchemy ORM model for operational care management utilization signals."""
    __tablename__ = "care_management_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    beneficiary_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_review: Mapped[str] = mapped_column(Text, nullable=False)
    audited_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self) -> Dict[str, Any]:
        aud_val = self.audited_at
        return {
            "id": self.id,
            "beneficiary_id": self.beneficiary_id,
            "signal_type": self.signal_type,
            "severity": self.severity,
            "evidence": self.evidence,
            "recommended_review": self.recommended_review,
            "audited_at": aud_val.isoformat() if aud_val is not None else None,
        }


class AuditCacheRecord(Base):
    """SQLAlchemy ORM model for persisting completed CMS audit reports (DQ, Freshness, Cross-Domain, Care Mgmt, Decision Impact)."""
    __tablename__ = "audit_cache_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    report_type: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    source_mtime_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self) -> Dict[str, Any]:
        data = json.loads(str(self.report_json)) if self.report_json else {}
        gen_val = self.generated_at
        data["_cached_metadata"] = {
            "cached": True,
            "generated_at": gen_val.isoformat() if gen_val is not None else None,
            "source_mtime_hash": self.source_mtime_hash
        }
        return data


def get_audit_cache(db: Session, report_type: str) -> Optional[Dict[str, Any]]:
    """Retrieve persisted audit report cache from database."""
    try:
        rec = db.query(AuditCacheRecord).filter(AuditCacheRecord.report_type == report_type).first()
        if rec:
            return rec.to_dict()
    except Exception as err:
        print(f"Error querying audit cache for {report_type}: {err}")
    return None


def set_audit_cache(db: Session, report_type: str, data: Dict[str, Any], source_mtime_hash: Optional[str] = None):
    """Persist completed audit report to database cache."""
    try:
        rec = db.query(AuditCacheRecord).filter(AuditCacheRecord.report_type == report_type).first()
        if not rec:
            rec = AuditCacheRecord(
                report_type=report_type,
                report_json=json.dumps(data),
                source_mtime_hash=source_mtime_hash,
                generated_at=datetime.now(timezone.utc)
            )
            db.add(rec)
        else:
            rec.report_json = json.dumps(data)
            rec.source_mtime_hash = source_mtime_hash
            rec.generated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as err:
        db.rollback()
        print(f"Error persisting audit cache for {report_type}: {err}")


def init_db():
    """Initialize database tables, falling back to SQLite if PostgreSQL is unreachable, and ensure schema migrations."""
    global engine, SessionLocal
    try:
        Base.metadata.create_all(bind=engine)
    except Exception as err:
        if not os.getenv("DATABASE_URL") or "localhost:5432" in str(engine.url) or "127.0.0.1:5432" in str(engine.url):
            print(f"[Database] PostgreSQL unavailable ({err}). Falling back to local SQLite database (final_anomaly.db)...")
            engine = create_engine("sqlite:///final_anomaly.db", connect_args={"check_same_thread": False})
            SessionLocal.configure(bind=engine)
            Base.metadata.create_all(bind=engine)
        else:
            raise err

    # Ensure batch_id column exists on existing authorization_records tables
    try:
        with engine.connect() as conn:
            if "sqlite" in str(engine.url):
                res = conn.exec_driver_sql("PRAGMA table_info(authorization_records);").fetchall()
                col_names = [r[1] for r in res]
                if col_names and "batch_id" not in col_names:
                    conn.exec_driver_sql("ALTER TABLE authorization_records ADD COLUMN batch_id VARCHAR(64);")
                    conn.commit()
            else:
                conn.exec_driver_sql("ALTER TABLE authorization_records ADD COLUMN IF NOT EXISTS batch_id VARCHAR(64);")
                conn.commit()
    except Exception as e:
        pass




def get_db():
    """Dependency helper for FastAPI session management."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def save_authorization_record(db: Session, record_data: Dict[str, Any]) -> AuthorizationRecord:
    """Save an authorization record to database."""
    reasons_list = record_data.get("reasons", [])
    rec = AuthorizationRecord(
        auth_id=record_data.get("auth_id", "AUTH_UNKNOWN"),
        batch_id=record_data.get("batch_id"),
        timestamp=datetime.now(timezone.utc),
        ml_req_units=float(record_data.get("ml_req_units", 0.0)),
        ml_aprvd_units=float(record_data.get("ml_aprvd_units", 0.0)),
        ml_latency_hours=float(record_data.get("ml_latency_hours", 0.0)),
        ml_bene_age=float(record_data.get("ml_bene_age", 0.0)),
        ml_prov_partd_cost=float(record_data.get("ml_prov_partd_cost", 0.0)),
        prediction=record_data.get("prediction", "NORMAL"),
        probability=float(record_data.get("probability", 0.0)),
        ml_risk_level=record_data.get("risk_level", "LOW"),
        rule_violations_count=int(record_data.get("rule_violations_count", 0)),
        sla_risk=record_data.get("sla_risk", "LOW"),
        final_priority=record_data.get("final_priority", "LOW"),
        reasons_json=json.dumps(reasons_list),
        inference_latency_ms=float(record_data.get("inference_latency_ms", 0.0)),
    )
    db.add(rec)
    db.commit()
    db.refresh(rec)
    return rec


def save_authorization_records_batch(
    db: Session,
    records_list: List[Dict[str, Any]],
    batch_id: Optional[str] = None
) -> List[AuthorizationRecord]:
    """Bulk save authorization records in a single database transaction for high performance."""
    if not records_list:
        return []
    recs = []
    now_ts = datetime.now(timezone.utc)
    for record_data in records_list:
        reasons_list = record_data.get("reasons", [])
        bid = record_data.get("batch_id") or batch_id
        rec = AuthorizationRecord(
            auth_id=str(record_data.get("auth_id", "AUTH_UNKNOWN")),
            batch_id=bid,
            timestamp=now_ts,
            ml_req_units=float(record_data.get("ml_req_units", 0.0)),
            ml_aprvd_units=float(record_data.get("ml_aprvd_units", 0.0)),
            ml_latency_hours=float(record_data.get("ml_latency_hours", 0.0)),
            ml_bene_age=float(record_data.get("ml_bene_age", 0.0)),
            ml_prov_partd_cost=float(record_data.get("ml_prov_partd_cost", 0.0)),
            prediction=str(record_data.get("prediction", "NORMAL")),
            probability=float(record_data.get("probability", 0.0)),
            ml_risk_level=str(record_data.get("risk_level", "LOW")),
            rule_violations_count=int(record_data.get("rule_violations_count", 0)),
            sla_risk=str(record_data.get("sla_risk", "LOW")),
            final_priority=str(record_data.get("final_priority", "LOW")),
            reasons_json=json.dumps(reasons_list),
            inference_latency_ms=float(record_data.get("inference_latency_ms", 0.0)),
        )
        recs.append(rec)
    
    try:
        db.add_all(recs)
        db.commit()
    except Exception as err:
        db.rollback()
        print(f"Error bulk saving authorization records: {err}")
    return recs


def create_batch_upload_record(db: Session, batch_data: Dict[str, Any]) -> BatchUploadRecord:
    """Create and persist a new batch upload metadata record."""
    priority_dist = batch_data.get("priority_distribution", {})
    rec = BatchUploadRecord(
        batch_id=batch_data["batch_id"],
        filename=batch_data.get("filename", "batch_upload.csv"),
        uploaded_at=datetime.now(timezone.utc),
        total_records=int(batch_data.get("total_records", 0)),
        normal_count=int(batch_data.get("normal_count", 0)),
        anomaly_count=int(batch_data.get("anomaly_count", 0)),
        anomaly_rate=float(batch_data.get("anomaly_rate", 0.0)),
        priority_low=int(priority_dist.get("LOW", 0)),
        priority_medium=int(priority_dist.get("MEDIUM", 0)),
        priority_high=int(priority_dist.get("HIGH", 0)),
        priority_critical=int(priority_dist.get("CRITICAL", 0)),
        avg_inference_latency_ms=float(batch_data.get("avg_inference_latency_ms", 0.0)),
        summary_json=json.dumps(batch_data)
    )
    try:
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec
    except Exception as err:
        db.rollback()
        print(f"Error creating batch upload record: {err}")
        return rec


def get_all_batches(db: Session) -> List[BatchUploadRecord]:
    """Retrieve all uploaded batches ordered by most recent first."""
    return db.query(BatchUploadRecord).order_by(BatchUploadRecord.uploaded_at.desc()).all()


def get_latest_batch(db: Session) -> Optional[BatchUploadRecord]:
    """Retrieve the most recent batch upload record."""
    return db.query(BatchUploadRecord).order_by(BatchUploadRecord.uploaded_at.desc()).first()


def get_batch_by_id(db: Session, batch_id: str) -> Optional[BatchUploadRecord]:
    """Retrieve a specific batch upload record by batch_id."""
    return db.query(BatchUploadRecord).filter(BatchUploadRecord.batch_id == batch_id).first()


def delete_batch_record(db: Session, batch_id: str) -> bool:
    """Delete a batch upload record and all associated authorization predictions."""
    try:
        db.query(AuthorizationRecord).filter(AuthorizationRecord.batch_id == batch_id).delete(synchronize_session=False)
        db.query(BatchUploadRecord).filter(BatchUploadRecord.batch_id == batch_id).delete(synchronize_session=False)
        db.commit()
        return True
    except Exception as err:
        db.rollback()
        print(f"Error deleting batch {batch_id}: {err}")
        return False




def save_cms_freshness_records(db: Session, reports_dict: Dict[str, Any]):
    """Persist CMS dataset freshness audit metadata into database."""
    try:
        for name, data in reports_dict.items():
            rec = CMSFreshnessRecord(
                dataset_name=data.get("dataset_name", name),
                source_file=data.get("source_file", "unknown"),
                reporting_period=data.get("reporting_period", "N/A"),
                file_size_bytes=int(data.get("file_size_bytes", 0)),
                file_modified_time=data.get("file_modified_time"),
                latest_data_date=data.get("latest_data_date"),
                rows_available=int(data.get("rows_available", 0)),
                rows_evaluated=int(data.get("rows_evaluated", 0)),
                coverage_percentage=float(data.get("coverage_percentage", 0.0)),
                ingestion_duration_ms=float(data.get("ingestion_duration_ms", 0.0)),
                freshness_status=data.get("freshness_status", "AVAILABLE"),
                audited_at=datetime.now(timezone.utc)
            )
            db.add(rec)
        db.commit()
    except Exception as err:
        db.rollback()
        print(f"Error persisting freshness metadata: {err}")


def save_cms_cross_domain_records(db: Session, checks_list: List[Dict[str, Any]]):
    """Persist CMS cross-domain audit check results into PostgreSQL database."""
    try:
        for check in checks_list:
            rec = CMSCrossDomainRecord(
                check_name=check.get("check_name", "UNKNOWN"),
                source_dataset=check.get("source_dataset", "unknown"),
                target_dataset=check.get("target_dataset", "unknown"),
                key_relationship_used=check.get("key_relationship_used", "N/A"),
                status=check.get("status", "PERFORMED"),
                finding_type=check.get("finding_type", "INFORMATIONAL"),
                evaluation_mode=check.get("evaluation_mode", "SAMPLE"),
                rows_available=int(check.get("rows_available", 0)),
                rows_evaluated=int(check.get("rows_evaluated", 0)),
                coverage_percentage=float(check.get("coverage_percentage", 0.0)),
                records_checked=int(check.get("records_checked", 0)),
                actionable_violations=int(check.get("actionable_violations", 0)),
                expected_differences=int(check.get("expected_differences", 0)),
                informational_findings=int(check.get("informational_findings", 0)),
                violation_rate=float(check.get("violation_rate", 0.0)),
                severity=check.get("severity", "LOW"),
                explanation=check.get("explanation", ""),
                audited_at=datetime.now(timezone.utc)
            )
            db.add(rec)
        db.commit()
    except Exception as err:
        db.rollback()
        print(f"Error persisting cross-domain check records: {err}")


def save_cms_decision_impact_records(db: Session, impacts_list: List[Dict[str, Any]]):
    """Persist downstream decision impact records into PostgreSQL database."""
    try:
        for imp in impacts_list:
            rec = CMSDecisionImpactRecord(
                impact_area=imp.get("impact_area", "CLAIMS_ANALYTICS"),
                severity=imp.get("severity", "LOW"),
                source_issue=imp.get("source_issue", "unknown"),
                reason=imp.get("reason", ""),
                confidence_score=float(imp.get("confidence_score", 1.0)),
                recommended_action=imp.get("recommended_action", ""),
                audited_at=datetime.now(timezone.utc)
            )
            db.add(rec)
        db.commit()
    except Exception as err:
        db.rollback()
        print(f"Error persisting decision impact records: {err}")


def save_cms_care_management_signals(db: Session, signals_list: List[Dict[str, Any]]):
    """Persist care management signal records into PostgreSQL database."""
    try:
        for sig in signals_list:
            rec = CMSCareManagementSignalRecord(
                beneficiary_id=sig.get("beneficiary_id", "UNKNOWN"),
                signal_type=sig.get("signal_type", "HIGH_UTILIZATION"),
                severity=sig.get("severity", "LOW"),
                evidence=sig.get("evidence", ""),
                recommended_review=sig.get("recommended_review", ""),
                audited_at=datetime.now(timezone.utc)
            )
            db.add(rec)
        db.commit()
    except Exception as err:
        db.rollback()
        print(f"Error persisting care management signals: {err}")


class LLMExplanationRecord(Base):
    """SQLAlchemy ORM model for storing evidence-grounded LLM explanations."""
    __tablename__ = "llm_explanation_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    issue_type: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    reference_id: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    provider: Mapped[str] = mapped_column(String(32), default="ollama")
    model: Mapped[str] = mapped_column(String(64), default="llama3.2:3b")
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    likely_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    business_impact: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    recommended_fix: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    evidence_used_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)

    def to_dict(self) -> Dict[str, Any]:
        cr_val = self.created_at
        ev_json = self.evidence_used_json
        return {
            "id": self.id,
            "issue_type": self.issue_type,
            "reference_id": self.reference_id,
            "provider": self.provider,
            "model": self.model,
            "status": self.status,
            "likely_cause": self.likely_cause,
            "business_impact": self.business_impact,
            "recommended_fix": self.recommended_fix,
            "evidence_used": json.loads(str(ev_json)) if ev_json else [],
            "confidence": self.confidence,
            "latency_ms": self.latency_ms,
            "created_at": cr_val.isoformat() if cr_val is not None else None,
        }


def save_llm_explanation_record(db: Session, res_dict: Dict[str, Any], reference_id: Optional[str] = None) -> Optional[LLMExplanationRecord]:
    """Save an evidence-grounded LLM explanation record to PostgreSQL database."""
    try:
        evidence_list = res_dict.get("evidence_used", [])
        rec = LLMExplanationRecord(
            issue_type=res_dict.get("issue_type", "GENERAL"),
            reference_id=reference_id,
            provider=res_dict.get("provider", "ollama"),
            model=res_dict.get("model", "llama3.2:3b"),
            status=res_dict.get("status", "SUCCESS"),
            likely_cause=res_dict.get("likely_cause"),
            business_impact=res_dict.get("business_impact"),
            recommended_fix=res_dict.get("recommended_fix"),
            evidence_used_json=json.dumps(evidence_list),
            confidence=float(res_dict.get("confidence", 0.0)),
            latency_ms=float(res_dict.get("latency_ms", 0.0)),
            created_at=datetime.now(timezone.utc)
        )
        db.add(rec)
        db.commit()
        db.refresh(rec)
        return rec
    except Exception as err:
        db.rollback()
        print(f"Error persisting LLM explanation record: {err}")
        return None

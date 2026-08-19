import json
import random
import asyncio
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Any, Optional

from fastapi import (
    FastAPI, HTTPException, Depends, UploadFile, File, WebSocket, WebSocketDisconnect, status, Query
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.schemas import (
    PredictionRequest, PredictionResponse, HealthResponse,
    BatchPredictionResponse, PaginatedPredictionsResponse
)
from app.model_service import ModelService
from app.rules import (
    evaluate_business_rules, evaluate_sla_risk, compute_hybrid_risk_priority
)
from app.explainability import generate_explanation_summary
from app.database import (
    init_db, get_db, SessionLocal, save_authorization_record, save_cms_freshness_records,
    save_cms_cross_domain_records, save_cms_decision_impact_records, save_cms_care_management_signals,
    save_llm_explanation_record, AuthorizationRecord, CMSFreshnessRecord, CMSCrossDomainRecord,
    CMSDecisionImpactRecord, CMSCareManagementSignalRecord, LLMExplanationRecord
)
from app.websocket_manager import ws_manager
from app.batch_processor import process_csv_batch
from app.data_quality import CMSDataQualityEngine
from app.freshness import CMSFreshnessEngine, LiveLatencyTracker
from app.cross_domain import CMSCrossDomainEngine
from app.decision_impact import DownstreamDecisionImpactEngine
from app.care_management import CMSCareManagementEngine
from app.llm_service import (
    LLMExplanationService, start_async_explanation, get_async_explanation_status, warmup_ollama_non_blocking
)
from app.cache_service import get_or_compute_report


# Global ModelService singleton instance
model_service: Optional[ModelService] = None


def get_model_service() -> ModelService:
    """Ensure ModelService and Database are initialized."""
    global model_service
    if model_service is None or not model_service.is_loaded:
        init_db()
        model_service = ModelService()
    return model_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan context manager for startup and shutdown initialization."""
    init_db()
    get_model_service()
    warmup_ollama_non_blocking()
    yield


app = FastAPI(
    title="Final Anomaly Detection System API",
    version="2.1.0",
    description="Enterprise ML Inference & Hybrid Risk Decision Engine Backend",
    lifespan=lifespan
)

FRONTEND_DIR = Path(__file__).resolve().parents[2] / "frontend_dist"
FRONTEND_INDEX = FRONTEND_DIR / "index.html"

# Enable CORS for frontend integration (supporting local dev and cloud deployment domains)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"^https?:\/\/.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["Status"])
def root_status():
    """Serve the bundled React application, with a backend-only fallback."""
    if FRONTEND_INDEX.is_file():
        return FileResponse(FRONTEND_INDEX)
    return {
        "status": "online",
        "message": "Final Anomaly Detection System Backend is running successfully.",
        "version": "2.1.0",
        "docs": "/docs",
        "health": "/api/health"
    }


@app.get("/api", tags=["Status"])
@app.get("/api/", tags=["Status"])
def api_root_status():
    """API entry point confirming backend API is running successfully."""
    return {
        "status": "online",
        "message": "Final Anomaly Detection System Backend API is running successfully.",
        "version": "2.1.0",
        "docs": "/docs",
        "health": "/api/health"
    }


@app.get("/health", response_model=HealthResponse, tags=["Status"])
def get_health_root():
    """Root health check alias for cloud orchestrators (e.g. AWS/Render/Railway/GCP)."""
    return get_health()



def execute_full_inference_pipeline(raw_data: Dict[str, Any], db: Optional[Session] = None) -> Dict[str, Any]:
    """
    Unified Inference Pipeline with microsecond LiveLatencyTracker precision timing.
    """
    tracker = LiveLatencyTracker()
    service = get_model_service()
    if not service or not service.is_loaded:
        raise RuntimeError("Model service is not loaded.")

    auth_id = str(raw_data.get("auth_id", "AUTH_001"))
    latency_hours = float(raw_data.get("ml_latency_hours", 0.0))

    # 1. Run Frozen ML Inference (Autoencoder + Logistic Regression)
    tracker.mark_inference_start()
    ml_result = service.predict(raw_data)
    tracker.mark_inference_end()

    ml_prediction = ml_result["prediction"]      # "NORMAL" or "ANOMALY" (threshold = 0.81)
    ml_probability = ml_result["probability"]    # 0.0 to 1.0
    ml_risk_level = ml_result["risk_level"]      # ML risk level

    # 2. Run Business Rules Engine (Domain policy violations)
    rule_codes, rule_reasons = evaluate_business_rules(raw_data)
    rule_violations_count = len(rule_codes)

    # 3. Calculate SLA Urgency (Negative latency handled as CRITICAL)
    sla_risk = evaluate_sla_risk(latency_hours)

    # 4. Compute Hybrid Risk Priority Decision Matrix
    final_priority = compute_hybrid_risk_priority(
        ml_prediction=ml_prediction,
        ml_probability=ml_probability,
        rule_violations_count=rule_violations_count,
        sla_risk=sla_risk
    )

    # 5. Synthesize Human-Readable Explanations
    reasons = generate_explanation_summary(
        ml_prediction=ml_prediction,
        ml_probability=ml_probability,
        rule_reasons=rule_reasons,
        sla_risk=sla_risk,
        final_priority=final_priority
    )

    # 6. Database Persistence
    if db is not None:
        try:
            save_authorization_record(db, {
                "auth_id": auth_id,
                "ml_req_units": float(raw_data.get("ml_req_units", 0.0)),
                "ml_aprvd_units": float(raw_data.get("ml_aprvd_units", 0.0)),
                "ml_latency_hours": latency_hours,
                "ml_bene_age": float(raw_data.get("ml_bene_age", 0.0)),
                "ml_prov_partd_cost": float(raw_data.get("ml_prov_partd_cost", 0.0)),
                "prediction": ml_prediction,
                "probability": ml_probability,
                "risk_level": ml_risk_level,
                "rule_violations_count": rule_violations_count,
                "sla_risk": sla_risk,
                "final_priority": final_priority,
                "reasons": reasons,
                "inference_latency_ms": ml_result["inference_latency_ms"],
            })
            tracker.mark_db_persisted()
        except Exception as err:
            print(f"Error persisting record to database: {err}")

    timing_info = tracker.get_timing_summary()

    response_payload = {
        "auth_id": auth_id,
        "prediction": ml_prediction,
        "probability": ml_probability,
        "risk_level": ml_risk_level,
        "sla_risk": sla_risk,
        "rule_violations_count": rule_violations_count,
        "final_priority": final_priority,
        "reasons": reasons,
        "inference_latency_ms": timing_info["inference_duration_ms"],
        "end_to_end_latency_ms": timing_info["end_to_end_latency_ms"],
        "timing": timing_info,
        "ml_req_units": float(raw_data.get("ml_req_units", 0.0)),
        "ml_aprvd_units": float(raw_data.get("ml_aprvd_units", 0.0)),
        "ml_latency_hours": latency_hours,
        "ml_bene_age": float(raw_data.get("ml_bene_age", 0.0)),
        "ml_prov_partd_cost": float(raw_data.get("ml_prov_partd_cost", 0.0)),
    }

    return response_payload


@app.get("/api/health", response_model=HealthResponse)
def get_health():
    """Health check reporting service status, model load state, feature count, threshold, and model name."""
    service = get_model_service()
    is_loaded = service.is_loaded if service else False
    feature_count = service.config.get("input_dim", 25) if service else 25
    threshold = service.config.get("threshold", 0.81) if service else 0.81
    model_name = service.config.get("model", "Autoencoder + Logistic Regression") if service else "Autoencoder + Logistic Regression"

    return HealthResponse(
        status="ok",
        model_loaded=is_loaded,
        feature_count=feature_count,
        threshold=threshold,
        model_name=model_name
    )


@app.post("/api/predict", response_model=PredictionResponse)
async def predict(request: PredictionRequest, db: Session = Depends(get_db)):
    """Single authorization real-time inference endpoint with DB persistence and WebSocket broadcast."""
    try:
        raw_data = request.model_dump()
        result = execute_full_inference_pipeline(raw_data, db=db)

        # Broadcast live stream update via WebSockets
        asyncio.create_task(ws_manager.broadcast({
            "event_type": "NEW_PREDICTION",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": result
        }))

        return PredictionResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Inference pipeline execution error: {str(e)}"
        )


@app.post("/api/stream/simulate")
async def simulate_stream_event(db: Session = Depends(get_db)):
    """Simulate a real-time authorization event for live streaming demo."""
    try:
        is_anomaly = random.choice([True, False])
        sample_payload = {
            "auth_id": f"SIM_{random.randint(10000, 99999)}",
            "ml_req_units": 180.0 if is_anomaly else round(random.uniform(1.0, 5.0), 1),
            "ml_aprvd_units": 1.0 if is_anomaly else round(random.uniform(1.0, 5.0), 1),
            "ml_units_diff": 179.0 if is_anomaly else 0.0,
            "ml_units_ratio": 180.0 if is_anomaly else 1.0,
            "ml_latency_hours": 780.0 if is_anomaly else round(random.uniform(1.0, 24.0), 1),
            "ml_bene_carrier_cnt": round(random.uniform(1.0, 5.0), 1),
            "ml_bene_outpatient_cnt": round(random.uniform(0.0, 3.0), 1),
            "ml_bene_pde_cnt": round(random.uniform(1.0, 10.0), 1),
            "ml_bene_total_utilization": 120.0 if is_anomaly else round(random.uniform(5.0, 30.0), 1),
            "ml_bene_gender": 1.0,
            "ml_bene_race": 1.0,
            "ml_bene_age": round(random.uniform(60.0, 85.0), 1),
            "ml_prov_partd_clms": 100.0 if is_anomaly else round(random.uniform(10.0, 50.0), 1),
            "ml_prov_partd_cost": 25000.0 if is_anomaly else round(random.uniform(100.0, 1000.0), 2),
            "ml_prov_avg_cost_per_clm": 600.0 if is_anomaly else round(random.uniform(10.0, 80.0), 2),
            "has_partd_provider_match": 0.0 if is_anomaly else 1.0
        }

        result = execute_full_inference_pipeline(sample_payload, db=db)

        # Broadcast live stream update via WebSockets
        await ws_manager.broadcast({
            "event_type": "NEW_PREDICTION",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": result
        })

        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Simulation error: {str(e)}"
        )


@app.post("/api/batch-predict", response_model=BatchPredictionResponse)
async def batch_predict(file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Batch authorization CSV upload ingestion endpoint using exact same inference pipeline."""
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")

    try:
        contents = await file.read()
        summary, results = process_csv_batch(
            csv_bytes=contents,
            pipeline_func=execute_full_inference_pipeline,
            db=db
        )

        # Broadcast batch completion notification to live stream
        await ws_manager.broadcast({
            "event_type": "BATCH_COMPLETED",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary
        })

        return BatchPredictionResponse(summary=summary, results=results)  # type: ignore
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CSV Batch Processing Error: {str(e)}")


@app.get("/api/predictions", response_model=PaginatedPredictionsResponse)
def get_predictions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    priority: Optional[str] = None,
    prediction: Optional[str] = None,
    db: Session = Depends(get_db)
):
    """Retrieve historical authorization predictions from database."""
    query = db.query(AuthorizationRecord)
    if priority:
        query = query.filter(AuthorizationRecord.final_priority == priority.upper())
    if prediction:
        query = query.filter(AuthorizationRecord.prediction == prediction.upper())

    total = query.count()
    items = query.order_by(AuthorizationRecord.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    total_pages = (total + page_size - 1) // page_size if total > 0 else 0

    return PaginatedPredictionsResponse(
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
        items=[item.to_dict() for item in items]
    )


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    """Retrieve aggregated stats for dashboard cards & charts."""
    total = db.query(AuthorizationRecord).count()
    normal_count = db.query(AuthorizationRecord).filter(AuthorizationRecord.prediction == "NORMAL").count()
    anomaly_count = db.query(AuthorizationRecord).filter(AuthorizationRecord.prediction == "ANOMALY").count()

    priorities = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    for prio in priorities.keys():
        priorities[prio] = db.query(AuthorizationRecord).filter(AuthorizationRecord.final_priority == prio).count()

    freshness_records_cnt = db.query(CMSFreshnessRecord).count()
    cross_domain_cnt = db.query(CMSCrossDomainRecord).count()
    decision_impact_cnt = db.query(CMSDecisionImpactRecord).count()
    care_signals_cnt = db.query(CMSCareManagementSignalRecord).count()

    return {
        "total_requests": total,
        "normal_count": normal_count,
        "anomaly_count": anomaly_count,
        "anomaly_rate": round(anomaly_count / total, 4) if total > 0 else 0.0,
        "priority_distribution": priorities,
        "cms_freshness": {
            "audited_datasets_count": freshness_records_cnt,
            "status": "AVAILABLE" if freshness_records_cnt > 0 else "PENDING_AUDIT"
        },
        "cross_domain_consistency": {
            "audited_checks_count": cross_domain_cnt,
            "status": "AUDITED" if cross_domain_cnt > 0 else "PENDING_AUDIT"
        },
        "business_impact": {
            "decision_impact_records_count": decision_impact_cnt,
            "care_management_signals_count": care_signals_cnt,
            "status": "ACTIVE" if (decision_impact_cnt > 0 or care_signals_cnt > 0) else "PENDING_AUDIT"
        }
    }


# ============================================================================
# PHASE 5.1 — CACHED AUDIT & REFRESH ENDPOINTS
# ============================================================================

@app.get("/api/data-quality/report")
def get_data_quality_report(
    max_chunks: int = Query(default=3, ge=1, le=10),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db)
):
    """Retrieve structured data quality analysis report (with PostgreSQL caching)."""
    mc = int(max_chunks)
    fr = bool(force_refresh)

    def _compute():
        dq_engine = CMSDataQualityEngine()
        return dq_engine.generate_full_report(chunksize=10000, max_chunks_per_file=mc)

    try:
        return get_or_compute_report(db, "DATA_QUALITY", _compute, force_refresh=fr)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data quality analysis error: {str(e)}"
        )


@app.post("/api/data-quality/refresh")
def refresh_data_quality_report(
    max_chunks: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db)
):
    """Explicitly recompute and refresh the Data Quality audit report in PostgreSQL cache."""
    mc = int(max_chunks)
    return get_data_quality_report(max_chunks=mc, force_refresh=True, db=db)


@app.get("/api/freshness/report")
def get_freshness_report(
    max_chunks: int = Query(default=3, ge=1, le=10),
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db)
):
    """Retrieve data freshness and ingestion timing report (with PostgreSQL caching)."""
    mc = int(max_chunks)
    fr = bool(force_refresh)

    def _compute():
        freshness_engine = CMSFreshnessEngine()
        report = freshness_engine.generate_full_freshness_report(chunksize=10000, max_chunks_per_file=mc)
        save_cms_freshness_records(db, report["datasets"])
        return report

    try:
        return get_or_compute_report(db, "FRESHNESS", _compute, force_refresh=fr)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Data freshness audit error: {str(e)}"
        )


@app.post("/api/freshness/refresh")
def refresh_freshness_report(
    max_chunks: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db)
):
    """Explicitly recompute and refresh Freshness audit report in PostgreSQL cache."""
    mc = int(max_chunks)
    return get_freshness_report(max_chunks=mc, force_refresh=True, db=db)


@app.get("/api/cross-domain/report")
def get_cross_domain_report(
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db)
):
    """Retrieve cross-domain consistency audit report (with PostgreSQL caching)."""
    fr = bool(force_refresh)

    def _compute():
        cross_domain_engine = CMSCrossDomainEngine()
        report = cross_domain_engine.run_all_checks()
        save_cms_cross_domain_records(db, report["checks"])
        return report

    try:
        return get_or_compute_report(db, "CROSS_DOMAIN", _compute, force_refresh=fr)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Cross-domain consistency audit error: {str(e)}"
        )


@app.post("/api/cross-domain/refresh")
def refresh_cross_domain_report(db: Session = Depends(get_db)):
    """Explicitly recompute and refresh Cross-Domain audit report in PostgreSQL cache."""
    return get_cross_domain_report(force_refresh=True, db=db)


@app.get("/api/decision-impact/report")
def get_decision_impact_report(
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db)
):
    """Retrieve downstream decision impact analysis report (with PostgreSQL caching)."""
    fr = bool(force_refresh)

    def _compute():
        dq_engine = CMSDataQualityEngine()
        dq_report = dq_engine.generate_full_report(chunksize=10000, max_chunks_per_file=1)

        f_engine = CMSFreshnessEngine()
        f_report = f_engine.generate_full_freshness_report(chunksize=10000, max_chunks_per_file=1)

        cd_engine = CMSCrossDomainEngine()
        cd_report = cd_engine.run_all_checks()

        impact_engine = DownstreamDecisionImpactEngine()
        report = impact_engine.generate_full_impact_report(
            data_quality_report=dq_report,
            freshness_report=f_report,
            cross_domain_report=cd_report
        )

        save_cms_decision_impact_records(db, report["impacts"])
        return report

    try:
        return get_or_compute_report(db, "DECISION_IMPACT", _compute, force_refresh=fr)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Decision impact analysis error: {str(e)}"
        )


@app.post("/api/decision-impact/refresh")
def refresh_decision_impact_report(db: Session = Depends(get_db)):
    """Explicitly recompute and refresh Decision Impact report in PostgreSQL cache."""
    return get_decision_impact_report(force_refresh=True, db=db)


@app.get("/api/care-management/signals")
def get_care_management_signals(
    force_refresh: bool = Query(default=False),
    db: Session = Depends(get_db)
):
    """Retrieve operational care management utilization signals (with PostgreSQL caching)."""
    fr = bool(force_refresh)

    def _compute():
        care_engine = CMSCareManagementEngine()
        report = care_engine.extract_care_signals(max_beneficiaries=50)
        save_cms_care_management_signals(db, report["signals"])
        return report

    try:
        return get_or_compute_report(db, "CARE_MANAGEMENT", _compute, force_refresh=fr)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Care management signal extraction error: {str(e)}"
        )


@app.post("/api/care-management/refresh")
def refresh_care_management_signals(db: Session = Depends(get_db)):
    """Explicitly recompute and refresh Care Management signals in PostgreSQL cache."""
    return get_care_management_signals(force_refresh=True, db=db)


@app.get("/api/beneficiary/{beneficiary_id}/decision-context")
def get_beneficiary_decision_context(beneficiary_id: str, db: Session = Depends(get_db)):
    """Retrieve Unified Downstream Decision Context for a specific beneficiary ID."""
    try:
        care_engine = CMSCareManagementEngine()
        result = care_engine.get_beneficiary_decision_context(beneficiary_id)
        return result
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error retrieving beneficiary decision context: {str(e)}"
        )


# ============================================================================
# PHASE 5.1 — ASYNCHRONOUS LLM EXPLANATION ENDPOINTS
# ============================================================================

@app.post("/api/llm/explain")
async def explain_evidence_with_llm(request: Dict[str, Any], db: Session = Depends(get_db)):
    """
    Asynchronous Evidence-Grounded LLM Explanation Endpoint.
    Starts non-blocking background thread and immediately returns {"status": "PROCESSING", "request_id": "..."}.
    """
    issue_type = str(request.get("issue_type", "GENERAL"))
    evidence = request.get("evidence", {})
    reference_id = request.get("reference_id")

    req_id = start_async_explanation(
        issue_type=issue_type,
        evidence=evidence,
        reference_id=reference_id,
        db_session_factory=SessionLocal
    )

    return {
        "status": "PROCESSING",
        "request_id": req_id,
        "message": "Evidence-grounded explanation generation started in background."
    }


@app.post("/api/llm/explain/authorization/{auth_id}")
async def explain_authorization_record(auth_id: str, db: Session = Depends(get_db)):
    """
    Asynchronous Authorization Explanation Endpoint.
    Retrieves verified AuthorizationRecord, launches background Llama 3.2 3B task,
    and returns {"status": "PROCESSING", "request_id": "..."} immediately.
    """
    rec = db.query(AuthorizationRecord).filter(AuthorizationRecord.auth_id == auth_id).first()
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Authorization record with auth_id '{auth_id}' not found in database."
        )

    reasons_list = json.loads(rec.reasons_json) if rec.reasons_json else []

    evidence = {
        "issue_type": "AUTHORIZATION_ANOMALY",
        "auth_id": rec.auth_id,
        "prediction": rec.prediction,
        "probability": rec.probability,
        "threshold": 0.81,
        "ml_risk_level": rec.ml_risk_level,
        "rule_violations_count": rec.rule_violations_count,
        "sla_risk": rec.sla_risk,
        "final_priority": rec.final_priority,
        "existing_reasons": reasons_list,
        "ml_req_units": rec.ml_req_units,
        "ml_aprvd_units": rec.ml_aprvd_units,
        "ml_latency_hours": rec.ml_latency_hours
    }

    req_id = start_async_explanation(
        issue_type="AUTHORIZATION_ANOMALY",
        evidence=evidence,
        reference_id=auth_id,
        db_session_factory=SessionLocal
    )

    return {
        "status": "PROCESSING",
        "request_id": req_id,
        "auth_id": auth_id,
        "message": "Authorization explanation generation started in background."
    }


@app.get("/api/llm/explanation/{request_id}")
def get_llm_explanation_status(request_id: str, db: Session = Depends(get_db)):
    """
    Poll status of an asynchronous LLM explanation request.
    Returns status: 'PROCESSING', 'SUCCESS', or 'LLM_UNAVAILABLE'.
    """
    return get_async_explanation_status(request_id, db=db)


@app.websocket("/ws/live")
async def websocket_live_endpoint(websocket: WebSocket):
    """WebSocket connection endpoint for real-time live dashboard updates."""
    await ws_manager.connect(websocket)
    try:
        await websocket.send_json({
            "event_type": "CONNECTED",
            "message": "Connected to Final Anomaly System Real-Time WebSocket Feed",
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


@app.get("/{frontend_path:path}", include_in_schema=False)
def serve_frontend(frontend_path: str):
    """Serve Vite assets and fall back to index.html for frontend routes."""
    if not FRONTEND_INDEX.is_file():
        raise HTTPException(status_code=404, detail="Frontend build is not available.")

    requested_path = (FRONTEND_DIR / frontend_path).resolve()
    frontend_root = FRONTEND_DIR.resolve()

    if frontend_root not in requested_path.parents and requested_path != frontend_root:
        raise HTTPException(status_code=404, detail="Not found.")

    if requested_path.is_file():
        return FileResponse(requested_path)

    return FileResponse(FRONTEND_INDEX)

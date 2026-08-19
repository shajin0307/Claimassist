from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, model_validator

FORBIDDEN_INFERENCE_FIELDS = {
    "EXPECTED_ANOMALY",
    "EXPECTED_TYPE",
    "IS_ANOMALY",
    "ANOMALY_TYPE",
}


class PredictionRequest(BaseModel):
    auth_id: Optional[str] = Field(default="AUTH_001", description="Unique Authorization ID")
    
    # Base features
    ml_req_units: float = Field(default=1.0, description="Requested units")
    ml_aprvd_units: float = Field(default=1.0, description="Approved units")
    ml_units_diff: Optional[float] = Field(default=None, description="Difference between requested and approved units")
    ml_units_ratio: Optional[float] = Field(default=None, description="Ratio of requested to approved units")
    ml_latency_hours: float = Field(default=0.0, description="Latency in hours")
    ml_bene_carrier_cnt: float = Field(default=0.0, description="Beneficiary carrier count")
    ml_bene_outpatient_cnt: float = Field(default=0.0, description="Beneficiary outpatient count")
    ml_bene_pde_cnt: float = Field(default=0.0, description="Beneficiary PDE count")
    ml_bene_total_utilization: float = Field(default=0.0, description="Beneficiary total utilization")
    ml_bene_gender: float = Field(default=1.0, description="Beneficiary gender code")
    ml_bene_race: float = Field(default=1.0, description="Beneficiary race code")
    ml_bene_age: float = Field(default=65.0, description="Beneficiary age")
    ml_prov_partd_clms: float = Field(default=10.0, description="Provider Part D claims")
    ml_prov_partd_cost: float = Field(default=500.0, description="Provider Part D cost")
    ml_prov_avg_cost_per_clm: float = Field(default=50.0, description="Provider average cost per claim")
    has_partd_provider_match: float = Field(default=1.0, description="Provider match flag (1.0 or 0.0)")

    @model_validator(mode="before")
    @classmethod
    def filter_forbidden_fields(cls, values: Any) -> Any:
        if isinstance(values, dict):
            # Strip forbidden target/ground-truth fields if present in incoming payload
            for field in list(values.keys()):
                if field in FORBIDDEN_INFERENCE_FIELDS or field.upper() in FORBIDDEN_INFERENCE_FIELDS:
                    values.pop(field)
        return values


class PredictionResponse(BaseModel):
    auth_id: str
    prediction: str            # "NORMAL" or "ANOMALY"
    probability: float         # ML probability score (0.0 to 1.0)
    risk_level: str            # ML risk level ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    sla_risk: str              # SLA urgency ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    rule_violations_count: int # Count of triggered business rules
    final_priority: str        # Consolidated priority ("LOW", "MEDIUM", "HIGH", "CRITICAL")
    reasons: List[str]         # Human-readable explanations
    inference_latency_ms: float


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    feature_count: int
    threshold: float
    model_name: str


class BatchPredictionSummary(BaseModel):
    batch_id: Optional[str] = None
    filename: Optional[str] = None
    total_records: int
    normal_count: int
    anomaly_count: int
    anomaly_rate: float
    priority_distribution: Dict[str, int]
    avg_inference_latency_ms: float
    uploaded_at: Optional[str] = None


class BatchPredictionResponse(BaseModel):
    summary: BatchPredictionSummary
    results: List[Dict[str, Any]]



class PaginatedPredictionsResponse(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int
    items: List[Dict[str, Any]]

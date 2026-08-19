import pandas as pd
import numpy as np
from typing import Dict, Any, List, Tuple

FORBIDDEN_FIELDS = {"EXPECTED_ANOMALY", "EXPECTED_TYPE", "IS_ANOMALY", "ANOMALY_TYPE"}

FINAL_FEATURES = [
    "ml_req_units",
    "ml_aprvd_units",
    "ml_units_diff",
    "ml_units_ratio",
    "ml_latency_hours",
    "ml_bene_carrier_cnt",
    "ml_bene_outpatient_cnt",
    "ml_bene_pde_cnt",
    "ml_bene_total_utilization",
    "ml_bene_gender",
    "ml_bene_race",
    "ml_bene_age",
    "ml_prov_partd_clms",
    "ml_prov_partd_cost",
    "ml_prov_avg_cost_per_clm",
    "has_partd_provider_match",
    "f_excessive_units",
    "f_zero_approved",
    "f_negative_latency",
    "f_zero_latency",
    "f_extreme_latency",
    "f_provider_bene_activity",
    "f_provider_cost_intensity",
    "f_provider_mismatch",
    "f_extreme_utilization",
]


def extract_base_features(data: Dict[str, Any]) -> Dict[str, float]:
    """Extract and validate 16 base features while stripping forbidden fields."""
    clean_data = {}
    for key, val in data.items():
        if key in FORBIDDEN_FIELDS or key.upper() in FORBIDDEN_FIELDS:
            continue
        clean_data[key] = val

    req_units = float(clean_data.get("ml_req_units", 1.0))
    aprvd_units = float(clean_data.get("ml_aprvd_units", 1.0))
    
    units_diff = clean_data.get("ml_units_diff")
    if units_diff is None:
        units_diff = req_units - aprvd_units
    else:
        units_diff = float(units_diff)

    units_ratio = clean_data.get("ml_units_ratio")
    if units_ratio is None:
        units_ratio = req_units / (aprvd_units + 1e-5)
    else:
        units_ratio = float(units_ratio)

    base = {
        "ml_req_units": req_units,
        "ml_aprvd_units": aprvd_units,
        "ml_units_diff": units_diff,
        "ml_units_ratio": units_ratio,
        "ml_latency_hours": float(clean_data.get("ml_latency_hours", 0.0)),
        "ml_bene_carrier_cnt": float(clean_data.get("ml_bene_carrier_cnt", 0.0)),
        "ml_bene_outpatient_cnt": float(clean_data.get("ml_bene_outpatient_cnt", 0.0)),
        "ml_bene_pde_cnt": float(clean_data.get("ml_bene_pde_cnt", 0.0)),
        "ml_bene_total_utilization": float(clean_data.get("ml_bene_total_utilization", 0.0)),
        "ml_bene_gender": float(clean_data.get("ml_bene_gender", 1.0)),
        "ml_bene_race": float(clean_data.get("ml_bene_race", 1.0)),
        "ml_bene_age": float(clean_data.get("ml_bene_age", 65.0)),
        "ml_prov_partd_clms": float(clean_data.get("ml_prov_partd_clms", 10.0)),
        "ml_prov_partd_cost": float(clean_data.get("ml_prov_partd_cost", 500.0)),
        "ml_prov_avg_cost_per_clm": float(clean_data.get("ml_prov_avg_cost_per_clm", 50.0)),
        "has_partd_provider_match": float(clean_data.get("has_partd_provider_match", 1.0)),
    }
    return base


def compute_engineered_features(base: Dict[str, float]) -> Tuple[Dict[str, float], List[str]]:
    """Compute the 9 engineered features and generate explanations for active flags."""
    req_units = base["ml_req_units"]
    aprvd_units = base["ml_aprvd_units"]
    units_diff = base["ml_units_diff"]
    units_ratio = base["ml_units_ratio"]
    latency = base["ml_latency_hours"]
    utilization = base["ml_bene_total_utilization"]
    prov_clms = base["ml_prov_partd_clms"]
    prov_cost = base["ml_prov_partd_cost"]
    prov_match = base["has_partd_provider_match"]

    reasons = []

    # 1. Excessive units
    f_excessive_units = 1.0 if (req_units > 100.0 or units_diff > 50.0 or units_ratio > 3.0) else 0.0
    if f_excessive_units == 1.0:
        reasons.append("Requested units significantly exceed approved baseline.")

    # 2. Zero approved
    f_zero_approved = 1.0 if (aprvd_units == 0.0 and req_units > 0.0) else 0.0
    if f_zero_approved == 1.0:
        reasons.append("Approved units are zero for a non-zero requested unit authorization.")

    # 3. Negative latency
    f_negative_latency = 1.0 if (latency < 0.0) else 0.0
    if f_negative_latency == 1.0:
        reasons.append("Negative latency detected in timestamps.")

    # 4. Zero latency
    f_zero_latency = 1.0 if (latency == 0.0) else 0.0
    if f_zero_latency == 1.0:
        reasons.append("Instantaneous zero-latency processing detected.")

    # 5. Extreme latency
    f_extreme_latency = 1.0 if (latency > 720.0) else 0.0
    if f_extreme_latency == 1.0:
        reasons.append("Extreme authorization latency exceeding 30 days (720 hours).")

    # 6. Provider beneficiary activity
    f_provider_bene_activity = prov_clms / (utilization + 1.0)

    # 7. Provider cost intensity
    f_provider_cost_intensity = prov_cost / (prov_clms + 1.0)

    # 8. Provider mismatch
    f_provider_mismatch = 1.0 if (prov_match == 0.0) else 0.0
    if f_provider_mismatch == 1.0:
        reasons.append("Part D provider record mismatch.")

    # 9. Extreme utilization
    f_extreme_utilization = 1.0 if (utilization > 100.0) else 0.0
    if f_extreme_utilization == 1.0:
        reasons.append("Extreme beneficiary total utilization count.")

    engineered = {
        "f_excessive_units": f_excessive_units,
        "f_zero_approved": f_zero_approved,
        "f_negative_latency": f_negative_latency,
        "f_zero_latency": f_zero_latency,
        "f_extreme_latency": f_extreme_latency,
        "f_provider_bene_activity": f_provider_bene_activity,
        "f_provider_cost_intensity": f_provider_cost_intensity,
        "f_provider_mismatch": f_provider_mismatch,
        "f_extreme_utilization": f_extreme_utilization,
    }

    return engineered, reasons


def prepare_feature_dataframe(data: Dict[str, Any]) -> Tuple[pd.DataFrame, List[str]]:
    """Transform raw dictionary data into 25-feature DataFrame ordered as in feature_config_final.json."""
    base = extract_base_features(data)
    engineered, reasons = compute_engineered_features(base)

    all_features = {**base, **engineered}
    df = pd.DataFrame([all_features])[FINAL_FEATURES]
    return df, reasons

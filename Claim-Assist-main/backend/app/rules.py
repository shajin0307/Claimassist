from dataclasses import dataclass
from typing import Dict, Any, List, Tuple


@dataclass
class BusinessRulesConfig:
    """Configurable business rule thresholds (separate from ML model thresholds)."""
    COST_PER_CLAIM_THRESHOLD: float = 500.0   # High average cost per claim threshold ($)
    TOTAL_COST_THRESHOLD: float = 10000.0     # High total provider Part D cost threshold ($)
    EXCESSIVE_UNIT_RATIO: float = 3.0         # Requested / Approved units ratio threshold
    EXCESSIVE_UNIT_DIFF: float = 50.0         # Requested - Approved units difference threshold
    EXCESSIVE_REQ_UNITS: float = 100.0        # High requested units threshold
    UTILIZATION_THRESHOLD: float = 100.0      # High beneficiary total utilization threshold
    SLA_MEDIUM_HOURS: float = 24.0            # SLA Warning threshold (1 day)
    SLA_HIGH_HOURS: float = 72.0              # SLA Urgent threshold (3 days)
    SLA_CRITICAL_HOURS: float = 168.0         # SLA Breach threshold (7 days)


# Default global rules configuration instance
DEFAULT_RULES_CONFIG = BusinessRulesConfig()


def evaluate_business_rules(
    raw_data: Dict[str, Any],
    config: BusinessRulesConfig = DEFAULT_RULES_CONFIG
) -> Tuple[List[str], List[str]]:
    """
    Evaluate domain business rules independently from ML predictions.
    
    Returns:
        (triggered_rule_codes, human_readable_reasons)
    """
    triggered_rules = []
    reasons = []

    req_units = float(raw_data.get("ml_req_units", 1.0))
    aprvd_units = float(raw_data.get("ml_aprvd_units", 1.0))
    units_diff = raw_data.get("ml_units_diff")
    if units_diff is None:
        units_diff = req_units - aprvd_units
    else:
        units_diff = float(units_diff)

    units_ratio = raw_data.get("ml_units_ratio")
    if units_ratio is None:
        units_ratio = req_units / (aprvd_units + 1e-5)
    else:
        units_ratio = float(units_ratio)

    latency = float(raw_data.get("ml_latency_hours", 0.0))
    prov_match = float(raw_data.get("has_partd_provider_match", 1.0))
    prov_cost = float(raw_data.get("ml_prov_partd_cost", 0.0))
    avg_cost = float(raw_data.get("ml_prov_avg_cost_per_clm", 0.0))
    utilization = float(raw_data.get("ml_bene_total_utilization", 0.0))

    # 1. Excessive Units Rule
    if req_units > config.EXCESSIVE_REQ_UNITS or units_diff > config.EXCESSIVE_UNIT_DIFF or units_ratio > config.EXCESSIVE_UNIT_RATIO:
        triggered_rules.append("R_EXCESSIVE_UNITS")
        reasons.append(f"Business Rule: Requested units ({req_units}) exceed approved baseline or threshold.")

    # 2. Zero Approved Rule
    if aprvd_units == 0.0 and req_units > 0.0:
        triggered_rules.append("R_ZERO_APPROVED")
        reasons.append("Business Rule: Zero approved units for positive requested authorization.")

    # 3. Invalid Negative Latency Rule (System clock / timing error)
    if latency < 0.0:
        triggered_rules.append("R_NEGATIVE_LATENCY")
        reasons.append(f"Business Rule [CRITICAL]: Invalid negative processing latency detected ({latency} hours).")

    # 4. Zero Latency (Logged as info/valid immediate adjudication, NOT marked as anomaly)
    if latency == 0.0:
        triggered_rules.append("R_ZERO_LATENCY_AUTO_ADJUDICATED")

    # 5. Extreme Latency Rule
    if latency > config.SLA_CRITICAL_HOURS:
        triggered_rules.append("R_EXTREME_LATENCY")
        reasons.append(f"Business Rule: Extreme processing latency ({latency} hours) exceeding {config.SLA_CRITICAL_HOURS}h.")

    # 6. Provider Record Mismatch Rule
    if prov_match == 0.0:
        triggered_rules.append("R_PROVIDER_MISMATCH")
        reasons.append("Business Rule: Part D provider match failure detected.")

    # 7. Provider Cost Spike Rule (Configurable business rule)
    if prov_cost > config.TOTAL_COST_THRESHOLD or avg_cost > config.COST_PER_CLAIM_THRESHOLD:
        triggered_rules.append("R_COST_SPIKE")
        reasons.append(f"Business Rule: Provider cost intensity exceeds threshold (Cost: ${prov_cost:,.2f}, Avg/Claim: ${avg_cost:,.2f}).")

    # 8. Extreme Utilization Rule
    if utilization > config.UTILIZATION_THRESHOLD:
        triggered_rules.append("R_EXTREME_UTILIZATION")
        reasons.append(f"Business Rule: Beneficiary utilization ({utilization}) exceeds threshold.")

    return triggered_rules, reasons


def evaluate_sla_risk(latency_hours: float, config: BusinessRulesConfig = DEFAULT_RULES_CONFIG) -> str:
    """
    Calculate SLA / time-in-queue risk rating.
    
    Negative latency is treated as an invalid/CRITICAL condition.
    """
    if latency_hours < 0.0:
        return "CRITICAL"
    elif latency_hours < config.SLA_MEDIUM_HOURS:
        return "LOW"
    elif latency_hours < config.SLA_HIGH_HOURS:
        return "MEDIUM"
    elif latency_hours < config.SLA_CRITICAL_HOURS:
        return "HIGH"
    else:
        return "CRITICAL"


def compute_hybrid_risk_priority(
    ml_prediction: str,
    ml_probability: float,
    rule_violations_count: int,
    sla_risk: str
) -> str:
    """
    Hybrid Risk Engine Decision Matrix.
    
    Independently combines ML anomaly classification with domain business rules and SLA urgency.
    ML prediction remains separate from final business priority.
    """
    # Critical overrides
    if sla_risk == "CRITICAL" or ml_probability >= 0.95 or (ml_prediction == "ANOMALY" and rule_violations_count >= 2):
        return "CRITICAL"

    # High priority conditions
    if ml_prediction == "ANOMALY" or rule_violations_count >= 2 or sla_risk == "HIGH":
        return "HIGH"

    # Medium priority conditions
    if ml_probability >= 0.50 or rule_violations_count == 1 or sla_risk == "MEDIUM":
        return "MEDIUM"

    return "LOW"

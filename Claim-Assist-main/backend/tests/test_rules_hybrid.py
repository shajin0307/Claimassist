import pytest
from app.rules import (
    BusinessRulesConfig, evaluate_business_rules, evaluate_sla_risk, compute_hybrid_risk_priority
)


def test_business_rules_evaluation():
    """Test business rules evaluation and configurable threshold constants."""
    config = BusinessRulesConfig()

    # Sample input triggering excessive units and cost spike
    data = {
        "ml_req_units": 200.0,
        "ml_aprvd_units": 10.0,
        "ml_latency_hours": 10.0,
        "ml_prov_partd_cost": 15000.0,  # > 10,000 threshold
        "ml_prov_avg_cost_per_clm": 600.0, # > 500 threshold
        "has_partd_provider_match": 0.0
    }

    triggered, reasons = evaluate_business_rules(data, config)

    assert "R_EXCESSIVE_UNITS" in triggered
    assert "R_PROVIDER_MISMATCH" in triggered
    assert "R_COST_SPIKE" in triggered
    assert len(reasons) >= 3


def test_negative_latency_is_critical_and_zero_latency_is_not_anomaly():
    """
    Test user constraint:
    - Negative latency is an INVALID/CRITICAL condition.
    - Zero latency is NOT automatically classified as an anomaly.
    """
    config = BusinessRulesConfig()

    # 1. Negative latency
    neg_data = {"ml_latency_hours": -5.0}
    triggered_neg, reasons_neg = evaluate_business_rules(neg_data, config)
    sla_neg = evaluate_sla_risk(-5.0, config)

    assert "R_NEGATIVE_LATENCY" in triggered_neg
    assert sla_neg == "CRITICAL"

    # 2. Zero latency
    zero_data = {"ml_latency_hours": 0.0}
    triggered_zero, reasons_zero = evaluate_business_rules(zero_data, config)
    sla_zero = evaluate_sla_risk(0.0, config)

    assert "R_ZERO_LATENCY_AUTO_ADJUDICATED" in triggered_zero
    assert sla_zero == "LOW"


def test_hybrid_risk_engine_matrix():
    """Test Hybrid Decision Matrix combining ML results, rule count, and SLA urgency."""
    # Case 1: ML = ANOMALY, prob = 0.91, SLA = HIGH, Rule Violations = 2 -> CRITICAL
    prio1 = compute_hybrid_risk_priority(
        ml_prediction="ANOMALY",
        ml_probability=0.91,
        rule_violations_count=2,
        sla_risk="HIGH"
    )
    assert prio1 == "CRITICAL"

    # Case 2: ML = NORMAL, prob = 0.30, SLA = CRITICAL -> CRITICAL (due to SLA breach)
    prio2 = compute_hybrid_risk_priority(
        ml_prediction="NORMAL",
        ml_probability=0.30,
        rule_violations_count=0,
        sla_risk="CRITICAL"
    )
    assert prio2 == "CRITICAL"

    # Case 3: ML = NORMAL, prob = 0.20, SLA = LOW, Rule Violations = 0 -> LOW
    prio3 = compute_hybrid_risk_priority(
        ml_prediction="NORMAL",
        ml_probability=0.20,
        rule_violations_count=0,
        sla_risk="LOW"
    )
    assert prio3 == "LOW"

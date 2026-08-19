from typing import Dict, Any, List


def generate_explanation_summary(
    ml_prediction: str,
    ml_probability: float,
    rule_reasons: List[str],
    sla_risk: str,
    final_priority: str,
    recon_error: float = 0.0
) -> List[str]:
    """
    Synthesize human-readable explanation sentences for operational review.
    """
    reasons = []

    # 1. ML Model Explanation
    if ml_prediction == "ANOMALY":
        reasons.append(f"ML Model: Flagged as ANOMALY with {ml_probability:.1%} probability score (threshold 81.0%).")
        if recon_error > 1.5:
            reasons.append(f"ML Autoencoder: High feature reconstruction error ({recon_error:.2f}) indicates structural pattern divergence.")
    else:
        if ml_probability >= 0.50:
            reasons.append(f"ML Model: Classified as NORMAL, but elevated probability ({ml_probability:.1%}) warrants monitoring.")

    # 2. Business Rules Explanations
    for rule_reason in rule_reasons:
        if rule_reason not in reasons:
            reasons.append(rule_reason)

    # 3. SLA & Queue Urgency Explanation
    if sla_risk == "CRITICAL":
        reasons.append("SLA Status: CRITICAL - Immediate review required due to queue delay or timestamp invalidity.")
    elif sla_risk == "HIGH":
        reasons.append("SLA Status: HIGH - Approaching review deadline threshold.")

    # 4. Final Priority Summary
    reasons.append(f"Decision Matrix: Consolidated final priority assigned as {final_priority}.")

    return reasons

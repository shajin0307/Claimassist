from typing import Dict, Any, List, Optional


class DownstreamDecisionImpactEngine:
    """
    Transparent Rule-Based Downstream Decision Impact Engine.
    Maps data-quality issues, data freshness gaps, cross-domain findings, and ML authorization anomalies
    to potential downstream business impact areas:
    - CLAIMS_ANALYTICS
    - PHARMACY_ANALYTICS
    - QUALITY_ANALYTICS
    - AUTHORIZATION_WORKFLOW
    - CARE_MANAGEMENT
    """

    def __init__(self):
        pass

    def evaluate_decision_impacts(
        self,
        data_quality_report: Optional[Dict[str, Any]] = None,
        freshness_report: Optional[Dict[str, Any]] = None,
        cross_domain_report: Optional[Dict[str, Any]] = None,
        authorization_event: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Evaluate and map findings across system components into structured downstream business impacts.
        """
        impacts: List[Dict[str, Any]] = []

        # 1. Map Data Quality Findings -> Downstream Impact Areas
        if data_quality_report and "datasets" in data_quality_report:
            for d_name, d_data in data_quality_report["datasets"].items():
                overall_score = d_data.get("overall_quality_score", 100.0)
                details = d_data.get("details", {})

                if overall_score < 90.0:
                    impacts.append({
                        "impact_area": "CLAIMS_ANALYTICS" if "Carrier" in d_name or "Outpatient" in d_name else "PHARMACY_ANALYTICS",
                        "severity": "HIGH" if overall_score < 80.0 else "MEDIUM",
                        "source_issue": f"Data Quality Score ({overall_score}%) in {d_name}",
                        "reason": f"High missingness or null rate in {d_name} may affect downstream claim reporting accuracy.",
                        "confidence_score": 0.95,
                        "recommended_action": f"Review data pipeline ingestion rules for {d_name} before publishing analytics dashboards."
                    })

                # Check specific claims or pharmacy quality issues
                if details.get("negative_cost_count", 0) > 0:
                    impacts.append({
                        "impact_area": "CLAIMS_ANALYTICS",
                        "severity": "HIGH",
                        "source_issue": f"Negative Cost Values in {d_name}",
                        "reason": f"Identified {details['negative_cost_count']} negative payment amounts in {d_name}. May skew financial financial reporting.",
                        "confidence_score": 0.98,
                        "recommended_action": "Audit claim billing system for negative charge adjustments."
                    })

        # 2. Map Data Freshness & Timeliness -> Downstream Impact Areas
        if freshness_report and "datasets" in freshness_report:
            for d_name, f_data in freshness_report["datasets"].items():
                status = f_data.get("freshness_status", "AVAILABLE")
                period = f_data.get("reporting_period", "N/A")

                if status != "AVAILABLE":
                    impacts.append({
                        "impact_area": "QUALITY_ANALYTICS",
                        "severity": "HIGH",
                        "source_issue": f"Dataset Unavailable: {d_name}",
                        "reason": f"Source file for {d_name} ({period}) is unavailable. May affect historical HEDIS/quality metrics.",
                        "confidence_score": 0.90,
                        "recommended_action": f"Ensure {d_name} raw file is ingested into primary data warehouse."
                    })

        # 3. Map Cross-Domain Findings -> Downstream Impact Areas
        if cross_domain_report and "checks" in cross_domain_report:
            for check in cross_domain_report["checks"]:
                c_name = check.get("check_name", "")
                f_type = check.get("finding_type", "")
                act_v = check.get("actionable_violations", 0)

                if f_type == "ACTIONABLE_VIOLATION" and act_v > 0:
                    impacts.append({
                        "impact_area": "CARE_MANAGEMENT",
                        "severity": "CRITICAL",
                        "source_issue": f"Cross-Domain Violation: {c_name}",
                        "reason": f"Identified {act_v} actionable cross-domain violations in {c_name}. May affect care management cohort assignment.",
                        "confidence_score": 0.99,
                        "recommended_action": "Perform immediate cross-domain beneficiary record reconciliation."
                    })
                elif f_type == "EXPECTED_DIFFERENCE":
                    impacts.append({
                        "impact_area": "PHARMACY_ANALYTICS",
                        "severity": "LOW",
                        "source_issue": f"Domain Taxonomy Difference: {c_name}",
                        "reason": "Physician claims and Part D prescribers exhibit expected domain taxonomy differences. Review recommended when linking physician vs pharmacy networks.",
                        "confidence_score": 0.85,
                        "recommended_action": "Apply taxonomy-aware mapping filters when correlating medical and pharmacy provider networks."
                    })

        # 4. Map Live Authorization ML & Hybrid Risk Anomalies -> Downstream Impact Areas
        if authorization_event:
            ml_pred = authorization_event.get("prediction", "NORMAL")
            final_prio = authorization_event.get("final_priority", "LOW")
            sla_risk = authorization_event.get("sla_risk", "LOW")

            if ml_pred == "ANOMALY":
                impacts.append({
                    "impact_area": "AUTHORIZATION_WORKFLOW",
                    "severity": "HIGH" if final_prio in ["HIGH", "CRITICAL"] else "MEDIUM",
                    "source_issue": f"ML Anomaly Detected for Authorization {authorization_event.get('auth_id', '')}",
                    "reason": f"ML prediction flagged authorization as ANOMALY with probability {authorization_event.get('probability', 0.0):.4f}. May affect prior-authorization decision speed.",
                    "confidence_score": 0.92,
                    "recommended_action": "Route authorization request to senior clinical reviewer queue for priority audit."
                })

            if final_prio == "CRITICAL":
                impacts.append({
                    "impact_area": "CARE_MANAGEMENT",
                    "severity": "CRITICAL",
                    "source_issue": f"Critical Priority Authorization {authorization_event.get('auth_id', '')}",
                    "reason": f"Combined hybrid risk engine flagged authorization as CRITICAL due to SLA urgency ({sla_risk}) and business rules. Review recommended for urgent care intervention.",
                    "confidence_score": 0.96,
                    "recommended_action": "Initiate immediate high-risk care management case management outreach."
                })

        return impacts

    def generate_full_impact_report(
        self,
        data_quality_report: Optional[Dict[str, Any]] = None,
        freshness_report: Optional[Dict[str, Any]] = None,
        cross_domain_report: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Generate structured Downstream Decision Impact Analysis Report.
        """
        impacts = self.evaluate_decision_impacts(
            data_quality_report=data_quality_report,
            freshness_report=freshness_report,
            cross_domain_report=cross_domain_report
        )

        area_counts = {
            "CLAIMS_ANALYTICS": 0,
            "PHARMACY_ANALYTICS": 0,
            "QUALITY_ANALYTICS": 0,
            "AUTHORIZATION_WORKFLOW": 0,
            "CARE_MANAGEMENT": 0
        }

        for imp in impacts:
            area = imp.get("impact_area")
            if area in area_counts:
                area_counts[area] += 1

        return {
            "summary": {
                "total_downstream_impacts_identified": len(impacts),
                "impact_area_distribution": area_counts
            },
            "impacts": impacts
        }

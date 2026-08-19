import os
import re
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from app.cms_ingestion import get_raw_file_paths, stream_cms_dataset

# Total physical row counts pre-calculated for accurate coverage metadata
TOTAL_PHYSICAL_ROWS = {
    "Carrier": 1121004,
    "Outpatient": 575092,
    "Part D 2023": 26794878,
    "Part D 2024": 28023892,
    "Beneficiary 2022": 8671,
    "Beneficiary 2023": 9179,
    "Beneficiary 2024": 9660,
}

# Required vs Optional vs Business Key Column Specifications
DATASET_SPECS = {
    "Carrier": {
        "required_cols": ["CLM_ID", "BENE_ID", "CLM_FROM_DT", "CLM_THRU_DT", "CLM_PMT_AMT"],
        "optional_cols_prefix": ["ICD_DGNS_", "HCPCS_", "CARR_CLM_RFRNG_", "LINE_HCT_"],
        "business_keys": ["CLM_ID", "LINE_NUM"],
        "date_cols": ["CLM_FROM_DT", "CLM_THRU_DT"],
        "amount_cols": ["CLM_PMT_AMT", "NCH_CARR_CLM_SBMTD_CHRG_AMT", "NCH_CARR_CLM_ALOWD_AMT"],
    },
    "Outpatient": {
        "required_cols": ["CLM_ID", "BENE_ID", "CLM_FROM_DT", "CLM_THRU_DT", "CLM_PMT_AMT", "PRVDR_NUM"],
        "optional_cols_prefix": ["ICD_DGNS_", "ICD_PRCDR_", "RSN_VISIT_", "REV_CNTR_"],
        "business_keys": ["CLM_ID", "CLM_LINE_NUM"],
        "date_cols": ["CLM_FROM_DT", "CLM_THRU_DT"],
        "amount_cols": ["CLM_PMT_AMT", "CLM_TOT_CHRG_AMT"],
    },
    "Part D 2023": {
        "required_cols": ["Prscrbr_NPI", "Brnd_Name", "Gnrc_Name", "Tot_Clms", "Tot_Drug_Cst"],
        "optional_cols_prefix": ["GE65_"],
        "business_keys": ["Prscrbr_NPI", "Brnd_Name", "Gnrc_Name"],
        "date_cols": [],
        "amount_cols": ["Tot_Clms", "Tot_30day_Fills", "Tot_Day_Suply", "Tot_Drug_Cst", "Tot_Benes"],
    },
    "Part D 2024": {
        "required_cols": ["Prscrbr_NPI", "Brnd_Name", "Gnrc_Name", "Tot_Clms", "Tot_Drug_Cst"],
        "optional_cols_prefix": ["GE65_"],
        "business_keys": ["Prscrbr_NPI", "Brnd_Name", "Gnrc_Name"],
        "date_cols": [],
        "amount_cols": ["Tot_Clms", "Tot_30day_Fills", "Tot_Day_Suply", "Tot_Drug_Cst", "Tot_Benes"],
    },
    "Beneficiary 2022": {
        "required_cols": ["BENE_ID", "BENE_BIRTH_DT", "SEX_IDENT_CD", "BENE_RACE_CD", "AGE_AT_END_REF_YR"],
        "optional_cols_prefix": ["BENE_DEATH_DT", "BENE_PTA_TRMNTN_", "BENE_PTB_TRMNTN_", "PTC_", "PTD_"],
        "business_keys": ["BENE_ID"],
        "date_cols": ["BENE_BIRTH_DT", "COVSTART"],
        "amount_cols": ["AGE_AT_END_REF_YR", "BENE_HI_CVRAGE_TOT_MONS"],
    },
    "Beneficiary 2023": {
        "required_cols": ["BENE_ID", "BENE_BIRTH_DT", "SEX_IDENT_CD", "BENE_RACE_CD", "AGE_AT_END_REF_YR"],
        "optional_cols_prefix": ["BENE_DEATH_DT", "BENE_PTA_TRMNTN_", "BENE_PTB_TRMNTN_", "PTC_", "PTD_"],
        "business_keys": ["BENE_ID"],
        "date_cols": ["BENE_BIRTH_DT", "COVSTART"],
        "amount_cols": ["AGE_AT_END_REF_YR", "BENE_HI_CVRAGE_TOT_MONS"],
    },
    "Beneficiary 2024": {
        "required_cols": ["BENE_ID", "BENE_BIRTH_DT", "SEX_IDENT_CD", "BENE_RACE_CD", "AGE_AT_END_REF_YR"],
        "optional_cols_prefix": ["BENE_DEATH_DT", "BENE_PTA_TRMNTN_", "BENE_PTB_TRMNTN_", "PTC_", "PTD_"],
        "business_keys": ["BENE_ID"],
        "date_cols": ["BENE_BIRTH_DT", "COVSTART"],
        "amount_cols": ["AGE_AT_END_REF_YR", "BENE_HI_CVRAGE_TOT_MONS"],
    },
}


class CMSDataQualityEngine:
    """
    Production-Quality Data Quality Engine for Raw CMS Healthcare Datasets.
    Performs completeness, validity, uniqueness, and consistency evaluation across chunked datasets.
    """

    def __init__(self, raw_dir: Optional[Path] = None):
        self.raw_dir = raw_dir
        self.registry = get_raw_file_paths(raw_dir)

    def evaluate_dataset(
        self,
        dataset_name: str,
        chunksize: int = 50000,
        max_chunks: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Evaluate data quality for a single raw CMS dataset in memory-efficient chunks.
        """
        if dataset_name not in self.registry:
            raise ValueError(f"Dataset {dataset_name} not in registry.")

        info = self.registry[dataset_name]
        if not info["exists"]:
            return {
                "dataset_name": dataset_name,
                "status": "MISSING_FILE",
                "evaluation_mode": "UNKNOWN",
                "rows_available": TOTAL_PHYSICAL_ROWS.get(dataset_name, 0),
                "rows_evaluated": 0,
                "coverage_percentage": 0.0,
                "cols_detected": 0,
                "completeness_score": 0.0,
                "validity_score": 0.0,
                "uniqueness_score": 0.0,
                "consistency_score": 0.0,
                "overall_quality_score": 0.0,
                "details": {"error": f"File not found at {info['path']}"}
            }

        spec = DATASET_SPECS.get(dataset_name, {})
        required_cols = spec.get("required_cols", [])
        business_keys = spec.get("business_keys", [])
        date_cols = spec.get("date_cols", [])
        amount_cols = spec.get("amount_cols", [])

        rows_available = TOTAL_PHYSICAL_ROWS.get(dataset_name, 0)
        rows_evaluated = 0

        # Completeness metrics
        required_cells_checked = 0
        required_missing_count = 0
        optional_missing_count = 0
        suppressed_count = 0

        # Validity & Date metrics
        invalid_date_count = 0
        date_inconsistency_count = 0
        negative_cost_count = 0
        invalid_numeric_count = 0
        invalid_age_count = 0
        invalid_npi_count = 0

        # Duplicates tracking
        full_row_duplicate_count = 0
        seen_business_keys = set()
        business_key_duplicate_count = 0

        cols_detected = 0
        chunks_processed = 0

        for chunk in stream_cms_dataset(dataset_name, chunksize=chunksize, max_chunks=max_chunks, raw_dir=self.raw_dir):
            chunks_processed += 1
            if cols_detected == 0:
                cols_detected = len(chunk.columns)

            num_rows = len(chunk)
            rows_evaluated += num_rows

            # 1. Fast Vectorized Suppression & Null Evaluation
            # Convert object columns to string chunk for fast matching
            str_chunk = chunk.astype(str)
            suppressed_mask = str_chunk.isin(["#", "*", "**", "* ", "# "])
            suppressed_count += int(suppressed_mask.sum().sum())

            # Evaluate required vs optional column missingness
            for col in chunk.columns:
                col_series = chunk[col]
                col_nulls = int(col_series.isnull().sum() + (str_chunk[col].str.strip() == "").sum())

                if col in required_cols:
                    required_cells_checked += num_rows
                    required_missing_count += col_nulls
                else:
                    optional_missing_count += col_nulls

            # 2. Validity Checks (Dates, Numbers, Costs, Ages)
            for d_col in date_cols:
                if d_col in chunk.columns:
                    dates = str_chunk[d_col].str.strip()
                    dates = dates[~dates.isin(["#", "*", "**", ""])]
                    parsed = pd.to_datetime(dates, errors="coerce", format="mixed")
                    invalid_date_count += int(parsed.isnull().sum())

            # Specific Claims Date Inconsistency: CLM_FROM_DT > CLM_THRU_DT
            if "CLM_FROM_DT" in chunk.columns and "CLM_THRU_DT" in chunk.columns:
                valid_dates = chunk[["CLM_FROM_DT", "CLM_THRU_DT"]].dropna()
                from_dt = pd.to_datetime(valid_dates["CLM_FROM_DT"], errors="coerce", format="mixed")
                thru_dt = pd.to_datetime(valid_dates["CLM_THRU_DT"], errors="coerce", format="mixed")
                mask = (from_dt.notnull()) & (thru_dt.notnull())
                inconsistent = (from_dt[mask] > thru_dt[mask])
                date_inconsistency_count += int(inconsistent.sum())

            # Amounts / Cost Validation
            for a_col in amount_cols:
                if a_col in chunk.columns:
                    str_vals = str_chunk[a_col].str.strip()
                    str_vals = str_vals[~str_vals.isin(["#", "*", "**", ""])]
                    vals = pd.to_numeric(str_vals, errors="coerce")
                    invalid_numeric_count += int(vals.isnull().sum())
                    negative_cost_count += int((vals < 0).sum())

            # Age Validation
            if "AGE_AT_END_REF_YR" in chunk.columns:
                ages = pd.to_numeric(chunk["AGE_AT_END_REF_YR"], errors="coerce").dropna()
                invalid_age_count += int(((ages < 0) | (ages > 120)).sum())

            # NPI Format Validation (10 digits)
            npi_cols = [c for c in chunk.columns if "NPI" in c.upper()]
            for npi_col in npi_cols:
                npis = str_chunk[npi_col].str.strip()
                npis = npis[~npis.isin(["#", "*", "**", "nan", "None", ""])]
                invalid_npi = ~npis.str.match(r"^\d{10}$")
                invalid_npi_count += int(invalid_npi.sum())

            # 3. Duplicate Evaluation
            full_row_duplicate_count += int(chunk.duplicated().sum())

            # Business-key duplicate evaluation
            valid_bkeys = [k for k in business_keys if k in chunk.columns]
            if valid_bkeys:
                bkey_chunk = str_chunk[valid_bkeys]
                for row in bkey_chunk.itertuples(index=False):
                    key_tuple = tuple(row)
                    if key_tuple in seen_business_keys:
                        business_key_duplicate_count += 1
                    else:
                        seen_business_keys.add(key_tuple)

        if rows_evaluated == 0:
            return {
                "dataset_name": dataset_name,
                "status": "EMPTY_DATASET",
                "evaluation_mode": "FULL_DATASET" if max_chunks is None else "SAMPLE",
                "rows_available": rows_available,
                "rows_evaluated": 0,
                "coverage_percentage": 0.0,
                "cols_detected": cols_detected,
                "completeness_score": 100.0,
                "validity_score": 100.0,
                "uniqueness_score": 100.0,
                "consistency_score": 100.0,
                "overall_quality_score": 100.0,
                "details": {}
            }

        # Determine Evaluation Mode & Coverage
        coverage_percentage = round((rows_evaluated / rows_available) * 100.0, 2) if rows_available > 0 else 100.0
        evaluation_mode = "FULL_DATASET" if coverage_percentage >= 99.9 else "SAMPLE"

        # Calculate Scores
        # A. Completeness (based on required fields without penalizing optional/suppressed cells)
        if required_cells_checked > 0:
            completeness_score = max(0.0, min(100.0, ((required_cells_checked - required_missing_count) / required_cells_checked) * 100.0))
        else:
            completeness_score = 100.0

        # B. Validity
        total_validity_tests = (rows_evaluated * max(1, len(amount_cols))) + (rows_evaluated * max(1, len(date_cols)))
        total_validity_errors = invalid_date_count + invalid_numeric_count + negative_cost_count + invalid_age_count
        validity_score = max(0.0, min(100.0, ((total_validity_tests - total_validity_errors) / total_validity_tests) * 100.0))

        # C. Uniqueness (business-key uniqueness)
        uniqueness_score = max(0.0, min(100.0, ((rows_evaluated - business_key_duplicate_count) / rows_evaluated) * 100.0))

        # D. Consistency
        total_consistency_tests = rows_evaluated * max(1, len(required_cols))
        total_consistency_errors = required_missing_count + date_inconsistency_count + invalid_npi_count
        consistency_score = max(0.0, min(100.0, ((total_consistency_tests - total_consistency_errors) / total_consistency_tests) * 100.0))

        # E. Overall Weighted Score
        overall_quality_score = round(
            completeness_score * 0.30 +
            validity_score * 0.30 +
            uniqueness_score * 0.20 +
            consistency_score * 0.20,
            2
        )

        return {
            "dataset_name": dataset_name,
            "status": "EVALUATED",
            "evaluation_mode": evaluation_mode,
            "rows_available": rows_available,
            "rows_evaluated": rows_evaluated,
            "coverage_percentage": coverage_percentage,
            "cols_detected": cols_detected,
            "chunk_size": chunksize,
            "chunks_processed": chunks_processed,
            "completeness_score": round(completeness_score, 2),
            "validity_score": round(validity_score, 2),
            "uniqueness_score": round(uniqueness_score, 2),
            "consistency_score": round(consistency_score, 2),
            "overall_quality_score": overall_quality_score,
            "details": {
                "required_missing_count": required_missing_count,
                "optional_missing_count": optional_missing_count,
                "suppressed_count": suppressed_count,
                "invalid_date_count": invalid_date_count,
                "date_inconsistency_count": date_inconsistency_count,
                "invalid_numeric_count": invalid_numeric_count,
                "negative_cost_count": negative_cost_count,
                "invalid_age_count": invalid_age_count,
                "invalid_npi_count": invalid_npi_count,
                "full_row_duplicate_count": full_row_duplicate_count,
                "business_key_duplicate_count": business_key_duplicate_count
            }
        }

    def generate_full_report(
        self,
        chunksize: int = 50000,
        max_chunks_per_file: Optional[int] = 5
    ) -> Dict[str, Any]:
        """
        Generate structured Data Quality Report across all 7 CMS raw datasets.
        """
        dataset_names = [
            "Carrier", "Outpatient", "Part D 2023", "Part D 2024",
            "Beneficiary 2022", "Beneficiary 2023", "Beneficiary 2024"
        ]

        reports = {}
        overall_scores = []

        for name in dataset_names:
            res = self.evaluate_dataset(name, chunksize=chunksize, max_chunks=max_chunks_per_file)
            reports[name] = res
            if res.get("status") == "EVALUATED":
                overall_scores.append(res.get("overall_quality_score", 0.0))

        overall_cms_score = round(sum(overall_scores) / len(overall_scores), 2) if overall_scores else 0.0

        return {
            "summary": {
                "total_datasets_evaluated": len(reports),
                "datasets_processed": list(reports.keys()),
                "overall_cms_quality_score": overall_cms_score
            },
            "datasets": reports
        }

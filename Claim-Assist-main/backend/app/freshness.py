import os
import glob
import time
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import pandas as pd

from app.cms_ingestion import get_raw_file_paths, stream_cms_dataset
from app.data_quality import TOTAL_PHYSICAL_ROWS


def get_file_modified_iso(path: Path) -> Optional[str]:
    """Retrieve ISO-8601 modified timestamp for a file."""
    if path.exists():
        mtime = os.path.getmtime(path)
        return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
    return None


def get_reporting_period(dataset_name: str) -> str:
    """Extract reporting period/year from dataset name."""
    if "2022" in dataset_name:
        return "2022"
    elif "2023" in dataset_name:
        return "2023"
    elif "2024" in dataset_name:
        return "2024"
    elif "Carrier" in dataset_name or "Outpatient" in dataset_name:
        return "2015-2023 Claims"
    return "Historical CMS"


class CMSFreshnessEngine:
    """
    Data Freshness & Ingestion Timing Engine for Raw CMS Datasets.
    Measures file availability, file modified timestamps, data date ranges, and ingestion performance.
    """

    def __init__(self, raw_dir: Optional[Path] = None):
        self.raw_dir = raw_dir
        self.registry = get_raw_file_paths(raw_dir)

    def evaluate_freshness(
        self,
        dataset_name: str,
        chunksize: int = 50000,
        max_chunks: Optional[int] = 3
    ) -> Dict[str, Any]:
        """
        Evaluate freshness, file metadata, and ingestion duration for a single dataset.
        """
        if dataset_name not in self.registry:
            raise ValueError(f"Dataset {dataset_name} not in registry.")

        info = self.registry[dataset_name]
        start_time = time.time()
        start_iso = datetime.now(timezone.utc).isoformat()

        if not info["exists"]:
            end_time = time.time()
            return {
                "dataset_name": dataset_name,
                "source_file": str(info["path"].name),
                "reporting_period": get_reporting_period(dataset_name),
                "file_size_bytes": 0,
                "file_modified_time": None,
                "latest_data_date": None,
                "rows_available": TOTAL_PHYSICAL_ROWS.get(dataset_name, 0),
                "rows_evaluated": 0,
                "coverage_percentage": 0.0,
                "ingestion_started_at": start_iso,
                "ingestion_completed_at": datetime.now(timezone.utc).isoformat(),
                "ingestion_duration_ms": round((end_time - start_time) * 1000, 2),
                "freshness_status": "UNAVAILABLE"
            }

        path = info["path"]
        file_size = path.stat().st_size if path.exists() else 0
        file_mtime = get_file_modified_iso(path)

        rows_available = TOTAL_PHYSICAL_ROWS.get(dataset_name, 0)
        rows_evaluated = 0
        latest_date_found = None

        date_col = None
        if "Carrier" in dataset_name or "Outpatient" in dataset_name:
            date_col = "CLM_THRU_DT"
        elif "Beneficiary" in dataset_name:
            date_col = "COVSTART"

        # Stream chunks and measure processing duration
        for chunk in stream_cms_dataset(dataset_name, chunksize=chunksize, max_chunks=max_chunks, raw_dir=self.raw_dir):
            rows_evaluated += len(chunk)
            if date_col and date_col in chunk.columns and latest_date_found is None:
                parsed = pd.to_datetime(chunk[date_col].dropna().astype(str), errors="coerce", format="mixed")
                # Filter out far-future anomaly dates (> 2026) for realistic CMS period representation
                valid_dates = parsed[(parsed.notnull()) & (parsed.dt.year <= 2026)]
                if not valid_dates.empty:
                    latest_date_found = valid_dates.max().strftime("%Y-%m-%d")

        end_time = time.time()
        end_iso = datetime.now(timezone.utc).isoformat()
        duration_ms = round((end_time - start_time) * 1000, 2)

        coverage_pct = round((rows_evaluated / rows_available) * 100.0, 2) if rows_available > 0 else 100.0
        freshness_status = "AVAILABLE" if info["exists"] else "UNAVAILABLE"

        return {
            "dataset_name": dataset_name,
            "source_file": str(path.name),
            "reporting_period": get_reporting_period(dataset_name),
            "file_size_bytes": file_size,
            "file_modified_time": file_mtime,
            "latest_data_date": latest_date_found or get_reporting_period(dataset_name),
            "rows_available": rows_available,
            "rows_evaluated": rows_evaluated,
            "coverage_percentage": coverage_pct,
            "ingestion_started_at": start_iso,
            "ingestion_completed_at": end_iso,
            "ingestion_duration_ms": duration_ms,
            "freshness_status": freshness_status
        }

    def generate_full_freshness_report(
        self,
        chunksize: int = 50000,
        max_chunks_per_file: Optional[int] = 3
    ) -> Dict[str, Any]:
        """
        Generate comprehensive freshness report across all 7 CMS raw datasets.
        """
        dataset_names = [
            "Carrier", "Outpatient", "Part D 2023", "Part D 2024",
            "Beneficiary 2022", "Beneficiary 2023", "Beneficiary 2024"
        ]

        reports = {}
        total_ingestion_time_ms = 0.0

        for name in dataset_names:
            res = self.evaluate_freshness(name, chunksize=chunksize, max_chunks=max_chunks_per_file)
            reports[name] = res
            total_ingestion_time_ms += res.get("ingestion_duration_ms", 0.0)

        return {
            "summary": {
                "total_datasets": len(reports),
                "total_ingestion_duration_ms": round(total_ingestion_time_ms, 2),
                "timestamp": datetime.now(timezone.utc).isoformat()
            },
            "datasets": reports
        }


class LiveLatencyTracker:
    """
    Precision microsecond timing tracker for live authorization processing pipeline.
    """

    def __init__(self):
        self.t_recv = datetime.now(timezone.utc)
        self.t_recv_mono = time.perf_counter()
        self.t_inf_start = None
        self.t_inf_end = None
        self.t_db_end = None
        self.t_ws_end = None

    def mark_inference_start(self):
        self.t_inf_start = time.perf_counter()

    def mark_inference_end(self):
        self.t_inf_end = time.perf_counter()

    def mark_db_persisted(self):
        self.t_db_end = time.perf_counter()

    def mark_ws_broadcast(self):
        self.t_ws_end = time.perf_counter()

    def get_timing_summary(self) -> Dict[str, Any]:
        now_mono = time.perf_counter()
        inf_dur_ms = round(((self.t_inf_end or now_mono) - (self.t_inf_start or now_mono)) * 1000, 3)
        db_dur_ms = round(((self.t_db_end or now_mono) - (self.t_inf_end or now_mono)) * 1000, 3) if self.t_inf_end and self.t_db_end else 0.0
        ws_dur_ms = round(((self.t_ws_end or now_mono) - (self.t_db_end or now_mono)) * 1000, 3) if self.t_db_end and self.t_ws_end else 0.0
        total_dur_ms = round((now_mono - self.t_recv_mono) * 1000, 3)

        return {
            "request_received_at": self.t_recv.isoformat(),
            "inference_duration_ms": max(0.001, inf_dur_ms),
            "database_persistence_ms": max(0.001, db_dur_ms),
            "websocket_broadcast_ms": max(0.001, ws_dur_ms),
            "end_to_end_latency_ms": max(0.001, total_dur_ms)
        }

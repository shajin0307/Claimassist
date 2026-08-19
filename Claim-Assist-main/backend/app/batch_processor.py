import io
import uuid
from datetime import datetime, timezone
import pandas as pd
from typing import Dict, Any, List, Tuple, Optional
from sqlalchemy.orm import Session

from app.database import save_authorization_records_batch, create_batch_upload_record

# Forbidden ground-truth columns that must NEVER be passed to ML inference
FORBIDDEN_FIELDS = {"EXPECTED_ANOMALY", "EXPECTED_TYPE", "IS_ANOMALY", "ANOMALY_TYPE"}


def process_csv_batch(
    csv_bytes: bytes,
    pipeline_func,
    db: Optional[Session] = None,
    batch_id: Optional[str] = None,
    filename: Optional[str] = None
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    """
    High-performance batch processor for authorization CSV files.
    Processes inference in-memory, tags each record with batch_id,
    and persists batch metadata & authorization records in a single bulk transaction.
    """
    if not batch_id:
        batch_id = f"BATCH_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    if not filename:
        filename = "upload_batch.csv"

    try:
        df = pd.read_csv(io.BytesIO(csv_bytes))
    except UnicodeDecodeError:
        df = pd.read_csv(io.BytesIO(csv_bytes), encoding="latin1")

    # Strip forbidden columns if present in CSV
    clean_columns = [col for col in df.columns if col not in FORBIDDEN_FIELDS and col.upper() not in FORBIDDEN_FIELDS]
    df_clean = df[clean_columns]

    records = df_clean.to_dict(orient="records")

    total_records = len(records)
    normal_count = 0
    anomaly_count = 0
    priority_counts = {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
    total_latency_ms = 0.0

    detailed_results = []

    for index, row in enumerate(records):
        if "auth_id" not in row or not row["auth_id"]:
            row["auth_id"] = f"CSV_AUTH_{index + 1:04d}"

        # Call pipeline with persist_db=False to compute inference at microsecond speed
        result = pipeline_func(row, db=None, persist_db=False)
        result["batch_id"] = batch_id

        prediction = result.get("prediction", "NORMAL")
        final_priority = result.get("final_priority", "LOW")
        latency = float(result.get("inference_latency_ms", 0.0))

        if prediction == "ANOMALY":
            anomaly_count += 1
        else:
            normal_count += 1

        priority_counts[final_priority] = priority_counts.get(final_priority, 0) + 1
        total_latency_ms += latency

        detailed_results.append(result)

    avg_latency_ms = round(total_latency_ms / total_records, 3) if total_records > 0 else 0.0

    summary = {
        "batch_id": batch_id,
        "filename": filename,
        "total_records": total_records,
        "normal_count": normal_count,
        "anomaly_count": anomaly_count,
        "anomaly_rate": round(anomaly_count / total_records, 4) if total_records > 0 else 0.0,
        "priority_distribution": priority_counts,
        "avg_inference_latency_ms": avg_latency_ms,
        "uploaded_at": datetime.now(timezone.utc).isoformat()
    }

    # Persist all records and batch metadata in database
    if db is not None and detailed_results:
        try:
            save_authorization_records_batch(db, detailed_results, batch_id=batch_id)
            create_batch_upload_record(db, summary)
        except Exception as err:
            print(f"Error persisting batch records: {err}")

    return summary, detailed_results



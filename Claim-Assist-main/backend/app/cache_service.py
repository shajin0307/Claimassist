import hashlib
import os
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any, Callable, Optional
from sqlalchemy.orm import Session

from app.cms_ingestion import get_raw_file_paths
from app.database import get_audit_cache, set_audit_cache


def get_raw_files_mtime_hash(raw_dir: Optional[Path] = None) -> str:
    """
    Compute a fast SHA-256 hash of modification times and sizes of all registered raw CMS files.
    Used to automatically invalidate audit caches if any raw CSV file is updated.
    """
    registry = get_raw_file_paths(raw_dir)
    mtime_strings = []
    for name in sorted(registry.keys()):
        p = registry[name]["path"]
        if p.exists():
            stat = p.stat()
            mtime_strings.append(f"{name}:{stat.st_size}:{stat.st_mtime}")
        else:
            mtime_strings.append(f"{name}:missing")
    
    combined = "|".join(mtime_strings)
    return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


def get_or_compute_report(
    db: Session,
    report_type: str,
    compute_fn: Callable[[], Dict[str, Any]],
    force_refresh: bool = False,
    raw_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Generic Audit Cache Manager:
    Returns cached PostgreSQL report immediately if source raw files are unchanged.
    Recomputes and updates database cache if force_refresh=True or source files changed.
    """
    current_mtime_hash = get_raw_files_mtime_hash(raw_dir)

    if not force_refresh:
        cached_data = get_audit_cache(db, report_type)
        if cached_data:
            meta = cached_data.get("_cached_metadata", {})
            cached_hash = meta.get("source_mtime_hash")
            if cached_hash == current_mtime_hash or not cached_hash:
                # Add top-level cache metadata for frontend inspection
                cached_data["metadata"] = {
                    "cached": True,
                    "generated_at": meta.get("generated_at", datetime.now(timezone.utc).isoformat()),
                    "evaluation_mode": "CACHED_POSTGRESQL",
                    "source_mtime_hash": current_mtime_hash
                }
                return cached_data

    # Compute fresh report
    fresh_report = compute_fn()
    fresh_report["metadata"] = {
        "cached": False,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "evaluation_mode": "FRESH_AUDIT",
        "source_mtime_hash": current_mtime_hash
    }

    # Save to PostgreSQL cache
    set_audit_cache(db, report_type, fresh_report, source_mtime_hash=current_mtime_hash)
    return fresh_report

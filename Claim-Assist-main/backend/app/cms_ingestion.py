import os
import glob
from pathlib import Path
from typing import Dict, Any, Generator, Optional
import pandas as pd

# Resolve project root and raw CMS directory
APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
SYSTEM_DIR = BACKEND_DIR.parent
PROJECT_ROOT = SYSTEM_DIR.parent

# Check candidate raw directory locations
RAW_CANDIDATES = [
    Path(os.getenv("RAW_CMS_DIR")) if os.getenv("RAW_CMS_DIR") else None,
    SYSTEM_DIR / "raw",
    BACKEND_DIR / "raw",
    PROJECT_ROOT / "raw",
]

DEFAULT_RAW_DIR = SYSTEM_DIR / "raw"
for cand in RAW_CANDIDATES:
    if cand and cand.exists():
        DEFAULT_RAW_DIR = cand
        break


def get_raw_file_paths(raw_dir: Optional[Path] = None) -> Dict[str, Dict[str, Any]]:
    """
    Locate all 7 raw CMS datasets and return metadata including path, delimiter, and existence status.
    """
    base_path = Path(raw_dir) if raw_dir else DEFAULT_RAW_DIR

    # Part D glob lookup
    part_d_2023_matches = glob.glob(str(base_path / "**" / "2023" / "*.csv"), recursive=True)
    part_d_2024_matches = glob.glob(str(base_path / "**" / "2024" / "*.csv"), recursive=True)

    part_d_2023_path = Path(part_d_2023_matches[0]) if part_d_2023_matches else base_path / "PartD_2023.csv"
    part_d_2024_path = Path(part_d_2024_matches[0]) if part_d_2024_matches else base_path / "PartD_2024.csv"

    registry = {
        "Carrier": {
            "path": base_path / "Carrier" / "carrier.csv",
            "delimiter": "|",
            "id_cols": ["CLM_ID", "BENE_ID", "PRF_PHYSN_NPI", "CARR_CLM_BLG_NPI_NUM"],
            "date_cols": ["CLM_FROM_DT", "CLM_THRU_DT"],
            "amount_cols": ["CLM_PMT_AMT", "NCH_CARR_CLM_SBMTD_CHRG_AMT", "NCH_CARR_CLM_ALOWD_AMT"]
        },
        "Outpatient": {
            "path": base_path / "Outpatient" / "outpatient.csv",
            "delimiter": "|",
            "id_cols": ["CLM_ID", "BENE_ID", "PRVDR_NUM", "ORG_NPI_NUM", "AT_PHYSN_NPI"],
            "date_cols": ["CLM_FROM_DT", "CLM_THRU_DT"],
            "amount_cols": ["CLM_PMT_AMT", "CLM_TOT_CHRG_AMT"]
        },
        "Part D 2023": {
            "path": part_d_2023_path,
            "delimiter": ",",
            "id_cols": ["Prscrbr_NPI"],
            "date_cols": [],
            "amount_cols": ["Tot_Clms", "Tot_30day_Fills", "Tot_Day_Suply", "Tot_Drug_Cst", "Tot_Benes"]
        },
        "Part D 2024": {
            "path": part_d_2024_path,
            "delimiter": ",",
            "id_cols": ["Prscrbr_NPI"],
            "date_cols": [],
            "amount_cols": ["Tot_Clms", "Tot_30day_Fills", "Tot_Day_Suply", "Tot_Drug_Cst", "Tot_Benes"]
        },
        "Beneficiary 2022": {
            "path": base_path / "beneficiary_2022.csv",
            "delimiter": ",",
            "id_cols": ["BENE_ID"],
            "date_cols": ["BENE_BIRTH_DT", "BENE_DEATH_DT", "COVSTART"],
            "amount_cols": ["AGE_AT_END_REF_YR", "BENE_HI_CVRAGE_TOT_MONS"]
        },
        "Beneficiary 2023": {
            "path": base_path / "beneficiary_2023.csv",
            "delimiter": ",",
            "id_cols": ["BENE_ID"],
            "date_cols": ["BENE_BIRTH_DT", "BENE_DEATH_DT", "COVSTART"],
            "amount_cols": ["AGE_AT_END_REF_YR", "BENE_HI_CVRAGE_TOT_MONS"]
        },
        "Beneficiary 2024": {
            "path": base_path / "beneficiary_2024.csv",
            "delimiter": ",",
            "id_cols": ["BENE_ID"],
            "date_cols": ["BENE_BIRTH_DT", "BENE_DEATH_DT", "COVSTART"],
            "amount_cols": ["AGE_AT_END_REF_YR", "BENE_HI_CVRAGE_TOT_MONS"]
        }
    }

    # Add metadata flags
    for name, item in registry.items():
        item["exists"] = item["path"].exists()
        item["size_bytes"] = item["path"].stat().st_size if item["exists"] else 0

    return registry


def stream_cms_dataset(
    dataset_name: str,
    chunksize: int = 50000,
    max_chunks: Optional[int] = None,
    raw_dir: Optional[Path] = None
) -> Generator[pd.DataFrame, None, None]:
    """
    Memory-efficient chunked reader generator for CMS raw CSV datasets.
    """
    registry = get_raw_file_paths(raw_dir)
    if dataset_name not in registry:
        raise ValueError(f"Unknown CMS dataset name: {dataset_name}. Valid names: {list(registry.keys())}")

    info = registry[dataset_name]
    if not info["exists"]:
        raise FileNotFoundError(f"Raw file for {dataset_name} not found at {info['path']}")

    chunk_count = 0
    reader = pd.read_csv(
        info["path"],
        sep=info["delimiter"],
        chunksize=chunksize,
        low_memory=False,
        encoding="utf-8",
        on_bad_lines="skip"
    )

    for chunk in reader:
        yield chunk
        chunk_count += 1
        if max_chunks is not None and chunk_count >= max_chunks:
            break

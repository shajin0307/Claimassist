import pytest
import os
from pathlib import Path
from app.cms_ingestion import get_raw_file_paths, stream_cms_dataset
from app.data_quality import CMSDataQualityEngine


@pytest.fixture(autouse=True)
def setup_mock_raw_dir(tmp_path, monkeypatch):
    """Set up temporary mock raw CMS files if not present on machine."""
    carrier_dir = tmp_path / "Carrier"
    carrier_dir.mkdir(parents=True, exist_ok=True)
    (carrier_dir / "carrier.csv").write_text("CLM_ID|BENE_ID|PRF_PHYSN_NPI|CARR_CLM_BLG_NPI_NUM|CLM_FROM_DT|CLM_THRU_DT|CLM_PMT_AMT|NCH_CARR_CLM_SBMTD_CHRG_AMT|NCH_CARR_CLM_ALOWD_AMT\nCLM01|BENE01|1234567890|1234567890|20230101|20230102|100.0|150.0|120.0\n", encoding="utf-8")

    outpatient_dir = tmp_path / "Outpatient"
    outpatient_dir.mkdir(parents=True, exist_ok=True)
    (outpatient_dir / "outpatient.csv").write_text("CLM_ID|BENE_ID|PRVDR_NUM|ORG_NPI_NUM|AT_PHYSN_NPI|CLM_FROM_DT|CLM_THRU_DT|CLM_PMT_AMT|CLM_TOT_CHRG_AMT\nCLM02|BENE01|PRV01|1234567890|1234567890|20230101|20230102|200.0|300.0\n", encoding="utf-8")

    part_d_2023_dir = tmp_path / "2023"
    part_d_2023_dir.mkdir(parents=True, exist_ok=True)
    (part_d_2023_dir / "partd.csv").write_text("Prscrbr_NPI,Tot_Clms,Tot_30day_Fills,Tot_Day_Suply,Tot_Drug_Cst,Tot_Benes\n1234567890,50,50,1500,2500.0,40\n", encoding="utf-8")

    part_d_2024_dir = tmp_path / "2024"
    part_d_2024_dir.mkdir(parents=True, exist_ok=True)
    (part_d_2024_dir / "partd.csv").write_text("Prscrbr_NPI,Tot_Clms,Tot_30day_Fills,Tot_Day_Suply,Tot_Drug_Cst,Tot_Benes\n1234567890,60,60,1800,3000.0,45\n", encoding="utf-8")

    for year in ["2022", "2023", "2024"]:
        (tmp_path / f"beneficiary_{year}.csv").write_text("BENE_ID,BENE_BIRTH_DT,BENE_SEX_IDENT_CD,BENE_RACE_CD\nBENE01,19500101,1,1\n", encoding="utf-8")

    monkeypatch.setenv("RAW_CMS_DIR", str(tmp_path))
    from app import cms_ingestion
    monkeypatch.setattr(cms_ingestion, "DEFAULT_RAW_DIR", tmp_path)


def test_cms_ingestion_registry():
    """Verify that all 7 raw CMS datasets are registered with correct delimiters."""
    registry = get_raw_file_paths()
    expected_datasets = [
        "Carrier", "Outpatient", "Part D 2023", "Part D 2024",
        "Beneficiary 2022", "Beneficiary 2023", "Beneficiary 2024"
    ]
    for dataset_name in expected_datasets:
        assert dataset_name in registry
        info = registry[dataset_name]
        assert info["exists"] is True
        assert info["size_bytes"] > 0
        assert info["delimiter"] in ["|", ","]


def test_cms_ingestion_streaming():
    """Verify memory-efficient chunked streaming of Carrier raw dataset."""
    chunks = list(stream_cms_dataset("Carrier", chunksize=500, max_chunks=2))
    assert len(chunks) >= 1
    assert chunks[0].shape[0] > 0
    assert "CLM_ID" in chunks[0].columns
    assert "BENE_ID" in chunks[0].columns


def test_data_quality_engine_single_dataset():
    """Verify single dataset quality evaluation metrics for Beneficiary 2022."""
    engine = CMSDataQualityEngine()
    result = engine.evaluate_dataset("Beneficiary 2022", chunksize=1000, max_chunks=2)
    assert result["status"] == "EVALUATED"
    assert result["dataset_name"] == "Beneficiary 2022"
    assert result["cols_detected"] > 0
    assert result["rows_evaluated"] > 0
    assert 0.0 <= result["completeness_score"] <= 100.0
    assert 0.0 <= result["validity_score"] <= 100.0
    assert 0.0 <= result["uniqueness_score"] <= 100.0
    assert 0.0 <= result["consistency_score"] <= 100.0
    assert 0.0 <= result["overall_quality_score"] <= 100.0


def test_data_quality_full_report():
    """Verify full quality report for all 7 raw CMS datasets."""
    engine = CMSDataQualityEngine()
    report = engine.generate_full_report(chunksize=1000, max_chunks_per_file=1)
    summary = report.get("summary", {})
    assert summary.get("total_datasets_evaluated") == 7
    assert len(summary.get("datasets_processed", [])) == 7
    assert summary.get("overall_cms_quality_score") > 0.0

    datasets = report.get("datasets", {})
    for name in summary["datasets_processed"]:
        assert name in datasets
        assert datasets[name]["status"] == "EVALUATED"
        assert datasets[name]["cols_detected"] > 0
        assert datasets[name]["rows_evaluated"] > 0


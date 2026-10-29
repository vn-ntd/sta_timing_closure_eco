import json

from run_experiments import main


def test_cli_execution_with_exports(tmp_path):
    json_path = tmp_path / "timing_summary.json"
    csv_prefix = tmp_path / "test_sweep"

    # Call CLI entrypoint with flags
    main([
        "--quiet",
        "--export-json", str(json_path),
        "--export-csv", str(csv_prefix),
        "--derate-late", "1.08",
        "--derate-early", "0.92",
    ])

    # Verify JSON output
    assert json_path.exists()
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    assert data["design"] == "Crypto_MAC_Unit"
    assert data["baseline"]["status"] == "VIOLATED"
    assert data["post_eco"]["status"] == "MET (CLOSED)"
    assert len(data["ocv_sweep"]) == 5
    assert len(data["jitter_sweep"]) == 7

    # Verify CSV outputs
    ocv_csv = tmp_path / "test_sweep_ocv.csv"
    jitter_csv = tmp_path / "test_sweep_jitter.csv"
    assert ocv_csv.exists()
    assert jitter_csv.exists()

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pandas as pd
import pytest

from tools.golden_master.normalize import normalize_text

pytestmark = pytest.mark.slow

ROOT = Path(__file__).resolve().parents[1]
CAPTURE_SCRIPT = ROOT / "tools" / "golden_master" / "capture_all.py"

NUMERIC_CSV_STREAMS = [
    "cpm_cc.csv",
    "bull_cc.csv",
    "ndx_cc.csv",
    "rpv_cc.csv",
    "cpm_mooex.csv",
    "rpv_mooex.csv",
    "ndx_mooex.csv",
    "val_mooex.csv",
    "blend.csv",
    "blend_uncapped.csv",
]

JSON_STREAMS = [
    "cpm_records.json",
    "rpv_records.json",
    "ndx_records.json",
    "val_records.json",
    "mooex_coverage.json",
]

TEXT_STREAMS = ["allocate.txt", "format_message.txt", "cpm_dashboard.html"]


@pytest.fixture(scope="module")
def golden_artifacts_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out_dir = tmp_path_factory.mktemp("golden_master")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")

    result = subprocess.run(
        [sys.executable, str(CAPTURE_SCRIPT), "--out", str(out_dir)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"capture_all.py failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"

    expected = set(NUMERIC_CSV_STREAMS + JSON_STREAMS + TEXT_STREAMS)
    produced = {p.name for p in out_dir.iterdir() if p.is_file()}
    missing = sorted(expected - produced)
    assert not missing, f"capture_all.py missing expected artifacts: {missing}"
    return out_dir


def _normalize_for_file(name: str, text: str) -> str:
    # Preserve legacy behavior: dashboard content is normalized/masked;
    # allocate and format_message remain byte-precise checks.
    if name == "cpm_dashboard.html":
        return normalize_text(text)
    return text


def test_allocate(golden_artifacts_dir: Path, file_regression) -> None:
    path = golden_artifacts_dir / "allocate.txt"
    text = path.read_text(encoding="utf-8")
    file_regression.check(_normalize_for_file(path.name, text), extension=".txt")


def test_format_message(golden_artifacts_dir: Path, file_regression) -> None:
    path = golden_artifacts_dir / "format_message.txt"
    text = path.read_text(encoding="utf-8")
    file_regression.check(_normalize_for_file(path.name, text), extension=".txt")


def test_cpm_dashboard(golden_artifacts_dir: Path, file_regression) -> None:
    path = golden_artifacts_dir / "cpm_dashboard.html"
    text = path.read_text(encoding="utf-8")
    file_regression.check(_normalize_for_file(path.name, text), extension=".html")


@pytest.mark.parametrize("stream_name", NUMERIC_CSV_STREAMS)
def test_numeric_csv_stream(
    golden_artifacts_dir: Path,
    stream_name: str,
    dataframe_regression,
    data_regression,
) -> None:
    path = golden_artifacts_dir / stream_name
    df = pd.read_csv(path, index_col=0, parse_dates=True)

    if isinstance(df.index, pd.DatetimeIndex):
        # Keep date signal deterministic while keeping value columns numeric.
        df.index = df.index.strftime("%Y-%m-%d")

    non_numeric_columns = [col for col in df.columns if not pd.api.types.is_numeric_dtype(df[col])]
    if non_numeric_columns:
        data_regression.check(
            {
                "index": [str(x) for x in df.index],
                "columns": {col: df[col].tolist() for col in df.columns},
                "non_numeric_columns": non_numeric_columns,
            }
        )
        return

    dataframe_regression.check(
        df,
        default_tolerance={"atol": 1e-10, "rtol": 1e-10},
    )


@pytest.mark.parametrize("stream_name", JSON_STREAMS)
def test_json_records(golden_artifacts_dir: Path, stream_name: str, data_regression) -> None:
    path = golden_artifacts_dir / stream_name
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    data_regression.check(data)

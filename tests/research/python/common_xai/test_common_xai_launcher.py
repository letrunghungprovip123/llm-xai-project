from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_run_common_xai_launcher_bootstraps_repository_root() -> None:
    root = Path(__file__).resolve().parents[4]
    script = root / "scripts/multidataset/run_common_xai.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert "--dataset-profile" in result.stdout
    assert "--through" in result.stdout

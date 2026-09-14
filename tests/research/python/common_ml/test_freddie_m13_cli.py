from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def test_freddie_m13_verifier_launcher_help() -> None:
    root = Path(__file__).resolve().parents[4]
    result = subprocess.run(
        [sys.executable, str(root / "scripts/multidataset/verify_freddie_common_ml.py"), "--help"],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "--workspace" in result.stdout

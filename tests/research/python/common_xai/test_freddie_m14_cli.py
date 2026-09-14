from __future__ import annotations
import subprocess, sys
from pathlib import Path

def test_freddie_m14_launchers_help() -> None:
    root=Path(__file__).resolve().parents[4]
    for name in ("preflight_freddie_xai.py","verify_freddie_xai_ir.py"):
        result=subprocess.run([sys.executable,str(root/"scripts/multidataset"/name),"--help"],cwd=root,text=True,capture_output=True,check=False)
        assert result.returncode==0, result.stderr

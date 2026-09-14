from __future__ import annotations
import subprocess,sys
from pathlib import Path

def test_m16_launchers_help() -> None:
 root=Path(__file__).resolve().parents[4]
 for name in ("build_freddie_evaluation_subset.py","verify_home_credit_36_selector_parity.py"):
  r=subprocess.run([sys.executable,str(root/"scripts/multidataset"/name),"--help"],cwd=root,text=True,capture_output=True,check=False); assert r.returncode==0,r.stderr

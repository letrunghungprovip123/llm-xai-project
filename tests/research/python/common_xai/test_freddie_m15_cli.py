from __future__ import annotations
import subprocess,sys
from pathlib import Path

def test_freddie_m15_launcher_help() -> None:
 root=Path(__file__).resolve().parents[4]; r=subprocess.run([sys.executable,str(root/"scripts/multidataset/verify_freddie_evidence.py"),"--help"],cwd=root,text=True,capture_output=True,check=False); assert r.returncode==0,r.stderr

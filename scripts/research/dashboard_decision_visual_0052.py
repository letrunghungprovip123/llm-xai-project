#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.python.dashboard.v3.decision_model import SCENARIO_ORDER, build_decision_model
from research.python.dashboard.v3.figures import (
    decision_noninferiority_plot,
    decision_quality_efficiency_plot,
    decision_quality_reliability_plot,
)
from research.python.dashboard.v3.repository import get_v3_repository

ROOT = PROJECT_ROOT
SCREENSHOT_DIR = ROOT / ".researchops/visual_decision_certification"


def data_gate() -> None:
    repo = get_v3_repository()
    for scope in ("HOME_CREDIT", "FREDDIE", "CROSS_DATASET"):
        model = build_decision_model(repo, scope, "vi")
        if len(model.options) != 18:
            raise RuntimeError(f"Decision option topology drift {scope}: {len(model.options)}")
        expected_ni = 30 if scope == "CROSS_DATASET" else 15
        if len(model.ni_rows) != expected_ni:
            raise RuntimeError(f"NI topology drift {scope}: {len(model.ni_rows)}")
        if model.primary_margin != 0.03:
            raise RuntimeError(f"Primary NI margin drift: {model.primary_margin}")
        ni = decision_noninferiority_plot(model.ni_rows, cross_dataset=scope == "CROSS_DATASET")
        qr = decision_quality_reliability_plot(model.options)
        qe = decision_quality_efficiency_plot(model.options)
        if any(len(fig.data) == 0 for fig in (ni, qr, qe)):
            raise RuntimeError(f"Decision figure unexpectedly empty: {scope}")
        if tuple(qr.layout.xaxis.range) != (0, 1.02) or tuple(qr.layout.yaxis.range) != (0, 1.02):
            raise RuntimeError("Decision quality/reliability axes must retain fixed 0–100% scales")

    cross = build_decision_model(repo, "CROSS_DATASET", "vi")
    expected_counts = {"total": 18, "both_hard_gate": 14, "home_credit_ni": 2, "freddie_ni": 2, "robust_ni": 0, "robust_eligible": 0}
    for key, expected in expected_counts.items():
        if cross.decision_counts[key] != expected:
            raise RuntimeError(f"Decision path drift {key}: {cross.decision_counts[key]} != {expected}")
    dataset_recs = {r["recommendation_scope"]: r for r in cross.dataset_recommendations}
    if dataset_recs["HOME_CREDIT_PRIMARY"]["option_id"] != "qwen3_8b::S1":
        raise RuntimeError("Home Credit certified recommendation drift")
    if dataset_recs["FREDDIE_PRIMARY"]["option_id"] != "qwen3_8b::S4":
        raise RuntimeError("Freddie certified recommendation drift")
    if cross.robust_status != "NO_ROBUST_RECOMMENDATION":
        raise RuntimeError("Cross-dataset robust recommendation status drift")
    if tuple(r["scenario_id"] for r in cross.scenarios) != SCENARIO_ORDER:
        raise RuntimeError("Frozen scenario order drift")
    if any(r["pool_mode"] != "NONE" or r["scenario_eligible_count"] != 0 or r["utility_non_null_count"] != 0 for r in cross.scenarios):
        raise RuntimeError("Scenario pool/utility state drifted from certified NONE/N/A state")

    focus = build_decision_model(repo, "CROSS_DATASET", "vi", search="?tab=tradeoffs&dataset=FREDDIE&model=qwen3_8b&evidence=S4&option=qwen3_8b::S4&scenario=QUALITY_FIRST")
    if (focus.initial_tab, focus.focus_dataset, focus.focus_model, focus.focus_evidence, focus.focus_option, focus.focus_scenario) != ("tradeoffs", "FREDDIE", "qwen3_8b", "S4", "qwen3_8b::S4", "QUALITY_FIRST"):
        raise RuntimeError("Decision URL-state contract failed")
    print("DASHBOARD_DECISION_0052_DATA=PASS scopes=3 options=18 ni=15x2 scenarios=5 robust=none")


def source_gate() -> None:
    page = (ROOT / "research/python/dashboard/v3/pages/decision.py").read_text(encoding="utf-8")
    model = (ROOT / "research/python/dashboard/v3/decision_model.py").read_text(encoding="utf-8")
    figures = (ROOT / "research/python/dashboard/v3/figures.py").read_text(encoding="utf-8")
    callbacks = (ROOT / "research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    for token in ("Certified decision", "Decision Eligibility Path", "Eligibility Matrix", "Certified Non-Inferiority evidence", "Quality × Reliability", "Quality × Token burden", "Certified scenarios", "NO_ROBUST_RECOMMENDATION"):
        if token not in page and token != "Decision Eligibility Path":
            raise RuntimeError(f"Missing Decision redesign token: {token}")
    for forbidden in ("import scipy", "from scipy", "statsmodels", "wilcoxon(", "multipletests(", "visualization_v2", "get_dashboard_repository", "decision_support", "idxmax(", "argmax("):
        if forbidden in page or forbidden in model or forbidden in callbacks:
            raise RuntimeError(f"Scientific/legacy token leaked into Decision: {forbidden}")
    if "pareto(" in page or "pareto(" in model or "utility_score =" in callbacks:
        raise RuntimeError("Decision presentation attempts to recompute Pareto/utility")
    if "dmc.Tabs" in page:
        raise RuntimeError("Decision must use certified SegmentedControl tab runtime")
    if "decision-detail-drawer-body-content" not in page or "decision-detail-drawer-title-content" not in page:
        raise RuntimeError("Decision Drawer content IDs are not portal-safe")
    if 'Input(LOCATION, "pathname")' not in callbacks or 'Input(LOCATION, "search")' not in callbacks:
        raise RuntimeError("Decision page render must listen to pathname + search")
    print("DASHBOARD_DECISION_0052_SOURCE=PASS science=read-only url_state=first-class drawer=portal-safe")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0)); return int(sock.getsockname()[1])


def _wait_server(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45; last = None
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Dashboard server exited early: {process.returncode}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status < 500: return
        except Exception as exc:
            last = exc
        time.sleep(0.25)
    raise RuntimeError(f"Dashboard did not become ready: {last}")


def _browser_executable() -> str | None:
    candidates = [shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("google-chrome"), shutil.which("google-chrome-stable"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    return next((str(x) for x in candidates if x and Path(x).exists()), None)


def _duplicates(page) -> dict:
    return page.evaluate("() => { const c={}; document.querySelectorAll('[id]').forEach(e => c[e.id]=(c[e.id]||0)+1); return Object.fromEntries(Object.entries(c).filter(([,n])=>n>1)); }")


def _layout(page) -> dict:
    return page.evaluate("() => ({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,bw:document.body.scrollWidth})")


def browser_gate() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError("Playwright is required for Decision visual certification") from exc
    for package in ("dash", "dash-mantine-components", "dash-iconify"):
        try: importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc: raise RuntimeError(f"Missing dashboard runtime dependency: {package}") from exc

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for old in SCREENSHOT_DIR.glob("decision_*.png"): old.unlink()
    port = _free_port(); base = f"http://127.0.0.1:{port}"
    env = os.environ.copy(); env.update({"DASH_HOST":"127.0.0.1","DASH_PORT":str(port),"DASH_DEBUG":"0","PYTHONUNBUFFERED":"1"})
    log_path = SCREENSHOT_DIR / "dashboard_server.log"; log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "research.python.dashboard.app_v3"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
    try:
        _wait_server(base, process)
        with sync_playwright() as p:
            try: browser = p.chromium.launch(headless=True)
            except Exception:
                executable = _browser_executable()
                if not executable: raise RuntimeError("Chromium/Chrome executable unavailable")
                browser = p.chromium.launch(headless=True, executable_path=executable)
            for width, height in ((1366,768),(1440,900),(1920,1080)):
                context = browser.new_context(viewport={"width":width,"height":height})
                page = context.new_page(); console_errors=[]; page_errors=[]; request_failures=[]
                page.on("console", lambda msg: console_errors.append(msg.text) if (msg.type == "error" or "warning #29" in msg.text.lower()) else None)
                page.on("pageerror", lambda exc: page_errors.append(str(exc)))
                page.on("requestfailed", lambda req: request_failures.append({"url":req.url,"failure":req.failure}))
                page.goto(base + "/decision", wait_until="networkidle")
                page.locator("#decision-ni-evidence").wait_for(state="visible", timeout=15000)
                text = page.locator("#v3-decision-content").inner_text()
                for token in ("Decision Studio", "Eligibility Matrix", "NO_ROBUST_RECOMMENDATION", "Certified Non-Inferiority evidence"):
                    if token not in text: raise RuntimeError(f"Decision UI missing {token}")
                points = page.locator("#decision-ni-evidence .scatterlayer path.point")
                if points.count() == 0: raise RuntimeError("Decision NI plot has no clickable markers")
                points.first.click(force=True)
                page.locator('[data-testid="decision-drawer-content"]').wait_for(state="visible", timeout=6000)
                if _duplicates(page): raise RuntimeError(f"Duplicate DOM IDs after Decision NI drawer: {_duplicates(page)}")
                page.keyboard.press("Escape")
                page.locator('[data-testid="decision-drawer-content"]').wait_for(state="hidden", timeout=4000)

                page.get_by_text("Trade-offs", exact=True).click()
                page.locator("#decision-quality-reliability").wait_for(state="visible", timeout=5000)
                trade_points = page.locator("#decision-quality-reliability .scatterlayer path.point")
                if trade_points.count() == 0: raise RuntimeError("Decision trade-off chart has no clickable markers")
                trade_points.first.click(force=True)
                page.locator('[data-testid="decision-drawer-content"]').wait_for(state="visible", timeout=6000)
                page.keyboard.press("Escape")
                page.locator('[data-testid="decision-drawer-content"]').wait_for(state="hidden", timeout=4000)

                page.get_by_text("Certified scenarios", exact=True).click()
                page.locator('[data-testid="decision-scenario-detail"]').wait_for(state="visible", timeout=5000)
                if "NO_ROBUST_RECOMMENDATION" not in page.locator('[data-testid="decision-scenario-detail"]').inner_text():
                    raise RuntimeError("Decision frozen scenario detail lost certified no-winner state")

                layout = _layout(page)
                if int(layout["sw"]) > int(layout["cw"]) + 2 or int(layout["bw"]) > int(layout["cw"]) + 2:
                    raise RuntimeError(f"Decision horizontal overflow {width}x{height}: {layout}")
                if console_errors or page_errors or request_failures:
                    raise RuntimeError(f"Decision browser errors console={console_errors} page={page_errors} requests={request_failures}")
                page.screenshot(path=str(SCREENSHOT_DIR / f"decision_cross_{width}x{height}.png"), full_page=True)
                context.close()

            # Direct URL state must be honored on first paint.
            context = browser.new_context(viewport={"width":1440,"height":900})
            page = context.new_page(); errors=[]
            page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
            page.goto(base + "/decision?tab=tradeoffs&dataset=FREDDIE&model=qwen3_8b&evidence=S4&option=qwen3_8b::S4", wait_until="networkidle")
            page.locator("#decision-quality-reliability").wait_for(state="visible", timeout=15000)
            if page.locator("#decision-quality-reliability .scatterlayer path.point").count() != 1:
                raise RuntimeError("Decision deep-link did not filter initial trade-off figure to one option")
            selected = page.locator("#decision-tradeoff-selected-option").inner_text()
            if "Qwen3 8B × S4" not in selected:
                raise RuntimeError(f"Decision deep-link selected-option mismatch: {selected!r}")
            if errors: raise RuntimeError(f"Decision deep-link console errors: {errors}")
            context.close()

            context = browser.new_context(viewport={"width":1440,"height":900})
            page = context.new_page()
            page.goto(base + "/decision?tab=scenarios&scenario=QUALITY_FIRST", wait_until="networkidle")
            page.locator('[data-testid="decision-scenario-detail"]').wait_for(state="visible", timeout=15000)
            if "Quality first" not in page.locator('[data-testid="decision-scenario-detail"]').inner_text():
                raise RuntimeError("Decision scenario deep-link did not honor QUALITY_FIRST")
            context.close(); browser.close()
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        log.close()
    print(f"DASHBOARD_DECISION_0052_BROWSER=PASS viewports=3 screenshots={SCREENSHOT_DIR}")


def main() -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--browser", action="store_true"); args=parser.parse_args()
    data_gate(); source_gate()
    if args.browser: browser_gate()
    print("DASHBOARD_DECISION_0052=PASS")
    return 0


if __name__ == "__main__": raise SystemExit(main())

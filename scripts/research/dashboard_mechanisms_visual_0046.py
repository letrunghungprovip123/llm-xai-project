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

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.python.dashboard.v3.figures import (
    mechanism_claim_matrix,
    mechanism_faithfulness_accounting,
    mechanism_lexical_signal,
    mechanism_quality_map,
)
from research.python.dashboard.v3.mechanisms_model import build_mechanisms_model
from research.python.dashboard.v3.repository import get_v3_repository

ROOT = PROJECT_ROOT
SCREENSHOT_DIR = ROOT / ".researchops/visual_mechanisms_certification"


def data_gate() -> None:
    repo = get_v3_repository()
    for scope in ("HOME_CREDIT", "FREDDIE", "CROSS_DATASET"):
        model = build_mechanisms_model(repo, scope, "vi")
        expected_loss = 2 if scope == "CROSS_DATASET" else 1
        expected_quality = 36 if scope == "CROSS_DATASET" else 18
        if len(model.loss_rows) != expected_loss:
            raise RuntimeError(f"Loss topology drift {scope}: {len(model.loss_rows)}")
        if len(model.quality_rows) != expected_quality:
            raise RuntimeError(f"Quality topology drift {scope}: {len(model.quality_rows)}")
        for row in model.loss_rows:
            identity = sum(float(row[key]) for key in ("primary_e2e", "pipeline_loss", "not_verifiable_loss", "unsupported_loss", "contradiction_loss"))
            if not np.isclose(identity, 1.0, atol=1e-8):
                raise RuntimeError(f"Faithfulness accounting identity drift: {scope} {identity}")
        cross = scope == "CROSS_DATASET"
        accounting = mechanism_faithfulness_accounting(model.loss_rows)
        lexical = mechanism_lexical_signal(model.loss_rows)
        claims = mechanism_claim_matrix(model.claim_rows, cross_dataset=cross, measure="share")
        quality = mechanism_quality_map(model.quality_rows, cross_dataset=cross)
        if any(len(fig.data) == 0 for fig in (accounting, lexical, claims, quality)):
            raise RuntimeError(f"Mechanisms figure unexpectedly empty: {scope}")
        stacked = np.sum([np.asarray(trace.x, dtype=float) for trace in accounting.data], axis=0)
        if not np.allclose(stacked, 1.0, atol=1e-8):
            raise RuntimeError("100% Faithfulness Accounting no longer reconciles")
        if cross:
            if len(claims.data) != 2 or any(float(trace.zmin) != 0 or float(trace.zmax) != 1 for trace in claims.data):
                raise RuntimeError("Cross claim-share matrices must use a shared 0–100% scale")
            hc = claims.data[0]
            if "causal" not in list(hc.y):
                raise RuntimeError("Union claim taxonomy lost Freddie causal claim type")
            causal_idx = list(hc.y).index("causal")
            values = list(hc.z[causal_idx])
            if not all(value is None or (isinstance(value, float) and np.isnan(value)) for value in values):
                raise RuntimeError("Absent Home Credit causal claim type must be N/A, never zero")
        if tuple(quality.layout.xaxis.range) != (0, 1.02) or tuple(quality.layout.yaxis.range) != (0, 1.02):
            raise RuntimeError("Quality mechanisms axes must remain fixed/comparable")

    focused = build_mechanisms_model(repo, "FREDDIE", "vi", search="?dataset=FREDDIE&validation_status=NOT_VERIFIABLE")
    if focused.initial_tab != "claims" or focused.focus_validation_status != "NOT_VERIFIABLE" or focused.focus_dataset != "FREDDIE":
        raise RuntimeError("Mechanisms validation-status drill-through contract failed")
    print("DASHBOARD_MECHANISMS_0046_DATA=PASS loss_identity=1 claim_taxonomy=dynamic quality_options=36")


def source_gate() -> None:
    page = (ROOT / "research/python/dashboard/v3/pages/mechanisms.py").read_text(encoding="utf-8")
    model = (ROOT / "research/python/dashboard/v3/mechanisms_model.py").read_text(encoding="utf-8")
    figures = (ROOT / "research/python/dashboard/v3/figures.py").read_text(encoding="utf-8")
    callbacks = (ROOT / "research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    for token in ("100% Faithfulness Accounting", "Claim type × Validation status", "Verifiability × Resolved Faithfulness Map", "không causal attribution", "N/A khác 0", "presentation normalization", "mechanisms-detail-drawer"):
        if token not in page:
            raise RuntimeError(f"Missing Page-3 redesign token: {token}")
    for forbidden in ("scipy", "statsmodels", "wilcoxon", "multipletests", "bootstrap(", "visualization_v2", "get_dashboard_repository"):
        if any(forbidden in source for source in (page, model, figures, callbacks)):
            raise RuntimeError(f"Scientific/legacy token leaked into Page 3: {forbidden}")
    if 'columnSize="sizeToFit"' in page:
        raise RuntimeError("Hidden-tab AgGrid must not call sizeToFit at zero width")
    if "mechanisms-detail-drawer-body-content" not in page or "mechanisms-detail-drawer-title-content" not in page:
        raise RuntimeError("Mechanisms Drawer content IDs are not portal-safe")
    print("DASHBOARD_MECHANISMS_0046_SOURCE=PASS diagnostic_noncausal=true science=read-only")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0)); return int(sock.getsockname()[1])


def _wait_server(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45; last = None
    while time.time() < deadline:
        if process.poll() is not None: raise RuntimeError(f"Dashboard server exited early: {process.returncode}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status < 500: return
        except Exception as exc: last = exc
        time.sleep(0.25)
    raise RuntimeError(f"Dashboard did not become ready: {last}")


def _browser_executable() -> str | None:
    candidates = [shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("google-chrome"), shutil.which("google-chrome-stable"), "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "/Applications/Chromium.app/Contents/MacOS/Chromium"]
    return next((str(item) for item in candidates if item and Path(item).exists()), None)


def browser_gate() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError("Playwright is required for Page-3 visual certification") from exc
    for package in ("dash", "dash-mantine-components", "dash-ag-grid", "dash-iconify"):
        try: importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc: raise RuntimeError(f"Missing dashboard runtime dependency: {package}") from exc
    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for old in SCREENSHOT_DIR.glob("mechanisms_*.png"): old.unlink()
    port = _free_port(); base = f"http://127.0.0.1:{port}"
    env = os.environ.copy(); env.update({"DASH_HOST": "127.0.0.1", "DASH_PORT": str(port), "DASH_DEBUG": "0", "PYTHONUNBUFFERED": "1"})
    log = (SCREENSHOT_DIR / "dashboard_server.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "research.python.dashboard.app_v3"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
    try:
        _wait_server(base, process)
        with sync_playwright() as p:
            try: browser = p.chromium.launch(headless=True)
            except Exception:
                executable = _browser_executable()
                if not executable: raise RuntimeError("Chromium/Chrome executable unavailable")
                browser = p.chromium.launch(headless=True, executable_path=executable)
            for width, height in ((1366, 768), (1440, 900), (1920, 1080)):
                context = browser.new_context(viewport={"width": width, "height": height}); page = context.new_page(); console_errors=[]; page_errors=[]
                page.on("console", lambda msg: console_errors.append(msg.text) if (msg.type == "error" or "AG Grid: warning #29" in msg.text) else None); page.on("pageerror", lambda exc: page_errors.append(str(exc)))
                page.goto(base + "/mechanisms", wait_until="networkidle")
                page.locator("#mechanisms-faithfulness-accounting").wait_for(state="visible", timeout=15000)
                text = page.locator("#v3-mechanisms-content").inner_text()
                for token in ("100% Faithfulness Accounting", "Loss decomposition", "Claim diagnostics", "Quality mechanisms"):
                    if token not in text: raise RuntimeError(f"Mechanisms UI missing {token}")
                page.get_by_text("Claim diagnostics", exact=True).click(); page.locator("#mechanisms-claim-validation-matrix").wait_for(state="visible", timeout=5000)
                # The Claim Matrix remains a required rendered diagnostic. Drawer interaction is
                # certified on the Quality Map using a real Plotly marker; arbitrary heatmap
                # drag-layer coordinates are brittle and can miss cells after responsive relayout.
                page.get_by_text("Quality mechanisms", exact=True).click(); page.locator("#mechanisms-quality-map").wait_for(state="visible", timeout=5000)
                points = page.locator("#mechanisms-quality-map .scatterlayer path.point")
                if points.count() == 0:
                    points = page.locator("#mechanisms-quality-map .scatterlayer .point")
                if points.count() == 0:
                    raise RuntimeError("Quality Map rendered without clickable Plotly markers")
                points.first.click(force=True)
                try:
                    page.locator("#mechanisms-detail-drawer-body-content").wait_for(state="visible", timeout=6000)
                except Exception as exc:
                    body = page.locator("body").inner_text()[:6000]
                    raise RuntimeError(
                        "Quality-map marker click did not open the Mechanisms detail drawer. "
                        f"console={console_errors} page={page_errors} body={body!r}"
                    ) from exc
                duplicate_ids = page.evaluate(
                    "() => { const c={}; document.querySelectorAll('[id]').forEach(e => c[e.id]=(c[e.id]||0)+1); return Object.fromEntries(Object.entries(c).filter(([,n])=>n>1)); }"
                )
                if duplicate_ids:
                    raise RuntimeError(f"Duplicate DOM ids after Mechanisms drawer open: {duplicate_ids}")
                layout = page.evaluate("() => ({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,bw:document.body.scrollWidth})")
                if int(layout["sw"]) > int(layout["cw"]) + 2 or int(layout["bw"]) > int(layout["cw"]) + 2: raise RuntimeError(f"Horizontal overflow {width}x{height}: {layout}")
                if console_errors or page_errors: raise RuntimeError(f"Browser errors: console={console_errors} page={page_errors}")
                page.screenshot(path=str(SCREENSHOT_DIR / f"mechanisms_cross_{width}x{height}.png"), full_page=True); context.close()

            # Quality deep-link focus must affect the initial figure and preserve dataset identity.
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page(); console_errors=[]; page_errors=[]
            page.on("console", lambda msg: console_errors.append(msg.text) if (msg.type == "error" or "AG Grid: warning #29" in msg.text) else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.goto(base + "/mechanisms?tab=quality&dataset=FREDDIE&model=qwen3_8b&evidence=S1", wait_until="networkidle")
            page.locator("#mechanisms-quality-map").wait_for(state="visible", timeout=15000)
            focus_points = page.locator("#mechanisms-quality-map .scatterlayer path.point")
            if focus_points.count() != 2:
                raise RuntimeError(f"Mechanisms deep-link focus did not filter initial figure: points={focus_points.count()}")
            selected_text = page.locator("#mechanisms-selected-option").inner_text()
            if "Freddie Mac" not in selected_text or "Qwen3 8B × S1" not in selected_text:
                raise RuntimeError(f"Mechanisms deep-link lost dataset/option identity: {selected_text!r}")
            eff_href = page.get_by_role("link", name="Mở Effectiveness").first.get_attribute("href") or ""
            case_href = page.get_by_role("link", name="Mở Case Explorer").first.get_attribute("href") or ""
            if "dataset=FREDDIE" not in eff_href or "dataset=FREDDIE" not in case_href:
                raise RuntimeError(f"Mechanisms drill-through lost dataset identity: effectiveness={eff_href} cases={case_href}")
            if console_errors or page_errors:
                raise RuntimeError(f"Mechanisms quality deep-link browser errors: console={console_errors} page={page_errors}")
            context.close()

            # Validation-status deep link must open Claims and materialize exactly one status column.
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page(); console_errors=[]; page_errors=[]
            page.on("console", lambda msg: console_errors.append(msg.text) if (msg.type == "error" or "AG Grid: warning #29" in msg.text) else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.goto(base + "/mechanisms?validation_status=NOT_VERIFIABLE", wait_until="networkidle")
            page.locator("#mechanisms-claim-validation-matrix").wait_for(state="visible", timeout=15000)
            x_values = page.locator("#mechanisms-claim-validation-matrix .js-plotly-plot").evaluate(
                "(el) => el.data.map(trace => Array.from(trace.x || []))"
            )
            if not x_values or any(values != ["NOT_VERIFIABLE"] for values in x_values):
                raise RuntimeError(f"Validation-status deep link did not constrain matrix columns: {x_values}")
            if console_errors or page_errors:
                raise RuntimeError(f"Mechanisms validation deep-link browser errors: console={console_errors} page={page_errors}")
            context.close()
            browser.close()
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        log.close()
    print(f"DASHBOARD_MECHANISMS_0046_BROWSER=PASS viewports=3 screenshots={SCREENSHOT_DIR}")


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--browser", action="store_true"); args = parser.parse_args()
    data_gate(); source_gate()
    if args.browser: browser_gate()
    print("DASHBOARD_MECHANISMS_0046=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

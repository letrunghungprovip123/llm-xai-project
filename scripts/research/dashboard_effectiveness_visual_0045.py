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

from research.python.dashboard.v3.effectiveness_model import build_effectiveness_model
from research.python.dashboard.v3.figures import (
    effectiveness_contrast_plot,
    effectiveness_effect_size_plot,
    effectiveness_evidence_profiles,
    effectiveness_metric_matrix,
    effectiveness_reliability_map,
)
from research.python.dashboard.v3.repository import get_v3_repository

ROOT = PROJECT_ROOT
SCREENSHOT_DIR = ROOT / ".researchops/visual_effectiveness_certification"


def data_gate() -> None:
    repo = get_v3_repository()
    for scope in ("HOME_CREDIT", "FREDDIE", "CROSS_DATASET"):
        model = build_effectiveness_model(repo, scope, "vi")
        expected_options = 36 if scope == "CROSS_DATASET" else 18
        expected_metrics = 144 if scope == "CROSS_DATASET" else 72
        expected_effects = 6 if scope == "CROSS_DATASET" else 3
        expected_contrasts = 66 if scope == "CROSS_DATASET" else 33
        if len(model.option_rows) != expected_options:
            raise RuntimeError(f"Option topology drift {scope}: {len(model.option_rows)}")
        if len(model.secondary_metric_rows) != expected_metrics:
            raise RuntimeError(f"Metric topology drift {scope}: {len(model.secondary_metric_rows)}")
        if len(model.effect_rows) != expected_effects:
            raise RuntimeError(f"Omnibus topology drift {scope}: {len(model.effect_rows)}")
        if len(model.contrast_rows) != expected_contrasts:
            raise RuntimeError(f"Planned-contrast topology drift {scope}: {len(model.contrast_rows)}")
        if model.rank_rows:
            raise RuntimeError("Replication/rank-stability conclusions leaked back into Effectiveness")

        cross = scope == "CROSS_DATASET"
        reliability = effectiveness_reliability_map(model.option_rows, cross_dataset=cross)
        profiles = effectiveness_evidence_profiles(model.option_rows, cross_dataset=cross)
        matrix = effectiveness_metric_matrix(model.secondary_metric_rows, cross_dataset=cross)
        effects = effectiveness_effect_size_plot(model.effect_rows, cross_dataset=cross)
        contrasts = effectiveness_contrast_plot(model.contrast_rows, cross_dataset=cross, family="evidence_vs_s0")
        if any(len(fig.data) == 0 for fig in (reliability, profiles, matrix, effects, contrasts)):
            raise RuntimeError(f"Effectiveness figure unexpectedly empty: {scope}")
        if tuple(reliability.layout.xaxis.range) != (0, 1.02) or tuple(reliability.layout.yaxis.range) != (0, 1.02):
            raise RuntimeError("Reliability Map must preserve fixed 0–100% comparable axes")
        if cross:
            if tuple(reliability.layout.xaxis2.range) != (0, 1.02) or tuple(reliability.layout.yaxis2.range) != (0, 1.02):
                raise RuntimeError("Cross-dataset Reliability Map axes are not synchronized")
            if len(matrix.data) != 2 or any(float(trace.zmin) != 0 or float(trace.zmax) != 1 for trace in matrix.data):
                raise RuntimeError("Cross-dataset metric matrices must retain one shared 0–100% scale")
        if int(effects.layout.height or 0) > 300:
            raise RuntimeError("Major Effects regressed into an oversized chart")

    focused = build_effectiveness_model(repo, "FREDDIE", "vi", search="?tab=secondary&dataset=FREDDIE&model=qwen3_8b&evidence=S4")
    if focused.initial_tab != "secondary" or focused.focus_model != "qwen3_8b" or focused.focus_evidence != "S4" or focused.focus_dataset != "FREDDIE":
        raise RuntimeError("Effectiveness URL focus contract failed")
    print("DASHBOARD_EFFECTIVENESS_0045_DATA=PASS scopes=3 options=18x2 metrics=144 contrasts=66")


def source_gate() -> None:
    page = (ROOT / "research/python/dashboard/v3/pages/effectiveness.py").read_text(encoding="utf-8")
    model = (ROOT / "research/python/dashboard/v3/effectiveness_model.py").read_text(encoding="utf-8")
    figures = (ROOT / "research/python/dashboard/v3/figures.py").read_text(encoding="utf-8")
    callbacks = (ROOT / "research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    required = (
        "Reliability Map",
        "Evidence Response Profiles",
        "Option × Metric matrix",
        "Major Effects",
        "Contrast Effect Plot",
        "Primary performance",
        "Secondary metrics",
        "Statistical evidence",
        "effectiveness-detail-drawer",
    )
    for token in required:
        if token not in page:
            raise RuntimeError(f"Missing Page-2 redesign token: {token}")
    for forbidden in ("scipy", "statsmodels", "wilcoxon", "multipletests", "bootstrap(", "visualization_v2", "get_dashboard_repository"):
        if any(forbidden in source for source in (page, model, figures, callbacks)):
            raise RuntimeError(f"Scientific/legacy token leaked into Page 2: {forbidden}")
    for replication_token in ("Replication status", "material_heterogeneity", "rank_stability"):
        if replication_token in page or replication_token in model:
            raise RuntimeError(f"Replication conclusion leaked into Effectiveness: {replication_token}")
    if 'columnSize="sizeToFit"' in page:
        raise RuntimeError("Hidden-tab AgGrid must not call sizeToFit at zero width")
    if "effectiveness-detail-drawer-body-content" not in page or "effectiveness-detail-drawer-title-content" not in page:
        raise RuntimeError("Effectiveness Drawer content IDs are not portal-safe")
    print("DASHBOARD_EFFECTIVENESS_0045_SOURCE=PASS science=read-only replication_conclusions=excluded")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_server(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last = None
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Dashboard server exited early: {process.returncode}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception as exc:
            last = exc
        time.sleep(0.25)
    raise RuntimeError(f"Dashboard did not become ready: {last}")


def _browser_executable() -> str | None:
    candidates = [
        shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("google-chrome"), shutil.which("google-chrome-stable"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    return next((str(item) for item in candidates if item and Path(item).exists()), None)


def browser_gate() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError("Playwright is required for Page-2 visual certification") from exc
    for package in ("dash", "dash-mantine-components", "dash-ag-grid", "dash-iconify"):
        try:
            importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"Missing dashboard runtime dependency: {package}") from exc

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for old in SCREENSHOT_DIR.glob("effectiveness_*.png"):
        old.unlink()
    port = _free_port(); base = f"http://127.0.0.1:{port}"
    env = os.environ.copy(); env.update({"DASH_HOST": "127.0.0.1", "DASH_PORT": str(port), "DASH_DEBUG": "0", "PYTHONUNBUFFERED": "1"})
    log = (SCREENSHOT_DIR / "dashboard_server.log").open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "research.python.dashboard.app_v3"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
    try:
        _wait_server(base, process)
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception:
                executable = _browser_executable()
                if not executable:
                    raise RuntimeError("Chromium/Chrome executable unavailable")
                browser = p.chromium.launch(headless=True, executable_path=executable)
            for width, height in ((1366, 768), (1440, 900), (1920, 1080)):
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page(); console_errors=[]; page_errors=[]
                page.on("console", lambda msg: console_errors.append(msg.text) if (msg.type == "error" or "AG Grid: warning #29" in msg.text) else None)
                page.on("pageerror", lambda exc: page_errors.append(str(exc)))
                page.goto(base + "/effectiveness", wait_until="networkidle")
                page.locator("#effectiveness-reliability-map").wait_for(state="visible", timeout=15000)
                text = page.locator("#v3-effectiveness-content").inner_text()
                for token in ("Reliability Map", "Primary performance", "Secondary metrics", "Statistical evidence"):
                    if token not in text:
                        raise RuntimeError(f"Effectiveness UI missing {token}")
                # Reliability click opens detail drawer. Click a real Plotly marker, not an
                # arbitrary drag-layer coordinate (which may land between sparse points and
                # therefore never produce dcc.Graph.clickData).
                points = page.locator("#effectiveness-reliability-map .scatterlayer path.point")
                if points.count() == 0:
                    points = page.locator("#effectiveness-reliability-map .scatterlayer .point")
                if points.count() == 0:
                    raise RuntimeError("Reliability Map rendered without clickable Plotly markers")
                points.first.click(force=True)
                try:
                    page.locator("#effectiveness-detail-drawer-body-content").wait_for(state="visible", timeout=6000)
                except Exception as exc:
                    body = page.locator("body").inner_text()[:6000]
                    raise RuntimeError(
                        "Reliability marker click did not open the Effectiveness detail drawer. "
                        f"console={console_errors} page={page_errors} body={body!r}"
                    ) from exc
                duplicate_ids = page.evaluate(
                    "() => { const c={}; document.querySelectorAll('[id]').forEach(e => c[e.id]=(c[e.id]||0)+1); return Object.fromEntries(Object.entries(c).filter(([,n])=>n>1)); }"
                )
                if duplicate_ids:
                    raise RuntimeError(f"Duplicate DOM ids after Effectiveness drawer open: {duplicate_ids}")
                # Drawer is rendered through a Mantine Portal; certify the visible drawer body,
                # then close it before clicking controls underneath the overlay.
                page.keyboard.press("Escape")
                page.locator("#effectiveness-detail-drawer-body-content").wait_for(state="hidden", timeout=4000)
                # Other tabs render their core figures.
                page.get_by_text("Secondary metrics", exact=True).click(); page.locator("#effectiveness-metric-matrix").wait_for(state="visible", timeout=5000)
                page.get_by_text("Statistical evidence", exact=True).click(); page.locator("#effectiveness-major-effects").wait_for(state="visible", timeout=5000); page.locator("#effectiveness-contrast-effect-plot").wait_for(state="visible", timeout=5000)
                contrast_points = page.locator("#effectiveness-contrast-effect-plot .scatterlayer path.point")
                if contrast_points.count() == 0:
                    raise RuntimeError("Contrast Effect Plot rendered without clickable markers")
                contrast_points.first.click(force=True)
                page.locator("#effectiveness-detail-drawer-body-content").wait_for(state="visible", timeout=6000)
                duplicate_ids = page.evaluate(
                    "() => { const c={}; document.querySelectorAll('[id]').forEach(e => c[e.id]=(c[e.id]||0)+1); return Object.fromEntries(Object.entries(c).filter(([,n])=>n>1)); }"
                )
                if duplicate_ids:
                    raise RuntimeError(f"Duplicate DOM ids after contrast drawer open: {duplicate_ids}")
                page.keyboard.press("Escape")
                page.locator("#effectiveness-detail-drawer-body-content").wait_for(state="hidden", timeout=4000)
                layout = page.evaluate("() => ({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,bw:document.body.scrollWidth})")
                if int(layout["sw"]) > int(layout["cw"]) + 2 or int(layout["bw"]) > int(layout["cw"]) + 2:
                    raise RuntimeError(f"Horizontal overflow {width}x{height}: {layout}")
                if console_errors or page_errors:
                    raise RuntimeError(f"Browser errors: console={console_errors} page={page_errors}")
                page.screenshot(path=str(SCREENSHOT_DIR / f"effectiveness_cross_{width}x{height}.png"), full_page=True)
                context.close()

            # Deep-link focus must affect the initial figure and preserve dataset identity.
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page(); console_errors=[]; page_errors=[]
            page.on("console", lambda msg: console_errors.append(msg.text) if (msg.type == "error" or "AG Grid: warning #29" in msg.text) else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.goto(base + "/effectiveness?tab=primary&dataset=FREDDIE&model=qwen3_8b&evidence=S1", wait_until="networkidle")
            page.locator("#effectiveness-reliability-map").wait_for(state="visible", timeout=15000)
            focus_points = page.locator("#effectiveness-reliability-map .scatterlayer path.point")
            if focus_points.count() != 2:
                raise RuntimeError(f"Effectiveness deep-link focus did not filter initial figure: points={focus_points.count()}")
            selected_text = page.locator("#effectiveness-selected-option").inner_text()
            if "Freddie Mac" not in selected_text or "Qwen3 8B × S1" not in selected_text:
                raise RuntimeError(f"Effectiveness deep-link lost dataset/option identity: {selected_text!r}")
            mech_href = page.get_by_role("link", name="Mở Mechanisms").first.get_attribute("href") or ""
            case_href = page.get_by_role("link", name="Mở Case Explorer").first.get_attribute("href") or ""
            if "dataset=FREDDIE" not in mech_href or "dataset=FREDDIE" not in case_href:
                raise RuntimeError(f"Effectiveness drill-through lost dataset identity: mechanisms={mech_href} cases={case_href}")
            if console_errors or page_errors:
                raise RuntimeError(f"Effectiveness deep-link browser errors: console={console_errors} page={page_errors}")
            context.close()
            browser.close()
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        log.close()
    print(f"DASHBOARD_EFFECTIVENESS_0045_BROWSER=PASS viewports=3 screenshots={SCREENSHOT_DIR}")


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--browser", action="store_true"); args = parser.parse_args()
    data_gate(); source_gate()
    if args.browser: browser_gate()
    print("DASHBOARD_EFFECTIVENESS_0045=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

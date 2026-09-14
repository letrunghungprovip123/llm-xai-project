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

from research.python.dashboard.v3.figures import (
    overview_major_effects,
    overview_option_landscape,
    overview_validation_composition,
)
from research.python.dashboard.v3.overview_model import build_overview_model
from research.python.dashboard.v3.repository import get_v3_repository


ROOT = PROJECT_ROOT
SCREENSHOT_DIR = ROOT / ".researchops/visual_overview_certification"


def data_gate() -> None:
    repo = get_v3_repository()
    for scope in ("HOME_CREDIT", "FREDDIE", "CROSS_DATASET"):
        model = build_overview_model(repo, scope, "en")
        if model.locale != "vi":
            raise RuntimeError(f"Overview locale drift for {scope}: {model.locale}")
        if len(model.cards) != 4:
            raise RuntimeError(f"Expected 4 Overview KPI cards for {scope}, found {len(model.cards)}")
        if len(model.option_rows) != 18:
            raise RuntimeError(f"Expected 18 options for {scope}, found {len(model.option_rows)}")
        if len(model.effects) != 3:
            raise RuntimeError(f"Expected 3 omnibus effect families for {scope}, found {len(model.effects)}")
        if not all(value.report_number_id for card in model.cards for value in card.values):
            raise RuntimeError(f"Missing KPI provenance for {scope}")

        landscape = overview_option_landscape(model.option_rows, cross_dataset=scope == "CROSS_DATASET")
        effects = overview_major_effects(model.effects, cross_dataset=scope == "CROSS_DATASET")
        validation = overview_validation_composition(model.validation_rows)
        figures = (landscape, effects, validation)
        if any(len(figure.data) == 0 for figure in figures):
            raise RuntimeError(f"Overview figure unexpectedly empty for {scope}")
        if int(landscape.layout.height or 0) > 380:
            raise RuntimeError(f"Landscape height regressed for {scope}: {landscape.layout.height}")
        if int(effects.layout.height or 0) > 290:
            raise RuntimeError(f"Major Effects is no longer compact for {scope}: {effects.layout.height}")
        if int(validation.layout.height or 0) > 260:
            raise RuntimeError(f"Validation composition is no longer compact for {scope}: {validation.layout.height}")
        effect_order = tuple(str(item) for item in effects.layout.yaxis.categoryarray)
        if effect_order != ("Model", "Evidence", "Model × Evidence"):
            raise RuntimeError(f"Major Effects order drift for {scope}: {effect_order}")
        if float(validation.layout.legend.y or 0) <= 1.0:
            raise RuntimeError("Validation legend must remain visibly above the plot area")

        if scope == "CROSS_DATASET":
            if len(model.validation_rows) != 2:
                raise RuntimeError("Cross-dataset validation composition must keep the studies separate")
            heatmaps = [trace for trace in landscape.data if getattr(trace, "type", None) == "heatmap"]
            if len(heatmaps) != 2 or any(float(trace.zmin) != 0.0 or float(trace.zmax) != 1.0 for trace in heatmaps):
                raise RuntimeError("Cross-dataset heatmaps must share the frozen 0–100% color scale")
            annotation_text = {str(item.text).replace("<b>", "").replace("</b>", "") for item in landscape.layout.annotations}
            if annotation_text != {"Home Credit", "Freddie Mac"}:
                raise RuntimeError(f"Cross-dataset heatmap study labels drifted: {annotation_text}")
            if sum(int(row["count"]) for row in model.replication_counts) != 33:
                raise RuntimeError("Replication summary must cover all 33 certified contrasts")
            if model.replication_scope != "MODEL_REVISION_UNKNOWN":
                raise RuntimeError("Replication scope drift")
            if model.robust_recommendation_status != "NO_ROBUST_RECOMMENDATION":
                raise RuntimeError("Robust recommendation status drift")
        elif len(model.validation_rows) != 1:
            raise RuntimeError(f"Study Overview must contain one validation row for {scope}")

    print("DASHBOARD_OVERVIEW_REDESIGN_DATA=PASS scopes=3 options=18 effects=3 replication_contrasts=33")


def source_gate() -> None:
    shell = (ROOT / "research/python/dashboard/v3/shell.py").read_text(encoding="utf-8")
    page = (ROOT / "research/python/dashboard/v3/pages/overview.py").read_text(encoding="utf-8")
    model = (ROOT / "research/python/dashboard/v3/overview_model.py").read_text(encoding="utf-8")
    figures = (ROOT / "research/python/dashboard/v3/figures.py").read_text(encoding="utf-8")
    app = (ROOT / "research/python/dashboard/app_v3.py").read_text(encoding="utf-8")

    if "dmc.SegmentedControl(id=LOCALE_SELECT" in shell:
        raise RuntimeError("Locale selector reintroduced")
    if 'storage_type="memory"' not in shell or 'data="vi"' not in shell:
        raise RuntimeError("Vietnamese-only locale store is not locked")
    for visible_version in ("Dashboard v3", "Dashboard v4", "visualization-data-v3", "LLM-XAI v3"):
        if visible_version in page or visible_version in shell or visible_version in app:
            raise RuntimeError(f"Visible product version token reintroduced: {visible_version}")
    for forbidden in ("scipy", "statsmodels", "wilcoxon", "multipletests", "bootstrap("):
        if forbidden in model or forbidden in figures or forbidden in page:
            raise RuntimeError(f"Scientific computation token found in Overview presentation layer: {forbidden}")
    required = (
        "overview-kpi-grid",
        "overview-primary-grid",
        "overview-secondary-grid",
        "overview-model-evidence-landscape",
        "overview-major-effects",
        "overview-validation-composition",
        "overview-detail-drawer",
        "overview-study-routes",
    )
    for token in required:
        if token not in page:
            raise RuntimeError(f"Missing Overview visual contract token: {token}")
    for generic_english in ("Multi-dataset analytical research", ">Export<", "Study scope", "Explore deeper", "Research overview"):
        if generic_english in shell or generic_english in page:
            raise RuntimeError(f"Generic English UI copy reintroduced: {generic_english}")
    print("DASHBOARD_OVERVIEW_REDESIGN_SOURCE=PASS language=vi-only version_label=absent scientific_recompute=forbidden")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_server(url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.time() + 45
    last = None
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Dashboard server exited early with code {process.returncode}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception as exc:  # pragma: no cover - runtime diagnostic only
            last = exc
        time.sleep(0.25)
    raise RuntimeError(f"Dashboard server did not become ready: {last}")


def _browser_executable() -> str | None:
    candidates = [
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
        shutil.which("google-chrome"),
        shutil.which("google-chrome-stable"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    return next((str(item) for item in candidates if item and Path(item).exists()), None)


def browser_gate() -> None:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError("Playwright is required for Overview visual certification") from exc
    for package in ("dash", "dash-mantine-components", "dash-iconify"):
        try:
            importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"Missing dashboard runtime dependency: {package}") from exc

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for old in SCREENSHOT_DIR.glob("overview_*.png"):
        old.unlink()

    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update({"DASH_HOST": "127.0.0.1", "DASH_PORT": str(port), "DASH_DEBUG": "0", "PYTHONUNBUFFERED": "1"})
    log = (SCREENSHOT_DIR / "dashboard_server.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-m", "research.python.dashboard.app_v3"],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_server(base, process)
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except Exception:
                executable = _browser_executable()
                if not executable:
                    raise RuntimeError("Chromium/Chrome executable is unavailable")
                browser = p.chromium.launch(headless=True, executable_path=executable)

            for width, height in ((1366, 768), (1440, 900), (1920, 1080)):
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                console_errors: list[str] = []
                page_errors: list[str] = []
                page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
                page.on("pageerror", lambda exc: page_errors.append(str(exc)))
                page.goto(base + "/", wait_until="networkidle")
                page.locator("#v3-overview-content .overview-page--golden").wait_for(state="visible", timeout=15000)

                if page.locator("#v3-locale-select").count() != 0:
                    raise RuntimeError("Locale selector is visible after Vietnamese-only redesign")
                if "Tổng quan nghiên cứu" not in page.locator("#v3-overview-content").inner_text():
                    raise RuntimeError("Vietnamese Overview title missing")
                if page.locator(".overview-kpi").count() != 4:
                    raise RuntimeError("Overview must render exactly four KPI components")
                for graph_id in ("overview-model-evidence-landscape", "overview-major-effects", "overview-validation-composition"):
                    page.locator(f"#{graph_id}").wait_for(state="visible", timeout=8000)

                # Every Plotly host must fit inside its analytical card. This is the
                # regression gate for the crop/overflow visible in the first golden-page build.
                for selector in (".overview-chart--landscape", ".overview-chart--effects", ".overview-chart--validation"):
                    metrics = page.locator(selector).evaluate("""node => {
                      const graph = node.querySelector('.overview-chart__graph');
                      const card = node.getBoundingClientRect();
                      const box = graph.getBoundingClientRect();
                      return {cardBottom: card.bottom, graphBottom: box.bottom, cardTop: card.top, graphTop: box.top};
                    }""")
                    if float(metrics["graphBottom"]) > float(metrics["cardBottom"]) + 2:
                        raise RuntimeError(f"Overview graph is clipped by its card {selector}: {metrics}")
                    if float(metrics["graphTop"]) < float(metrics["cardTop"]):
                        raise RuntimeError(f"Overview graph overlaps its card header {selector}: {metrics}")

                validation_legend = page.locator("#overview-validation-composition .legend")
                if validation_legend.count() == 0 or not validation_legend.first.is_visible():
                    raise RuntimeError("Claim Validation Composition legend is not visible")

                # Cross-dataset is the default landing scope and must preserve certified statuses.
                text = page.locator("#v3-overview-content").inner_text()
                if "MODEL_REVISION_UNKNOWN" not in text or "NO_ROBUST_RECOMMENDATION" not in text:
                    raise RuntimeError("Cross-dataset Overview lost certified status markers")

                # Heatmap click must open the analytical detail drawer.
                heatmap = page.locator("#overview-model-evidence-landscape .nsewdrag").first
                box = heatmap.bounding_box()
                if not box:
                    raise RuntimeError("Overview heatmap interaction layer was not rendered")
                heatmap.click(position={"x": box["width"] * 0.30, "y": box["height"] * 0.38})
                page.locator("#overview-detail-drawer").wait_for(state="visible", timeout=4000)

                # Dataset scope interactions must update the same page, not navigate away.
                for label in ("Home Credit", "Freddie Mac", "Cross-dataset"):
                    page.locator("#v3-dataset-scope-select").get_by_text(label, exact=True).click(timeout=3000)
                    page.wait_for_timeout(450)
                    if label not in page.locator("#v3-overview-content").inner_text():
                        raise RuntimeError(f"Overview scope switch failed: {label}")

                layout = page.evaluate("""() => ({scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth, bodyWidth: document.body.scrollWidth})""")
                if int(layout["scrollWidth"]) > int(layout["clientWidth"]) + 2 or int(layout["bodyWidth"]) > int(layout["clientWidth"]) + 2:
                    raise RuntimeError(f"Horizontal overflow at {width}x{height}: {layout}")
                if console_errors or page_errors:
                    raise RuntimeError(f"Browser errors: console={console_errors}, page={page_errors}")

                page.screenshot(path=str(SCREENSHOT_DIR / f"overview_cross_{width}x{height}.png"), full_page=True)
                context.close()
            browser.close()
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        log.close()

    print(f"DASHBOARD_OVERVIEW_REDESIGN_BROWSER=PASS viewports=3 screenshots={SCREENSHOT_DIR}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    data_gate()
    source_gate()
    if args.browser:
        browser_gate()
    print("DASHBOARD_OVERVIEW_REDESIGN=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

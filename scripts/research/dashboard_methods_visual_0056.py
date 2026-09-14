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
from urllib.parse import urlencode
from urllib.request import urlopen

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from research.python.dashboard.v3.methods_model import (
    CAPABILITY_GAP,
    build_methods_model,
    finding_by_id,
    metric_by_key,
    report_by_id,
    schema_for_table,
)
from research.python.dashboard.v3.repository import get_v3_repository

ROOT = PROJECT_ROOT
SCREENSHOT_DIR = ROOT / ".researchops/visual_methods_certification"


def data_gate() -> None:
    model = build_methods_model(get_v3_repository(), "vi")
    expected = {
        "research_questions": 6,
        "metric_dictionary": 41,
        "report_source_index": 275,
        "table_names": 31,
        "visualization_dictionary": 560,
        "findings": 8,
        "limitations": 11,
    }
    actual = {
        "research_questions": len(model.research_questions),
        "metric_dictionary": len(model.metric_dictionary),
        "report_source_index": len(model.report_source_index),
        "table_names": len(model.table_names),
        "visualization_dictionary": len(model.visualization_dictionary),
        "findings": len(model.findings),
        "limitations": len(model.limitations),
    }
    if actual != expected:
        raise RuntimeError(f"Methods audit topology drift: {actual} != {expected}")
    if model.release["parent_release_id"] != "certified_multidataset_analytical_release_v1" or model.release["release_id"] != "visualization-data-v3":
        raise RuntimeError("Methods certified release lineage drift")
    if model.release["scientific_recomputation_allowed"] is not False:
        raise RuntimeError("Methods release must forbid scientific recomputation")
    for key in ("metric_formula_capability", "validator_readiness_capability", "template_readiness_capability"):
        if model.method_evidence[key] != CAPABILITY_GAP:
            raise RuntimeError(f"Methods capability state drift: {key}")

    report_id = "dataset::HOME_CREDIT::mean_e2e"
    report = report_by_id(model, report_id)
    if report is None or report["source_artifact_id"] != "home_credit_generation_metrics" or len(str(report["source_sha256"])) != 64:
        raise RuntimeError("Methods exact report provenance mapping drift")
    if not schema_for_table(model, "case_generation_metrics"):
        raise RuntimeError("Methods visualization schema lookup failed")
    finding = finding_by_id(model, "F_ROBUSTNESS_MARGIN")
    if finding is None or finding["supporting_report_refs"] != ("robustness::margin::status",):
        raise RuntimeError("Methods finding-to-report chain drift")
    if tuple(row["limitation_id"] for row in finding["limitations"]) != ("M27_MARGIN_SENSITIVITY",):
        raise RuntimeError("Methods finding-to-limitation chain drift")

    metric_key = "end_to_end_faithfulness_yield::DATASET_SUMMARY::PRIMARY"
    deep = build_methods_model(
        get_v3_repository(),
        "vi",
        search="?" + urlencode({
            "tab": "traceability",
            "report": report_id,
            "table": "case_generation_metrics",
            "finding": "F_ROBUSTNESS_MARGIN",
            "metric_key": metric_key,
        }),
    )
    if deep.initial_tab != "traceability" or deep.selected_report_id != report_id or deep.selected_table_name != "case_generation_metrics" or deep.selected_finding_id != "F_ROBUSTNESS_MARGIN":
        raise RuntimeError("Methods direct URL-state contract failed")
    if deep.selected_metric_key != metric_key or metric_by_key(deep, deep.selected_metric_key)["metric_key"] != metric_key:
        raise RuntimeError("Methods exact metric-key deep-link resolution failed")

    ambiguous = build_methods_model(get_v3_repository(), "vi", search="?metric=end_to_end_faithfulness_yield")
    matching = [row for row in ambiguous.metric_dictionary if row["metric_id"] == "end_to_end_faithfulness_yield"]
    if len(matching) < 2:
        raise RuntimeError("Methods ambiguity guard fixture drift")
    if ambiguous.selected_metric_key not in ambiguous.metric_keys:
        raise RuntimeError("Methods ambiguous bare metric id must resolve only to a valid deterministic default")

    print("DASHBOARD_METHODS_0056_DATA=PASS rqs=6 metrics=41 provenance=275 tables=31 schema=560 findings=8 limitations=11")


def source_gate() -> None:
    page = (ROOT / "research/python/dashboard/v3/pages/methods.py").read_text(encoding="utf-8")
    model = (ROOT / "research/python/dashboard/v3/methods_model.py").read_text(encoding="utf-8")
    callbacks = (ROOT / "research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    joined = page + "\n" + model + "\n" + callbacks
    for token in (
        "Release provenance",
        "Research Question Registry",
        "Metric role & unit",
        "Report Number / Provenance Explorer",
        "Visualization Schema Explorer",
        "Finding Evidence Chain",
        "11 certified limitations",
    ):
        if token not in page:
            raise RuntimeError(f"Missing Methods redesign token: {token}")
    for forbidden in (
        "visualization_v2",
        "get_dashboard_repository",
        "research.python.claim_validation",
        "research.python.statistical_analysis",
        "research.python.decision_support",
        "statsmodels",
        "scipy",
        ".rank(",
    ):
        if forbidden in joined:
            raise RuntimeError(f"Scientific/legacy token leaked into Methods: {forbidden}")
    if "dmc.Tabs" in page or 'columnSize="sizeToFit"' in page or ('dmc.Button' in page and 'href=' in page):
        raise RuntimeError("Methods reintroduced a known runtime-danger component pattern")
    for token in ('data-testid": "methods-provenance-detail"', 'data-testid": "methods-finding-detail"', 'data-testid": "methods-release-lineage"'):
        if token not in page:
            raise RuntimeError(f"Missing Methods test-owned semantic selector: {token}")
    if CAPABILITY_GAP in page:
        raise RuntimeError("Methods page duplicated capability-gap literal instead of consuming model contract")
    if 'Input(LOCATION, "search")' not in callbacks or 'Input(LOCATION, "pathname")' not in callbacks:
        raise RuntimeError("Methods URL state is not first-class")
    if '"metric_key": _query_value(raw, "metric_key")' not in model or "len(matching) == 1" not in model:
        raise RuntimeError("Methods canonical metric-key / ambiguity guard contract missing")
    print("DASHBOARD_METHODS_0056_SOURCE=PASS provenance=exact registry=certified metric_identity=composite capability_gap=model_owned science=read-only")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _browser_executable() -> str | None:
    candidates = [
        shutil.which("chromium"), shutil.which("chromium-browser"), shutil.which("google-chrome"), shutil.which("google-chrome-stable"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    return next((str(x) for x in candidates if x and Path(x).exists()), None)


def _log_tail(path: Path, lines: int = 100) -> str:
    if not path.is_file():
        return "<server log unavailable>"
    return "\n".join(path.read_text(encoding="utf-8", errors="replace").splitlines()[-lines:])


def _wait_server(url: str, process: subprocess.Popen[str], log_path: Path) -> None:
    deadline = time.time() + 45
    last = None
    while time.time() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Dashboard server exited early: {process.returncode}\n--- server log tail ---\n{_log_tail(log_path)}")
        try:
            with urlopen(url, timeout=1) as response:
                if response.status < 500:
                    return
        except Exception as exc:
            last = exc
        time.sleep(0.25)
    raise RuntimeError(f"Dashboard did not become ready: {last}\n--- server log tail ---\n{_log_tail(log_path)}")


def _duplicates(page) -> dict:
    return page.evaluate("() => { const c={}; document.querySelectorAll('[id]').forEach(e => c[e.id]=(c[e.id]||0)+1); return Object.fromEntries(Object.entries(c).filter(([,n])=>n>1)); }")


def _layout(page) -> dict:
    return page.evaluate("() => ({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,bw:document.body.scrollWidth})")


def _assert_no_errors(page, console_errors, page_errors, request_failures, *, label: str) -> None:
    dupes = _duplicates(page)
    layout = _layout(page)
    if dupes:
        raise RuntimeError(f"{label} duplicate DOM IDs: {dupes}")
    if int(layout["sw"]) > int(layout["cw"]) + 2 or int(layout["bw"]) > int(layout["cw"]) + 2:
        raise RuntimeError(f"{label} horizontal overflow: {layout}")
    if console_errors or page_errors or request_failures:
        raise RuntimeError(f"{label} browser errors console={console_errors} page={page_errors} requests={request_failures}")


def browser_gate() -> None:
    try:
        from research.python.dashboard.app_v3 import create_app_v3
        app = create_app_v3()
        if app is None:
            raise RuntimeError("create_app_v3 returned None")
    except Exception as exc:
        raise RuntimeError(f"Methods browser preflight app construction failed: {exc}") from exc

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError("Playwright is required for Methods visual certification") from exc
    for package in ("dash", "dash-mantine-components", "dash-ag-grid", "dash-iconify"):
        try:
            importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"Missing dashboard runtime dependency: {package}") from exc

    model = build_methods_model(get_v3_repository(), "vi")
    report_id = "dataset::HOME_CREDIT::mean_e2e"
    report = report_by_id(model, report_id)
    report_url = "/methods?" + urlencode({"tab": "traceability", "report": report_id, "table": "case_generation_metrics"})
    finding_url = "/methods?" + urlencode({"tab": "findings", "finding": "F_ROBUSTNESS_MARGIN"})
    metric_key = "end_to_end_faithfulness_yield::DATASET_SUMMARY::PRIMARY"
    if metric_key not in model.metric_keys:
        raise RuntimeError(f"Canonical Methods metric key missing: {metric_key}")
    metric_url = "/methods?" + urlencode({"tab": "metrics", "metric_key": metric_key})

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for old in SCREENSHOT_DIR.glob("methods_*.png"):
        old.unlink()
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    env = os.environ.copy()
    env.update({"DASH_HOST": "127.0.0.1", "DASH_PORT": str(port), "DASH_DEBUG": "0", "PYTHONUNBUFFERED": "1"})
    log_path = SCREENSHOT_DIR / "dashboard_server.log"
    log = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen([sys.executable, "-m", "research.python.dashboard.app_v3"], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, text=True)
    try:
        _wait_server(base, process, log_path)
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
                page = context.new_page()
                console_errors: list[str] = []
                page_errors: list[str] = []
                request_failures: list[dict] = []
                page.on("console", lambda msg: console_errors.append(msg.text) if (msg.type == "error" or "warning #29" in msg.text.lower()) else None)
                page.on("pageerror", lambda exc: page_errors.append(str(exc)))
                page.on("requestfailed", lambda req: request_failures.append({"url": req.url, "failure": req.failure}))

                page.goto(base + report_url, wait_until="networkidle")
                detail = page.locator('[data-testid="methods-provenance-detail"]')
                detail.wait_for(state="visible", timeout=15000)
                page.wait_for_function(
                    """([selector, reportId]) => {
                        const node = document.querySelector(selector);
                        return node && node.getAttribute('data-report-number-id') === reportId;
                    }""",
                    arg=['[data-testid="methods-provenance-detail"]', report_id],
                    timeout=15000,
                )
                text = detail.inner_text()
                for token in (report_id, str(report["source_artifact_id"]), str(report["source_field"]), str(report["source_sha256"])):
                    if token not in text:
                        raise RuntimeError(f"Methods provenance detail missing exact source token: {token}")
                page.locator("#methods-schema-grid").wait_for(state="visible", timeout=5000)
                if page.locator("#methods-schema-grid .ag-row").count() == 0:
                    raise RuntimeError("Methods schema explorer has no rows")
                _assert_no_errors(page, console_errors, page_errors, request_failures, label=f"Methods traceability {width}x{height}")
                page.screenshot(path=str(SCREENSHOT_DIR / f"methods_traceability_{width}x{height}.png"), full_page=True)
                context.close()

            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            console_errors: list[str] = []
            page_errors: list[str] = []
            request_failures: list[dict] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if (msg.type == "error" or "warning #29" in msg.text.lower()) else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.on("requestfailed", lambda req: request_failures.append({"url": req.url, "failure": req.failure}))
            page.goto(base + metric_url, wait_until="networkidle")
            metric = page.locator('[data-testid="methods-metric-detail"]')
            metric.wait_for(state="visible", timeout=15000)
            page.wait_for_function(
                """([selector, metricKey]) => {
                    const node = document.querySelector(selector);
                    return node && node.getAttribute('data-metric-key') === metricKey;
                }""",
                arg=['[data-testid="methods-metric-detail"]', metric_key],
                timeout=15000,
            )
            if CAPABILITY_GAP not in metric.inner_text():
                raise RuntimeError("Methods metric capability boundary mismatch")
            _assert_no_errors(page, console_errors, page_errors, request_failures, label="Methods metric deep-link")
            context.close()

            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            console_errors = []
            page_errors = []
            request_failures = []
            page.on("console", lambda msg: console_errors.append(msg.text) if (msg.type == "error" or "warning #29" in msg.text.lower()) else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.on("requestfailed", lambda req: request_failures.append({"url": req.url, "failure": req.failure}))
            page.goto(base + finding_url, wait_until="networkidle")
            finding = page.locator('[data-testid="methods-finding-detail"]')
            finding.wait_for(state="visible", timeout=15000)
            page.wait_for_function(
                """([selector, findingId]) => {
                    const node = document.querySelector(selector);
                    return node && node.getAttribute('data-finding-id') === findingId;
                }""",
                arg=['[data-testid="methods-finding-detail"]', "F_ROBUSTNESS_MARGIN"],
                timeout=15000,
            )
            finding_text = finding.inner_text()
            if "robustness::margin::status" not in finding_text or "M27_MARGIN_SENSITIVITY" not in finding_text:
                raise RuntimeError("Methods finding evidence chain is incomplete")
            _assert_no_errors(page, console_errors, page_errors, request_failures, label="Methods finding deep-link")
            context.close()
            browser.close()
    except Exception as exc:
        raise RuntimeError(f"Methods browser certification failed: {exc}\n--- server log tail ---\n{_log_tail(log_path)}") from exc
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        log.close()
    print(f"DASHBOARD_METHODS_0056_BROWSER=PASS viewports=3 screenshots={SCREENSHOT_DIR}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    data_gate()
    source_gate()
    if args.browser:
        browser_gate()
    print("DASHBOARD_METHODS_0056=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

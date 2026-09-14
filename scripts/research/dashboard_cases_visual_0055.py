#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.metadata
import os
import re
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

from research.python.dashboard.v3.cases_model import (
    STRATUM_ORDER,
    build_cases_model,
    generation_from_landscape_click,
)
from research.python.dashboard.v3.figures import (
    cases_claim_type_status_matrix,
    cases_performance_landscape,
    cases_section_profile,
    cases_validation_composition,
)
from research.python.dashboard.v3.repository import get_v3_repository

ROOT = PROJECT_ROOT
SCREENSHOT_DIR = ROOT / ".researchops/visual_cases_certification"


def data_gate() -> None:
    repo = get_v3_repository()
    total_cases = 0
    total_claims = 0
    for scope in ("HOME_CREDIT", "FREDDIE"):
        model = build_cases_model(repo, scope, "vi")
        if len(model.case_ids) != 36:
            raise RuntimeError(f"Case universe drift {scope}: {len(model.case_ids)}")
        if tuple(model.strata) != STRATUM_ORDER:
            raise RuntimeError(f"Case stratum registry drift {scope}: {model.strata}")
        counts = {s: 0 for s in model.strata}
        for row in model.case_records:
            counts[str(row["selection_stratum"])] += 1
        if set(counts.values()) != {6}:
            raise RuntimeError(f"Expected six cases per stratum {scope}: {counts}")
        if len(model.generation_rows) != 18:
            raise RuntimeError(f"Expected 18 generations per case {scope}")
        if {str(r["model_id"]) for r in model.generation_rows} != {"qwen3_8b", "deepseek_v4_flash", "phi4_mini_instruct"}:
            raise RuntimeError(f"Model topology drift {scope}")
        if {str(r["evidence_level"]) for r in model.generation_rows} != {f"S{i}" for i in range(6)}:
            raise RuntimeError(f"Evidence topology drift {scope}")
        if len(model.claims) != int(model.generation["claim_count"]):
            raise RuntimeError(f"Selected generation claim denominator mismatch {scope}")
        if sum(int(r["claim_count"]) for r in model.status_counts) != len(model.claims):
            raise RuntimeError(f"Validation composition denominator mismatch {scope}")
        expected_gap = "NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE"
        if {model.capabilities[k] for k in ("raw_generation_text", "raw_claim_text", "evidence_source_text")} != {expected_gap}:
            raise RuntimeError(f"Raw-text capability boundary drift {scope}")
        figures = (
            cases_performance_landscape(model.generation_rows, selected_generation_id=model.selected_generation_id),
            cases_validation_composition(model.status_counts),
            cases_claim_type_status_matrix(model.claim_type_status),
            cases_section_profile(model.section_profile),
        )
        if len(figures[0].data) != 2 or figures[0].data[0].type != "heatmap" or figures[0].data[1].type != "scatter":
            raise RuntimeError(f"Case landscape must expose heatmap + SVG click layer {scope}")
        if len(figures[0].data[0].z) != 3 or any(len(row) != 6 for row in figures[0].data[0].z):
            raise RuntimeError(f"Case landscape must remain exact 3×6 {scope}")
        click_ids = {str(custom[4]) for custom in figures[0].data[1].customdata}
        unusable_ids = {str(row["generation_id"]) for row in model.generation_rows if bool(row["is_unusable"])}
        if not click_ids or not click_ids.isdisjoint(unusable_ids):
            raise RuntimeError(f"Case click layer must contain usable generations only {scope}")
        if any(len(fig.data) == 0 for fig in figures):
            raise RuntimeError(f"Case diagnostic figure unexpectedly empty {scope}")
        total_cases += len(model.case_ids)
        total_claims += len(repo.study_table("case_claim_diagnostics", scope))

    if total_cases != 72 or total_claims != 26976:
        raise RuntimeError(f"Case mart topology drift cases={total_cases} claims={total_claims}")

    frame = repo.study_table("case_generation_metrics", "HOME_CREDIT")
    unusable = frame.loc[frame["is_unusable"].astype(bool)]
    if unusable.empty:
        raise RuntimeError("Expected certified unusable Home Credit generations")
    row = unusable.iloc[0]
    model = build_cases_model(repo, "HOME_CREDIT", "vi", case_id=str(row["case_id"]), model_id=str(row["model_id"]), evidence_level=str(row["evidence_level"]))
    fig = cases_performance_landscape(model.generation_rows, selected_generation_id=model.selected_generation_id)
    mi = {"qwen3_8b": 0, "deepseek_v4_flash": 1, "phi4_mini_instruct": 2}[str(row["model_id"])]
    ei = int(str(row["evidence_level"])[1:])
    if fig.data[0].z[mi][ei] is not None or fig.data[0].text[mi][ei] != "N/A":
        raise RuntimeError("Unusable case generation was visualized as a zero-value observation")

    freddie = repo.study_table("case_generation_metrics", "FREDDIE")
    deep = freddie.loc[
        freddie["selection_stratum"].astype(str).eq("false_negative")
        & freddie["model_id"].astype(str).eq("qwen3_8b")
        & freddie["evidence_level"].astype(str).eq("S4")
    ].iloc[0]
    linked = build_cases_model(repo, "FREDDIE", "vi", search="?" + urlencode({"dataset": "FREDDIE", "case": str(deep["case_id"]), "model": "qwen3_8b", "evidence": "S4", "tab": "claims"}))
    if linked.selected_generation_id != str(deep["generation_id"]) or linked.selected_stratum != "false_negative" or linked.initial_tab != "claims":
        raise RuntimeError("Case Explorer direct deep-link identity contract failed")

    custom = list(fig.data[1].customdata[0])
    identity = generation_from_landscape_click({"points": [{"customdata": custom}]})
    if not identity or identity["generation_id"] != custom[4] or identity["usable"] != "USABLE":
        raise RuntimeError("Case landscape click-layer customdata identity contract failed")

    print("DASHBOARD_CASES_0055_DATA=PASS cases=72 generations=1296 claims=26976 landscape=3x6 capability_boundary=explicit")


def source_gate() -> None:
    paths = [
        ROOT / "research/python/dashboard/v3/cases_model.py",
        ROOT / "research/python/dashboard/v3/pages/cases.py",
        ROOT / "research/python/dashboard/v3/callbacks.py",
        ROOT / "research/python/dashboard/v3/figures.py",
    ]
    sources = {p.name: p.read_text(encoding="utf-8") for p in paths}
    page = sources["cases.py"]
    model = sources["cases_model.py"]
    callbacks = sources["callbacks.py"]
    joined = "\n".join(sources.values())
    for token in (
        "Case Performance Landscape",
        "Generation diagnostics",
        "Claim trace",
        "Certified diagnostic source span",
        "NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE",
    ):
        if token not in joined:
            raise RuntimeError(f"Missing Case Explorer redesign token: {token}")
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
            raise RuntimeError(f"Scientific/legacy token leaked into Case Explorer: {forbidden}")
    if "dmc.Tabs" in page or 'columnSize="sizeToFit"' in page or ('dmc.Button' in page and 'href=' in page):
        raise RuntimeError("Case Explorer reintroduced a known runtime-danger component pattern")
    if "cases-claim-detail-title-content" not in page or "cases-claim-detail-body-content" not in page:
        raise RuntimeError("Case claim Drawer IDs are not portal-safe")
    if 'data-testid": "cases-selected-generation"' not in page or 'data-testid": "cases-claim-drawer-content"' not in page:
        raise RuntimeError("Case Explorer lacks test-owned semantic identity selectors")
    if 'Input(LOCATION, "search")' not in callbacks or 'Input(LOCATION, "pathname")' not in callbacks:
        raise RuntimeError("Case URL state is not first-class")
    cases_callbacks = callbacks.split("def register_cases_callbacks(app):", 1)[1].split("def register_methods_callbacks(app):", 1)[0]
    if "def cases_capture_intent" in cases_callbacks or "STATE_INTENT_STORE_ID" in cases_callbacks:
        raise RuntimeError("Case Explorer reintroduced an unsupported cross-callback state cycle")
    if "def cases_landscape_selection" not in cases_callbacks or "HYDRATED_STORE_ID" not in cases_callbacks:
        raise RuntimeError("Case canonical hydration/Plotly selection callbacks are missing")
    if 'Output(LANDSCAPE_SELECTION_STORE_ID, "data")' not in cases_callbacks or 'Input(LANDSCAPE_SELECTION_STORE_ID, "data"' not in cases_callbacks:
        raise RuntimeError("Case Plotly event Store is not wired into the canonical resolver")

    resolver_decorator = cases_callbacks.split("def cases_resolve_state", 1)[0].rsplit("@app.callback", 1)[1]
    if 'State(HYDRATED_STORE_ID, "data"' not in resolver_decorator or 'State(SELECTED_GENERATION_STORE_ID, "data"' not in resolver_decorator:
        raise RuntimeError("Case canonical resolver lacks hydration/canonical state guards")
    for token in ("DATASET_ID", "STRATUM_ID", "CASE_ID", "MODEL_ID", "EVIDENCE_ID", "TABS_ID"):
        if f'Input({token}, "value"' not in resolver_decorator or f'Output({token}, "value")' not in resolver_decorator:
            raise RuntimeError(f"Case canonical resolver does not own/read control: {token}")
        if cases_callbacks.count(f'Output({token}, "value")') != 1:
            raise RuntimeError(f"Case control has multiple callback owners: {token}")
    for transition in ("initial_cases_intent", "url_cases_intent", "control_cases_intent", "landscape_cases_intent", "len(control_triggers) != 1"):
        if transition not in cases_callbacks:
            raise RuntimeError(f"Case deterministic transition guard missing: {transition}")
    if "allow_duplicate=True" in cases_callbacks:
        raise RuntimeError("Case Explorer reintroduced duplicate callback outputs")
    click_block = cases_callbacks.split("def cases_landscape_selection", 1)[1].split("@app.callback", 1)[0]
    if "allow_duplicate=True" in click_block:
        raise RuntimeError("Case Plotly selection uses duplicate output")
    if '"event_seq": prior_seq + 1' not in click_block:
        raise RuntimeError("Case Plotly event Store lacks unique event identity")
    if 'name="Certified usable generation"' not in sources["figures.py"]:
        raise RuntimeError("Case certified SVG click layer missing")
    if "resolve" not in model.lower() or "selected_identity" not in model:
        raise RuntimeError("Case canonical state/identity contract missing")
    print("DASHBOARD_CASES_0055_SOURCE=PASS state=canonical shell=stable claim_identity=exact science=read-only")


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


def _select_option(page, selector: str, label: str) -> None:
    page.locator(selector).click()
    try:
        page.get_by_role("option", name=label, exact=True).click(timeout=2500)
        return
    except Exception:
        matches = page.get_by_text(label, exact=True)
        if matches.count():
            matches.nth(matches.count() - 1).click(timeout=2500)
            return
    raise RuntimeError(f"Unable to select {label!r} from {selector}")


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
        raise RuntimeError(f"Case browser preflight app construction failed: {exc}") from exc

    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError("Playwright is required for Case Explorer visual certification") from exc
    for package in ("dash", "dash-mantine-components", "dash-ag-grid", "dash-iconify"):
        try:
            importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(f"Missing dashboard runtime dependency: {package}") from exc

    repo = get_v3_repository()
    freddie = repo.study_table("case_generation_metrics", "FREDDIE")
    deep = freddie.loc[
        freddie["selection_stratum"].astype(str).eq("false_negative")
        & freddie["model_id"].astype(str).eq("qwen3_8b")
        & freddie["evidence_level"].astype(str).eq("S4")
    ].iloc[0]
    deep_url = "/cases?" + urlencode({"dataset": "FREDDIE", "case": str(deep["case_id"]), "model": "qwen3_8b", "evidence": "S4", "tab": "landscape"})

    SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
    for old in SCREENSHOT_DIR.glob("cases_*.png"):
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

                page.goto(base + deep_url, wait_until="networkidle")
                page.locator("#cases-performance-landscape").wait_for(state="visible", timeout=15000)
                selected = page.locator('[data-testid="cases-selected-generation"]')
                selected.wait_for(state="visible", timeout=10000)
                page.wait_for_function(
                    """([selector, dataset, caseId, modelId, evidence, generationId]) => {
                        const node = document.querySelector(selector);
                        return node
                            && node.getAttribute('data-dataset-id') === dataset
                            && node.getAttribute('data-case-id') === caseId
                            && node.getAttribute('data-model-id') === modelId
                            && node.getAttribute('data-evidence-level') === evidence
                            && node.getAttribute('data-generation-id') === generationId;
                    }""",
                    arg=['[data-testid="cases-selected-generation"]', "FREDDIE", str(deep["case_id"]), "qwen3_8b", "S4", str(deep["generation_id"])],
                    timeout=15000,
                )
                if page.locator("#cases-header-dataset-value").inner_text() != "Freddie Mac":
                    raise RuntimeError("Case deep-link left stale dataset header")
                print("CASE_BROWSER_DEEP_LINK_IDENTITY=PASS")

                # The Case page owns a local dataset independently of the shell
                # comparison scope; prove the export follows that exact local
                # certified identity rather than SCOPE_STORE.
                if width == 1366:
                    with page.expect_download(timeout=15000) as download_info:
                        page.locator("#v3-export-current").click()
                    suggested = download_info.value.suggested_filename
                    if suggested != "llm_xai_cases_freddie.zip":
                        raise RuntimeError(f"Case export scope mismatch: {suggested}")
                    print("CASE_BROWSER_LOCAL_EXPORT_SCOPE=PASS")

                before_generation = selected.get_attribute("data-generation-id")
                # Rebuild the exact certified figure for the deep-linked case and choose the
                # first alternate point from its *usable-only* click layer.  This means the
                # browser target is derived from the same presentation contract as runtime,
                # not from an independent hard-coded model/evidence guess.
                current_model_view = build_cases_model(
                    repo,
                    "FREDDIE",
                    "vi",
                    case_id=str(deep["case_id"]),
                    model_id="qwen3_8b",
                    evidence_level="S4",
                )
                current_figure = cases_performance_landscape(
                    current_model_view.generation_rows,
                    selected_generation_id=current_model_view.selected_generation_id,
                )
                if len(current_figure.data) < 2 or str(current_figure.data[1].type) != "scatter":
                    raise RuntimeError("Case landscape is missing the certified SVG click layer")
                click_custom = [list(custom) for custom in current_figure.data[1].customdata]
                try:
                    target_point_index, target_custom = next(
                        (i, custom) for i, custom in enumerate(click_custom)
                        if str(custom[4]) != str(before_generation)
                    )
                except StopIteration as exc:
                    raise RuntimeError("Case browser certification could not find a usable alternate generation") from exc
                target_generation = str(target_custom[4])
                target_model = str(target_custom[2])
                target_evidence = str(target_custom[3])
                print(f"CASE_BROWSER_CLICK_TARGET model={target_model} evidence={target_evidence} generation={target_generation}")

                points = page.locator("#cases-performance-landscape .scatterlayer path.point")
                page.wait_for_function(
                    """([selector, expected]) => document.querySelectorAll(selector).length === expected""",
                    arg=["#cases-performance-landscape .scatterlayer path.point", len(click_custom)],
                    timeout=6000,
                )
                if points.count() != len(click_custom):
                    raise RuntimeError(f"Case click-layer DOM count mismatch: {points.count()} != {len(click_custom)}")
                point = points.nth(target_point_index)

                # Instrument Plotly itself before the click.  This separates a front-end
                # event failure from a Dash callback/state failure in one browser run.
                page.evaluate(
                    """() => {
                        const gd = document.querySelector('#cases-performance-landscape .js-plotly-plot');
                        if (!gd || typeof gd.on !== 'function') throw new Error('Plotly graph div unavailable');
                        window.__casesLastPlotlyClickGeneration = null;
                        gd.on('plotly_click', event => {
                            const point = event && event.points && event.points[0];
                            const custom = point && point.customdata;
                            window.__casesLastPlotlyClickGeneration = custom && custom[4] ? String(custom[4]) : null;
                        });
                    }"""
                )
                point.hover(force=True)
                page.wait_for_timeout(120)
                hover_text = page.locator("#cases-performance-landscape .hoverlayer").text_content(timeout=3000) or ""
                if target_generation not in hover_text:
                    raise RuntimeError(
                        "Case SVG click target hover identity mismatch: "
                        f"target={target_generation} hover={hover_text!r}"
                    )
                point.click(force=True)

                # Gate 1: browser click must become the exact Plotly event.
                page.wait_for_function(
                    """generationId => window.__casesLastPlotlyClickGeneration === generationId""",
                    arg=target_generation,
                    timeout=4000,
                )
                print("CASE_BROWSER_PLOTLY_CLICK=PASS")
                # Gate 2: Dash callback cascade must materialize the exact certified identity.
                try:
                    page.wait_for_function(
                        """([selector, generationId]) => {
                            const node = document.querySelector(selector);
                            return node && node.getAttribute('data-generation-id') === generationId;
                        }""",
                        arg=['[data-testid="cases-selected-generation"]', target_generation],
                        timeout=10000,
                    )
                except Exception as exc:
                    current = selected.get_attribute("data-generation-id")
                    plotly_event = page.evaluate("() => window.__casesLastPlotlyClickGeneration")
                    raise RuntimeError(
                        f"Case Dash state failed after confirmed Plotly click: "
                        f"before={before_generation} target={target_generation} plotly_event={plotly_event} current={current}"
                    ) from exc
                print("CASE_BROWSER_DASH_STATE_TRANSITION=PASS")
                if selected.get_attribute("data-model-id") != target_model or selected.get_attribute("data-evidence-level") != target_evidence:
                    raise RuntimeError(
                        "Case selected generation identity changed without exact model/evidence synchronization: "
                        f"target_model={target_model} target_evidence={target_evidence}"
                    )
                page.wait_for_timeout(500)
                if selected.get_attribute("data-generation-id") != target_generation:
                    raise RuntimeError("Case selected generation reverted after callback cascade")

                page.get_by_text("Generation diagnostics", exact=True).click()
                page.locator("#cases-validation-composition").wait_for(state="visible", timeout=6000)
                page.locator("#cases-claim-type-status").wait_for(state="visible", timeout=6000)
                page.get_by_text("Claim trace", exact=True).click()
                grid = page.locator("#cases-claim-grid")
                grid.wait_for(state="visible", timeout=6000)
                rows = page.locator("#cases-claim-grid .ag-center-cols-container .ag-row")
                if rows.count() == 0:
                    raise RuntimeError("Case claim grid has no rows for selected generation")
                first = rows.first
                claim_id = first.get_attribute("row-id")
                first.locator(".ag-cell").first.click(force=True)
                drawer = page.locator('[data-testid="cases-claim-drawer-content"]')
                drawer.wait_for(state="visible", timeout=6000)
                drawer_text = drawer.inner_text()
                if "certified diagnostic source span" not in drawer_text.casefold():
                    raise RuntimeError("Case claim drawer does not expose certified diagnostic source span")
                if claim_id and claim_id not in drawer_text:
                    raise RuntimeError(f"Case claim drawer identity mismatch: expected {claim_id}")
                if _duplicates(page):
                    raise RuntimeError(f"Case Drawer introduced duplicate DOM IDs: {_duplicates(page)}")
                page.keyboard.press("Escape")
                drawer.wait_for(state="hidden", timeout=4000)

                _assert_no_errors(page, console_errors, page_errors, request_failures, label=f"Cases {width}x{height}")
                page.screenshot(path=str(SCREENSHOT_DIR / f"cases_freddie_{width}x{height}.png"), full_page=True)
                context.close()

            # Dependency reconciliation: local dataset is authoritative and old case/generation cannot leak.
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            page = context.new_page()
            console_errors: list[str] = []
            page_errors: list[str] = []
            request_failures: list[dict] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if (msg.type == "error" or "warning #29" in msg.text.lower()) else None)
            page.on("pageerror", lambda exc: page_errors.append(str(exc)))
            page.on("requestfailed", lambda req: request_failures.append({"url": req.url, "failure": req.failure}))
            page.goto(base + deep_url, wait_until="networkidle")
            current = page.locator('[data-testid="cases-selected-generation"]')
            current.wait_for(state="visible", timeout=15000)
            page.wait_for_function(
                """([selector, generationId]) => {
                    const node = document.querySelector(selector);
                    return node && node.getAttribute('data-generation-id') === generationId;
                }""",
                arg=['[data-testid="cases-selected-generation"]', str(deep["generation_id"])],
                timeout=15000,
            )
            _select_option(page, "#v3-cases-dataset", "Home Credit")
            page.wait_for_function(
                """selector => {
                    const node = document.querySelector(selector);
                    return node && node.getAttribute('data-dataset-id') === 'HOME_CREDIT';
                }""",
                arg='[data-testid="cases-selected-generation"]',
                timeout=10000,
            )
            if page.locator("#cases-header-dataset-value").inner_text() != "Home Credit":
                raise RuntimeError("Case local dataset reconciliation left stale header")
            _assert_no_errors(page, console_errors, page_errors, request_failures, label="Cases dependency reconciliation")
            context.close()
            browser.close()
    except Exception as exc:
        raise RuntimeError(f"Case browser certification failed: {exc}\n--- server log tail ---\n{_log_tail(log_path)}") from exc
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait(timeout=5)
        log.close()
    print(f"DASHBOARD_CASES_0055_BROWSER=PASS viewports=3 screenshots={SCREENSHOT_DIR}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", action="store_true")
    args = parser.parse_args()
    data_gate()
    source_gate()
    if args.browser:
        browser_gate()
    print("DASHBOARD_CASES_0055=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

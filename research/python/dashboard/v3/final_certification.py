from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from research.python.common.paths import DEFAULT_PATHS

from .cases_model import build_cases_model
from .decision_model import build_decision_model
from .effectiveness_model import build_effectiveness_model
from .i18n import _TEXT
from .mechanisms_model import build_mechanisms_model
from .methods_model import build_methods_model
from .overview_model import build_overview_model
from .release_guard import get_v3_release_guard
from .repository import get_v3_repository
from .robustness_model import build_robustness_model
from .settings import PAGE_PATHS, VISUALIZATION_MANIFEST_PATH


FINAL_RELEASE_ID = "llm-xai-multidataset-dashboard-v3"
FINAL_RELEASE_DIR = DEFAULT_PATHS.project_root / "release/multidataset_dashboard_v3"
CERTIFIED_VIEWPORT = {"width": 1366, "height": 768}
PAGE_CONTENT_IDS = {
    "/": "v3-overview-content",
    "/effectiveness": "v3-effectiveness-content",
    "/mechanisms": "v3-mechanisms-content",
    "/decision": "v3-decision-content",
    "/robustness": "v3-robustness-content",
    "/cases": "v3-cases-content",
    "/methods": "v3-methods-content",
}
FORBIDDEN_IMPORT_PREFIXES = (
    "research.python.statistical_analysis",
    "research.python.claim_validation",
    "research.python.decision_support",
)


def _sha256(path: Path) -> str:
    digest=hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024*1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8")


def _source_files(root: Path) -> list[Path]:
    paths=[root/"research/python/dashboard/app_v3.py",root/"research/python/dashboard/components/empty_state.py"]
    for folder in (root/"research/python/dashboard/v3",root/"research/python/dashboard/i18n",root/"research/python/dashboard/assets"):
        if folder.is_dir():
            paths.extend(p for p in folder.rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix not in {".pyc"})
    return sorted(set(paths),key=lambda p:p.relative_to(root).as_posix())


def source_identity(root: Path) -> dict[str, Any]:
    records=[]
    canonical=[]
    for path in _source_files(root):
        rel=path.relative_to(root).as_posix(); sha=_sha256(path); size=path.stat().st_size
        records.append({"path":rel,"sha256":sha,"byte_count":size})
        canonical.append(f"{rel}\t{sha}\t{size}\n")
    tree_sha=hashlib.sha256("".join(canonical).encode("utf-8")).hexdigest()
    return {"source_tree_sha256":tree_sha,"file_count":len(records),"files":records}


def source_isolation_audit(root: Path) -> dict[str, Any]:
    violations=[]
    for path in [root/"research/python/dashboard/app_v3.py", *sorted((root/"research/python/dashboard/v3").rglob("*.py"))]:
        source=path.read_text(encoding="utf-8")
        legacy_release_token="visualization"+"_"+"v2"
        legacy_repo_token="get_dashboard"+"_repository"
        if legacy_release_token in source or legacy_repo_token in source:
            violations.append({"path":path.relative_to(root).as_posix(),"reason":"legacy_fallback_reference"})
        try: tree=ast.parse(source)
        except SyntaxError as exc:
            violations.append({"path":path.relative_to(root).as_posix(),"reason":f"syntax:{exc}"}); continue
        modules=[]
        for node in ast.walk(tree):
            if isinstance(node,ast.Import): modules.extend(alias.name for alias in node.names)
            elif isinstance(node,ast.ImportFrom) and node.module: modules.append(node.module)
        for module in modules:
            if any(module.startswith(prefix) for prefix in FORBIDDEN_IMPORT_PREFIXES):
                violations.append({"path":path.relative_to(root).as_posix(),"reason":f"forbidden_import:{module}"})
    return {"passed":not violations,"violations":violations}


def traceability_audit() -> dict[str, Any]:
    guard=get_v3_release_guard()
    if not guard.ready or guard.release is None:
        return {"passed":False,"errors":guard.errors}
    repo=get_v3_repository(); errors=[]
    backed_overview_values=0
    for scope in ("HOME_CREDIT","FREDDIE","CROSS_DATASET"):
        overview=build_overview_model(repo,scope,"vi")
        for card in overview.cards:
            for value in card.values:
                if not value.report_number_id:
                    errors.append(f"overview_card_missing_report_number:{scope}:{card.key}")
                else:
                    backed_overview_values+=1
    options=repo.table("option_performance")
    if options["mean_e2e_report_number_id"].isna().any(): errors.append("option_mean_e2e_missing_report_number")
    losses=repo.table("failure_decomposition")
    for col in ("pipeline_loss_report_number_id","not_verifiable_loss_report_number_id","unsupported_loss_report_number_id","contradiction_loss_report_number_id"):
        if losses[col].isna().any(): errors.append(f"failure_decomposition_missing:{col}")
    findings=repo.table("findings")
    if findings["supporting_report_numbers"].isna().any(): errors.append("finding_missing_supporting_report_number")
    metadata=json.loads((guard.release.files[0].path.parent/"release_metadata.json").read_text(encoding="utf-8"))
    if metadata.get("scientific_recomputation_allowed") is not False: errors.append("scientific_recomputation_not_forbidden")
    return {"passed":not errors,"errors":errors,"release_id":repo.release.release_id,"table_count":repo.release.table_count,"report_number_backed_overview_cards":backed_overview_values}


def i18n_audit() -> dict[str, Any]:
    # Product contract is Vietnamese-only. English scientific terminology remains
    # in labels where translation would weaken meaning, but there is no EN UI.
    errors=[]
    repo=get_v3_repository()
    locale="vi"
    for scope in ("HOME_CREDIT","FREDDIE","CROSS_DATASET"):
        build_overview_model(repo,scope,locale); build_effectiveness_model(repo,scope,locale); build_mechanisms_model(repo,scope,locale); build_decision_model(repo,scope,locale); build_robustness_model(repo,scope,locale)
    for scope in ("HOME_CREDIT","FREDDIE"): build_cases_model(repo,scope,locale)
    build_methods_model(repo,locale)
    return {"passed":not errors,"errors":errors,"locales":["vi"],"catalog_key_count":len(_TEXT["vi"])}


def static_precheck(root: Path) -> dict[str, Any]:
    guard=get_v3_release_guard()
    data_guard={"passed":bool(guard.ready and guard.release is not None),"errors":guard.errors,"release_id":guard.release.release_id if guard.release else None}
    isolation=source_isolation_audit(root); i18n=i18n_audit(); trace=traceability_audit(); identity=source_identity(root)
    passed=all(x["passed"] for x in (data_guard,isolation,i18n,trace))
    return {"passed":passed,"data_guard":data_guard,"source_isolation":isolation,"i18n":i18n,"traceability":trace,"source_identity":identity}


def _free_port() -> int:
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1",0)); return int(sock.getsockname()[1])


def _wait_server(url: str, process: subprocess.Popen[str]) -> None:
    deadline=time.time()+45
    last=None
    while time.time()<deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Dashboard server exited early with code {process.returncode}")
        try:
            with urlopen(url,timeout=1) as response:
                if response.status<500: return
        except Exception as exc: last=exc
        time.sleep(0.25)
    raise RuntimeError(f"Dashboard server did not become ready: {last}")


def _browser_executable() -> str | None:
    candidates=[
        shutil.which("chromium"),shutil.which("chromium-browser"),shutil.which("google-chrome"),shutil.which("google-chrome-stable"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ]
    return next((str(x) for x in candidates if x and Path(x).exists()),None)


def _select_option(page, selector: str, label: str) -> None:
    page.locator(selector).click()
    try:
        page.get_by_role("option",name=label,exact=True).click(timeout=2500); return
    except Exception:
        pass
    matches=page.get_by_text(label,exact=True)
    count=matches.count()
    if count:
        matches.nth(count-1).click(timeout=2500); return
    raise RuntimeError(f"Unable to select {label!r} from {selector}")


def _assert_page_ready(page, route: str) -> str:
    selector=f"#{PAGE_CONTENT_IDS[route]} .research-page"
    page.locator(selector).wait_for(state="visible",timeout=15000)
    text=page.locator(f"#{PAGE_CONTENT_IDS[route]}").inner_text()
    if not text.strip(): raise RuntimeError(f"Empty page content at {route}")
    return text


def _layout_check(page) -> dict[str, Any]:
    result=page.evaluate("""() => ({scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth, bodyScrollWidth: document.body.scrollWidth})""")
    result["passed"]=int(result["scrollWidth"])<=int(result["clientWidth"])+2 and int(result["bodyScrollWidth"])<=int(result["clientWidth"])+2
    return result


def browser_certification(root: Path, staging: Path) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError("Playwright is required for final dashboard certification") from exc
    for package in ("dash","dash-mantine-components","dash-iconify"):
        try: importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc: raise RuntimeError(f"Missing dashboard runtime dependency: {package}") from exc

    port=_free_port(); base=f"http://127.0.0.1:{port}"
    env=os.environ.copy(); env.update({"DASH_HOST":"127.0.0.1","DASH_PORT":str(port),"DASH_DEBUG":"0","PYTHONUNBUFFERED":"1"})
    log_path=staging/"dashboard_server.log"; log_path.parent.mkdir(parents=True,exist_ok=True)
    log_handle=log_path.open("w",encoding="utf-8")
    process=subprocess.Popen([sys.executable,"-m","research.python.dashboard.app_v3"],cwd=root,env=env,stdout=log_handle,stderr=subprocess.STDOUT,text=True)
    page_results=[]; console_errors=[]; page_errors=[]; network_errors=[]; layout_results=[]; export_result={"passed":False}; scope_checks=[]; locale_checks=[]
    try:
        _wait_server(base,process)
        with sync_playwright() as p:
            browser_type=p.chromium
            try:
                browser=browser_type.launch(headless=True)
            except Exception:
                executable=_browser_executable()
                if not executable: raise RuntimeError("Chromium/Chrome executable is unavailable for final certification")
                browser=browser_type.launch(headless=True,executable_path=executable)
            context=browser.new_context(viewport=CERTIFIED_VIEWPORT,accept_downloads=True)
            page=context.new_page()
            page.on("console",lambda msg: console_errors.append(msg.text) if msg.type=="error" else None)
            page.on("pageerror",lambda exc: page_errors.append(str(exc)))
            page.on(
                "response",
                lambda response: network_errors.append(
                    {"status": response.status, "url": response.url}
                )
                if (
                    response.status >= 400
                    and response.url.startswith(base)
                    and not response.url.endswith("/favicon.ico")
                )
                else None,
            )

            # Overview: Vietnamese-only product contract and all global scopes.
            page.goto(base+"/",wait_until="networkidle")
            text=_assert_page_ready(page,"/")
            locale_checks.append({"locale":"vi","passed":"Tổng quan nghiên cứu" in text and page.locator("#v3-locale-select").count()==0})
            for label,expected in (("Home Credit","Home Credit"),("Freddie Mac","Freddie Mac"),("Cross-dataset","MODEL_REVISION_UNKNOWN")):
                page.locator("#v3-dataset-scope-select").get_by_text(label,exact=True).click(timeout=2500)
                page.wait_for_timeout(450); current=_assert_page_ready(page,"/")
                scope_checks.append({"scope_label":label,"passed":expected in current})
            current=_assert_page_ready(page,"/")
            if "NO_ROBUST_RECOMMENDATION" not in current or "MODEL_REVISION_UNKNOWN" not in current: raise RuntimeError("Overview does not preserve certified cross-dataset status codes")

            checks={
                "/effectiveness": ("Reliability Map", "Statistical evidence"),
                "/mechanisms": ("100% Faithfulness Accounting", "Claim diagnostics"),
                "/decision": ("NO_ROBUST_RECOMMENDATION","CONTROL","FALLBACK_ONLY"),
                "/robustness": ("PRIMARY_CERTIFIED","SENSITIVITY_ONLY","NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3"),
                "/cases": ("NOT_AVAILABLE_IN_M28_AUTHORIZED_LINEAGE",),
                "/methods": ("MODEL_REVISION_UNKNOWN","NO_ROBUST_RECOMMENDATION","certified_multidataset_analytical_release_v1"),
            }
            screenshots=staging/"screenshots"; screenshots.mkdir(parents=True,exist_ok=True)
            # Overview screenshot in the certified Cross-dataset / Vietnamese state.
            page.goto(base+"/",wait_until="networkidle"); _assert_page_ready(page,"/")
            page.screenshot(path=str(screenshots/"01_overview_cross.png"),full_page=True)
            layout_results.append({"route":"/",**_layout_check(page)})
            page_results.append({"route":"/","passed":True})
            order=2
            for route,needles in checks.items():
                page.goto(base+route,wait_until="networkidle"); text=_assert_page_ready(page,route)
                missing=[needle for needle in needles if needle not in text]
                if missing: raise RuntimeError(f"{route} missing certified markers: {missing}")
                layout={"route":route,**_layout_check(page)}; layout_results.append(layout)
                if not layout["passed"]: raise RuntimeError(f"Horizontal overflow at {route}: {layout}")
                page.screenshot(path=str(screenshots/f"{order:02d}_{route.strip('/').replace('/','_') or 'overview'}.png"),full_page=True)
                page_results.append({"route":route,"passed":True,"markers":list(needles)}); order+=1

            # Case Explorer: certify exact first-paint URL identity, then prove the
            # local dataset selector remains authoritative independently of global
            # comparison scope.  This catches the historical URL/global/control
            # race rather than merely checking that some Freddie text is present.
            repo=get_v3_repository()
            case_target=(
                repo.study_table("case_generation_metrics","FREDDIE")
                .loc[lambda x: x["selection_stratum"].astype(str).eq("false_negative") & x["model_id"].astype(str).eq("qwen3_8b") & x["evidence_level"].astype(str).eq("S4")]
                .iloc[0]
            )
            case_query=urlencode({"dataset":"FREDDIE","case":str(case_target["case_id"]),"model":"qwen3_8b","evidence":"S4","tab":"landscape"})
            page.goto(base+"/cases?"+case_query,wait_until="networkidle"); _assert_page_ready(page,"/cases")
            page.wait_for_function(
                """([selector, caseId, generationId]) => {
                    const node=document.querySelector(selector);
                    return node
                        && node.getAttribute('data-dataset-id') === 'FREDDIE'
                        && node.getAttribute('data-case-id') === caseId
                        && node.getAttribute('data-model-id') === 'qwen3_8b'
                        && node.getAttribute('data-evidence-level') === 'S4'
                        && node.getAttribute('data-generation-id') === generationId;
                }""",
                arg=['[data-testid="cases-selected-generation"]',str(case_target["case_id"]),str(case_target["generation_id"])],
                timeout=15000,
            )
            header_dataset=page.locator("#cases-header-dataset-value").inner_text()
            scope_checks.append({"scope_label":"Case Explorer exact Freddie deep-link","passed":header_dataset=="Freddie Mac"})
            _select_option(page,"#v3-cases-dataset","Home Credit")
            page.wait_for_function(
                """selector => {
                    const node=document.querySelector(selector);
                    return node && node.getAttribute('data-dataset-id') === 'HOME_CREDIT';
                }""",
                arg='[data-testid="cases-selected-generation"]',
                timeout=10000,
            )
            scope_checks.append({"scope_label":"Case Explorer local Home Credit reconciliation","passed":page.locator("#cases-header-dataset-value").inner_text()=="Home Credit"})

            # Methods: certify one exact provenance deep-link, then prove this
            # global audit surface exports CROSS_DATASET even when the shell is
            # deliberately changed to a single study.
            report_id="dataset::HOME_CREDIT::mean_e2e"
            methods_query=urlencode({"tab":"traceability","report":report_id,"table":"case_generation_metrics"})
            page.goto(base+"/methods?"+methods_query,wait_until="networkidle"); _assert_page_ready(page,"/methods")
            page.wait_for_function(
                """([selector, reportId]) => {
                    const node=document.querySelector(selector);
                    return node && node.getAttribute('data-report-number-id') === reportId;
                }""",
                arg=['[data-testid="methods-provenance-detail"]',report_id],
                timeout=15000,
            )
            page.locator("#v3-dataset-scope-select").get_by_text("Home Credit",exact=True).click(timeout=2500)
            page.wait_for_timeout(250)
            with page.expect_download(timeout=15000) as download_info:
                page.locator("#v3-export-current").click()
            download=download_info.value
            suggested=download.suggested_filename
            export_result={"passed":suggested=="llm_xai_methods_cross_dataset.zip","suggested_filename":suggested,"expected_scope":"CROSS_DATASET","report_number_id":report_id}

            context.close(); browser.close()
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=8)
            except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
        log_handle.close()

    passed=(all(x.get("passed") for x in page_results) and all(x.get("passed") for x in scope_checks) and all(x.get("passed") for x in locale_checks) and all(x.get("passed") for x in layout_results) and export_result.get("passed") and not console_errors and not page_errors and not network_errors)
    return {"passed":bool(passed),"base_url":base,"viewport":CERTIFIED_VIEWPORT,"pages":page_results,"scope_checks":scope_checks,"locale_checks":locale_checks,"layout":layout_results,"export":export_result,"console_errors":console_errors,"page_errors":page_errors,"network_errors":network_errors}


def _environment() -> dict[str, Any]:
    packages={}
    for name in ("dash","dash-mantine-components","dash-iconify","plotly","pandas","playwright"):
        try: packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError: packages[name]=None
    return {"python":platform.python_version(),"platform":platform.platform(),"machine":platform.machine(),"packages":packages,"browser_executable_fallback":_browser_executable()}


def _manifest_files(staging: Path) -> dict[str, Any]:
    result={}
    for path in sorted(p for p in staging.rglob("*") if p.is_file() and p.name!="dashboard_release_manifest.json"):
        rel=path.relative_to(staging).as_posix(); result[rel]={"sha256":_sha256(path),"byte_count":path.stat().st_size}
    return result


def certify(*,static_only: bool=False) -> int:
    root=DEFAULT_PATHS.project_root
    static=static_precheck(root)
    if not static["passed"]:
        print("MULTIDATASET_M30F_STATIC_PRECHECK=FAIL"); return 2
    print("MULTIDATASET_M30F_DATA_GUARD=PASS")
    print("MULTIDATASET_M30F_SOURCE_ISOLATION=PASS")
    print(f"MULTIDATASET_M30F_I18N=PASS locales={len(static['i18n']['locales'])}")
    print("MULTIDATASET_M30F_TRACEABILITY=PASS")
    if static_only:
        print("MULTIDATASET_M30F_STATIC_PRECHECK=PASS")
        return 0

    input_identity={"visualization_manifest_sha256":_sha256(VISUALIZATION_MANIFEST_PATH),"source_tree_sha256":static["source_identity"]["source_tree_sha256"]}
    existing=FINAL_RELEASE_DIR/"dashboard_release_manifest.json"
    if existing.is_file():
        old=json.loads(existing.read_text(encoding="utf-8"))
        if old.get("input_identity")!=input_identity:
            raise RuntimeError("Existing final dashboard certification has different input/source identity; refusing overwrite")

    staging=Path(tempfile.mkdtemp(prefix="m30f_dashboard_cert_",dir=str(root/".researchops" if (root/".researchops").is_dir() else root)))
    try:
        browser=browser_certification(root,staging)
        if not browser["passed"]: raise RuntimeError(f"Browser certification failed: {browser}")
        print(f"MULTIDATASET_M30F_BROWSER_E2E=PASS pages={len(browser['pages'])} scopes=3")
        print("MULTIDATASET_M30F_LAYOUT=PASS")
        print("MULTIDATASET_M30F_CONSOLE=PASS")
        print("MULTIDATASET_M30F_EXPORT=PASS")
        _write_json(staging/"browser_e2e_report.json",browser)
        _write_json(staging/"source_trace_audit.json",static["traceability"])
        _write_json(staging/"source_isolation_audit.json",static["source_isolation"])
        _write_json(staging/"i18n_audit.json",static["i18n"])
        _write_json(staging/"source_identity.json",static["source_identity"])
        _write_json(staging/"environment.json",_environment())
        page_matrix={"pages":list(PAGE_CONTENT_IDS),"study_scopes":["HOME_CREDIT","FREDDIE"],"comparison_scope":"CROSS_DATASET","case_explorer_scopes":["HOME_CREDIT","FREDDIE"],"locales":["vi"]}
        _write_json(staging/"page_matrix.json",page_matrix)
        validation={"schema_version":"multidataset_dashboard_v3_validation_v1","passed":True,"checks":{"data_guard":True,"source_isolation":True,"i18n":True,"browser_e2e":True,"layout":True,"console":True,"traceability":True,"exports":True}}
        _write_json(staging/"dashboard_release_validation.json",validation)
        manifest={"schema_version":"multidataset_dashboard_v3_manifest_v1","release_id":FINAL_RELEASE_ID,"status":"FINAL_CERTIFIED","input_identity":input_identity,"scientific_parent_release_id":get_v3_repository().release.parent_release_id,"visualization_parent_release_id":get_v3_repository().release.release_id,"replication_scope":get_v3_repository().release.replication_scope,"robust_recommendation_status":get_v3_repository().release.robust_recommendation_status,"files":{}}
        manifest["files"]=_manifest_files(staging)
        _write_json(staging/"dashboard_release_manifest.json",manifest)

        if existing.is_file():
            shutil.rmtree(staging,ignore_errors=True)
            print("MULTIDATASET_M30F_FINAL_CERTIFICATION=ALREADY_CERTIFIED")
            print("LLM_XAI_MULTIDATASET_RESEARCH_RELEASE=FINAL_CERTIFIED")
            return 0
        FINAL_RELEASE_DIR.parent.mkdir(parents=True,exist_ok=True)
        os.replace(staging,FINAL_RELEASE_DIR)
        print("MULTIDATASET_M30F_FINAL_CERTIFICATION=PASS")
        print("LLM_XAI_MULTIDATASET_RESEARCH_RELEASE=FINAL_CERTIFIED")
        return 0
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--static-only",action="store_true")
    args=parser.parse_args()
    return certify(static_only=args.static_only)


if __name__=="__main__":
    raise SystemExit(main())

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
if str(PROJECT_ROOT) not in sys.path: sys.path.insert(0, str(PROJECT_ROOT))

from research.python.dashboard.v3.figures import (
    robustness_contrast_stability_map,
    robustness_effect_dumbbell,
    robustness_margin_sensitivity_plot,
    robustness_rank_shift_heatmap,
)
from research.python.dashboard.v3.repository import get_v3_repository
from research.python.dashboard.v3.robustness_model import build_robustness_model

ROOT=PROJECT_ROOT
SCREENSHOT_DIR=ROOT / ".researchops/visual_robustness_certification"


def data_gate() -> None:
    repo=get_v3_repository()
    for scope in ("HOME_CREDIT","FREDDIE","CROSS_DATASET"):
        model=build_robustness_model(repo,scope,"vi")
        expected_effects=6 if scope=="CROSS_DATASET" else 3
        expected_contrasts=66 if scope=="CROSS_DATASET" else 33
        expected_metrics=144 if scope=="CROSS_DATASET" else 72
        if len(model.population_effects)!=expected_effects: raise RuntimeError(f"Population-effect topology drift {scope}")
        if len(model.population_contrasts)!=expected_contrasts: raise RuntimeError(f"Population-contrast topology drift {scope}")
        if len(model.metric_rows)!=expected_metrics: raise RuntimeError(f"Metric-sensitivity topology drift {scope}")
        effects=robustness_effect_dumbbell(model.population_effects,cross_dataset=scope=="CROSS_DATASET")
        contrasts=robustness_contrast_stability_map(model.population_contrasts,cross_dataset=scope=="CROSS_DATASET")
        ranks=robustness_rank_shift_heatmap(model.metric_rows,cross_dataset=scope=="CROSS_DATASET")
        margin=robustness_margin_sensitivity_plot(model.margin_rows,selected_margin=.03)
        if any(len(fig.data)==0 for fig in (effects,contrasts,ranks,margin)): raise RuntimeError(f"Robustness figure empty {scope}")
        if tuple(effects.layout.xaxis.range)!=(0,1): raise RuntimeError("Effect-size dumbbell must use fixed 0–1 scale")
        if scope=="CROSS_DATASET" and tuple(effects.layout.xaxis2.range)!=(0,1): raise RuntimeError("Cross effect-size axes are not synchronized")
    cross=build_robustness_model(repo,"CROSS_DATASET","vi")
    if sum(bool(r["direction_stable"]) for r in cross.population_contrasts)!=60: raise RuntimeError("Certified contrast direction-stability count drift")
    if sum(bool(r["significance_conclusion_stable"]) for r in cross.population_contrasts)!=64: raise RuntimeError("Certified contrast significance-stability count drift")
    lanes={round(float(r["margin"]),2):r for r in cross.margin_rows}
    if set(lanes)!={.02,.03,.05}: raise RuntimeError("Certified margin registry drift")
    if lanes[.03]["analysis_status"]!="PRIMARY_CERTIFIED" or lanes[.02]["analysis_status"]!="SENSITIVITY_ONLY" or lanes[.05]["analysis_status"]!="SENSITIVITY_ONLY": raise RuntimeError("Primary/sensitivity margin role drift")
    if int(lanes[.03]["robust_primary_candidate_count"])!=0 or int(lanes[.05]["robust_primary_candidate_count"])!=2: raise RuntimeError("Margin candidate-count sensitivity drift")
    shifts={}
    for row in cross.metric_rows: shifts.setdefault((row["dataset_scope"],row["metric_id"]),[]).append(abs(int(row["rank_shift_vs_primary"])))
    if max(shifts[("HOME_CREDIT","resolved_faithfulness")])!=16 or max(shifts[("FREDDIE","resolved_faithfulness")])!=17: raise RuntimeError("Resolved-faithfulness certified rank shifts drift")
    if cross.validator_status!="NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3" or cross.template_status!="NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3": raise RuntimeError("Capability-gap state drift")
    focus=build_robustness_model(repo,"CROSS_DATASET","vi",search="?tab=metric&dataset=FREDDIE&model=qwen3_8b&evidence=S4&metric=resolved_faithfulness&margin=0.05")
    if (focus.initial_tab,focus.focus_dataset,focus.focus_model,focus.focus_evidence,focus.focus_metric,focus.focus_margin)!=("metric","FREDDIE","qwen3_8b","S4","resolved_faithfulness",.05): raise RuntimeError("Robustness URL-state contract failed")
    print("DASHBOARD_ROBUSTNESS_0053_DATA=PASS effects=6 contrasts=66 metrics=144 margins=3 capability_gap=explicit")


def source_gate() -> None:
    page=(ROOT/"research/python/dashboard/v3/pages/robustness.py").read_text(encoding="utf-8")
    model=(ROOT/"research/python/dashboard/v3/robustness_model.py").read_text(encoding="utf-8")
    callbacks=(ROOT/"research/python/dashboard/v3/callbacks.py").read_text(encoding="utf-8")
    for token in ("Effect-size stability","Contrast Stability Map","Certified Rank Shift Heatmap","NI Margin Sensitivity","PRIMARY_CERTIFIED","SENSITIVITY_ONLY"):
        if token not in page: raise RuntimeError(f"Missing Robustness redesign token: {token}")
    if "NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3" not in model or "_capability_state" not in page:
        raise RuntimeError("Robustness capability-gap contract is not owned by model + explicit page state")
    for forbidden in ("import scipy","from scipy","statsmodels","wilcoxon(","multipletests(","bootstrap(","visualization_v2","get_dashboard_repository","idxmax(","argmax("):
        if forbidden in page or forbidden in model or forbidden in callbacks: raise RuntimeError(f"Scientific/legacy token leaked into Robustness: {forbidden}")
    if "dmc.Tabs" in page: raise RuntimeError("Robustness must use certified SegmentedControl tab runtime")
    if "robustness-detail-drawer-body-content" not in page or "robustness-detail-drawer-title-content" not in page: raise RuntimeError("Robustness Drawer content IDs are not portal-safe")
    if 'Input(LOCATION, "pathname")' not in callbacks or 'Input(LOCATION, "search")' not in callbacks: raise RuntimeError("Robustness page render must listen to pathname + search")
    print("DASHBOARD_ROBUSTNESS_0053_SOURCE=PASS science=read-only primary_vs_sensitivity=preserved capability_gap=explicit")


def _free_port():
    with socket.socket(socket.AF_INET,socket.SOCK_STREAM) as s: s.bind(("127.0.0.1",0)); return int(s.getsockname()[1])

def _wait(url,process):
    deadline=time.time()+45; last=None
    while time.time()<deadline:
        if process.poll() is not None: raise RuntimeError(f"Dashboard server exited early: {process.returncode}")
        try:
            with urlopen(url,timeout=1) as r:
                if r.status<500:return
        except Exception as e:last=e
        time.sleep(.25)
    raise RuntimeError(f"Dashboard did not become ready: {last}")

def _browser_executable():
    candidates=[shutil.which("chromium"),shutil.which("chromium-browser"),shutil.which("google-chrome"),shutil.which("google-chrome-stable"),"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome","/Applications/Chromium.app/Contents/MacOS/Chromium"]
    return next((str(x) for x in candidates if x and Path(x).exists()),None)

def _dupes(page): return page.evaluate("() => { const c={}; document.querySelectorAll('[id]').forEach(e => c[e.id]=(c[e.id]||0)+1); return Object.fromEntries(Object.entries(c).filter(([,n])=>n>1)); }")
def _layout(page): return page.evaluate("() => ({sw:document.documentElement.scrollWidth,cw:document.documentElement.clientWidth,bw:document.body.scrollWidth})")


def browser_gate() -> None:
    try: from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc: raise RuntimeError("Playwright is required for Robustness visual certification") from exc
    for package in ("dash","dash-mantine-components","dash-iconify"):
        try: importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError as exc: raise RuntimeError(f"Missing dashboard runtime dependency: {package}") from exc
    SCREENSHOT_DIR.mkdir(parents=True,exist_ok=True)
    for old in SCREENSHOT_DIR.glob("robustness_*.png"):old.unlink()
    port=_free_port();base=f"http://127.0.0.1:{port}"
    env=os.environ.copy();env.update({"DASH_HOST":"127.0.0.1","DASH_PORT":str(port),"DASH_DEBUG":"0","PYTHONUNBUFFERED":"1"})
    log=(SCREENSHOT_DIR/"dashboard_server.log").open("w",encoding="utf-8")
    process=subprocess.Popen([sys.executable,"-m","research.python.dashboard.app_v3"],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,text=True)
    try:
        _wait(base,process)
        with sync_playwright() as p:
            try:browser=p.chromium.launch(headless=True)
            except Exception:
                executable=_browser_executable()
                if not executable:raise RuntimeError("Chromium/Chrome executable unavailable")
                browser=p.chromium.launch(headless=True,executable_path=executable)
            for width,height in ((1366,768),(1440,900),(1920,1080)):
                context=browser.new_context(viewport={"width":width,"height":height})
                page=context.new_page();console=[];page_errors=[];requests=[]
                page.on("console",lambda msg:console.append(msg.text) if (msg.type=="error" or "warning #29" in msg.text.lower()) else None)
                page.on("pageerror",lambda exc:page_errors.append(str(exc)))
                page.on("requestfailed",lambda req:requests.append({"url":req.url,"failure":req.failure}))
                page.goto(base+"/robustness",wait_until="networkidle")
                page.locator("#robustness-effect-dumbbell").wait_for(state="visible",timeout=15000)
                page.locator("#robustness-contrast-stability-map").wait_for(state="visible",timeout=15000)
                text=page.locator("#v3-robustness-content").inner_text()
                for token in ("Robustness","PRIMARY_CERTIFIED","SENSITIVITY_ONLY","Contrast Stability Map","NOT_MATERIALIZED_IN_VISUALIZATION_DATA_V3"):
                    if token not in text:raise RuntimeError(f"Robustness UI missing {token}")
                points=page.locator("#robustness-contrast-stability-map .scatterlayer path.point")
                if points.count()==0:raise RuntimeError("Contrast Stability Map has no clickable markers")
                points.first.click(force=True)
                page.locator('[data-testid="robustness-drawer-content"]').wait_for(state="visible",timeout=6000)
                if _dupes(page):raise RuntimeError(f"Duplicate DOM IDs after Robustness contrast drawer: {_dupes(page)}")
                page.keyboard.press("Escape");page.locator('[data-testid="robustness-drawer-content"]').wait_for(state="hidden",timeout=4000)

                page.get_by_text("Metric sensitivity",exact=True).click();page.locator("#robustness-rank-shift-heatmap").wait_for(state="visible",timeout=5000)
                page.get_by_text("Decision sensitivity",exact=True).click();page.locator("#robustness-margin-sensitivity").wait_for(state="visible",timeout=5000)
                margin_points=page.locator("#robustness-margin-sensitivity .scatterlayer path.point")
                if margin_points.count()<3:raise RuntimeError(f"Margin sensitivity must expose three frozen lane markers, found {margin_points.count()}")
                margin_points.nth(1).click(force=True)
                page.locator('[data-testid="robustness-drawer-content"]').wait_for(state="visible",timeout=6000)
                page.keyboard.press("Escape");page.locator('[data-testid="robustness-drawer-content"]').wait_for(state="hidden",timeout=4000)
                layout=_layout(page)
                if int(layout["sw"])>int(layout["cw"])+2 or int(layout["bw"])>int(layout["cw"])+2:raise RuntimeError(f"Robustness horizontal overflow {width}x{height}: {layout}")
                if console or page_errors or requests:raise RuntimeError(f"Robustness browser errors console={console} page={page_errors} requests={requests}")
                page.screenshot(path=str(SCREENSHOT_DIR/f"robustness_cross_{width}x{height}.png"),full_page=True)
                context.close()

            context=browser.new_context(viewport={"width":1440,"height":900});page=context.new_page()
            page.goto(base+"/robustness?tab=decision&margin=0.05",wait_until="networkidle")
            page.locator("#robustness-margin-detail").wait_for(state="visible",timeout=15000)
            detail=page.locator("#robustness-margin-detail").inner_text()
            if "δ=0.05" not in detail or "SENSITIVITY_ONLY" not in detail or "qwen3_8b::S1" not in detail or "qwen3_8b::S4" not in detail:raise RuntimeError(f"Robustness margin deep-link state mismatch: {detail!r}")
            context.close()

            context=browser.new_context(viewport={"width":1440,"height":900});page=context.new_page()
            page.goto(base+"/robustness?tab=metric&dataset=FREDDIE&model=qwen3_8b&evidence=S4&metric=resolved_faithfulness",wait_until="networkidle")
            page.locator("#robustness-rank-shift-heatmap").wait_for(state="visible",timeout=15000)
            if "Resolved" not in page.locator("#v3-robustness-content").inner_text():raise RuntimeError("Robustness metric deep-link did not materialize resolved-faithfulness lens")
            context.close();browser.close()
    finally:
        if process.poll() is None:
            process.terminate()
            try:process.wait(timeout=8)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=5)
        log.close()
    print(f"DASHBOARD_ROBUSTNESS_0053_BROWSER=PASS viewports=3 screenshots={SCREENSHOT_DIR}")


def main():
    parser=argparse.ArgumentParser();parser.add_argument("--browser",action="store_true");args=parser.parse_args()
    data_gate();source_gate()
    if args.browser:browser_gate()
    print("DASHBOARD_ROBUSTNESS_0053=PASS")
    return 0

if __name__=="__main__":raise SystemExit(main())

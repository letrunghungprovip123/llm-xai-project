#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from research.python.robustness.input_lock import build_input_lock


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--protocol", required=True)
    parser.add_argument("--m25-lock", required=True)
    parser.add_argument("--m25-dir", required=True)
    parser.add_argument("--m26-policy-lock", required=True)
    parser.add_argument("--m26-dir", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(args.repo_root).resolve()
    output = Path(args.output).resolve()
    lock = build_input_lock(
        root,
        Path(args.protocol).resolve(),
        Path(args.m25_lock).resolve(),
        Path(args.m25_dir).resolve(),
        Path(args.m26_policy_lock).resolve(),
        Path(args.m26_dir).resolve(),
    )
    encoded = json.dumps(lock, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        if output.read_text(encoding="utf-8") == encoded:
            print(
                "MULTIDATASET_M27A_ROBUSTNESS_INPUT_LOCK=ALREADY_CERTIFIED "
                f"hc_complete={lock['observed']['home_credit_complete_case_count']} "
                f"freddie_complete={lock['observed']['freddie_complete_case_count']}"
            )
            return 0
        raise SystemExit(f"Refusing to overwrite different M27 input lock: {output}")
    output.write_text(encoded, encoding="utf-8")
    print(
        "MULTIDATASET_M27A_ROBUSTNESS_INPUT_LOCK=PASS "
        f"hc_complete={lock['observed']['home_credit_complete_case_count']} "
        f"freddie_complete={lock['observed']['freddie_complete_case_count']} "
        f"validator={lock['readiness']['validator_sensitivity']['status']} "
        f"template={lock['readiness']['template_baseline']['status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

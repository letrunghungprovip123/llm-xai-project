#!/usr/bin/env python3
"""Wrap certified Home Credit preparation outputs in CanonicalDatasetBundleV1.

The current refactor worktree is allowed to contain only code/manifests. Large
historical prepared artifacts may remain in an older sibling repository. This
script discovers such a read-only artifact root without copying or rewriting
those outputs.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from research.python.datasets.adapters.home_credit import HomeCreditCompatibilityAdapter
from research.python.datasets.root import find_repository_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Output bundle manifest. Default: "
            "data/manifests/canonical_dataset_bundle_home_credit_v1.json"
        ),
    )
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=None,
        help=(
            "Root containing historical Home Credit prepared outputs. "
            "If omitted, the script checks an environment override, the current "
            "repo, then known sibling worktrees such as llm-xai-next."
        ),
    )
    return parser.parse_args()


def candidate_artifact_roots(project_root: Path, explicit: Path | None) -> list[Path]:
    if explicit is not None:
        return [explicit.expanduser().resolve()]

    candidates: list[Path] = []
    env_value = os.environ.get("LLM_XAI_HOME_CREDIT_ARTIFACT_ROOT", "").strip()
    if env_value:
        candidates.append(Path(env_value).expanduser().resolve())

    candidates.extend(
        [
            project_root.resolve(),
            (project_root.parent / "llm-xai-next").resolve(),
            (project_root.parent / "llm-xai-project").resolve(),
        ]
    )

    unique: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = str(candidate)
        if key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def resolve_adapter(project_root: Path, explicit: Path | None) -> tuple[HomeCreditCompatibilityAdapter, dict[str, object]]:
    diagnostics: list[tuple[Path, list[str]]] = []
    for candidate in candidate_artifact_roots(project_root, explicit):
        adapter = HomeCreditCompatibilityAdapter(
            project_root=project_root,
            artifact_root=candidate,
        )
        validation = adapter.validate_source()
        if validation["status"] == "passed":
            return adapter, validation
        diagnostics.append((candidate, list(validation["missing_required"])))

    lines = [
        "Cannot build canonical bundle; no artifact root contains all required "
        "historical Home Credit outputs.",
        "Checked:",
    ]
    for candidate, missing in diagnostics:
        lines.append(f"  - {candidate}")
        for relative in missing:
            lines.append(f"      missing: {relative}")
    lines.extend(
        [
            "",
            "If the outputs are stored elsewhere, rerun with:",
            "  python scripts/multidataset/build_home_credit_canonical_bundle.py "
            "--artifact-root /path/to/repo-containing-data-and-ml-registry",
            "or set LLM_XAI_HOME_CREDIT_ARTIFACT_ROOT.",
        ]
    )
    raise SystemExit("\n".join(lines))


def main() -> None:
    args = parse_args()
    root = find_repository_root(Path(__file__))
    output = args.output or (
        root / "data/manifests/canonical_dataset_bundle_home_credit_v1.json"
    )
    adapter, validation = resolve_adapter(root, args.artifact_root)
    bundle = adapter.build_canonical_bundle(output)
    print("HOME_CREDIT_CANONICAL_BUNDLE=PASS")
    print(f"dataset_id={bundle.dataset_id}")
    print(f"dataset_fingerprint={bundle.dataset_fingerprint}")
    print(f"artifact_root={validation['artifact_root']}")
    print(f"output={output}")
    if validation["missing_optional"]:
        print(f"warnings_missing_optional={validation['missing_optional']}")


if __name__ == "__main__":
    main()

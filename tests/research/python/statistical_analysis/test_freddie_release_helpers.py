from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from scripts.research.freddie_m23_statistics_0025 import (
    add_contrast_ids,
    reverify_existing_release,
    sha,
)


class ReleaseHelperTests(unittest.TestCase):
    def test_contrast_id_mapping(self) -> None:
        frame = pd.DataFrame([
            {
                "contrast_family": "model_within_evidence",
                "condition_a_model_id": "a",
                "condition_a_evidence_level": "S2",
                "condition_b_model_id": "b",
                "condition_b_evidence_level": "S2",
            },
            {
                "contrast_family": "evidence_vs_s0",
                "condition_a_model_id": "a",
                "condition_a_evidence_level": "S3",
                "condition_b_model_id": "a",
                "condition_b_evidence_level": "S0",
            },
        ])
        out = add_contrast_ids(frame)
        self.assertEqual(out.loc[0, "contrast_id"], "model_within_evidence::S2::a::b")
        self.assertEqual(out.loc[1, "contrast_id"], "evidence_vs_s0::a::S3")

    def test_existing_release_reverify_is_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            output = root / "statistical_analysis_v1"
            output.mkdir()
            lock = root / "freddie_statistical_input_lock.json"
            lock.write_text("{}\n", encoding="utf-8")

            payloads = {
                "statistical_validation.json": {
                    "passed": True,
                    "exit_gate": "STATISTICAL_CORE_READY",
                },
                "contrast_registry_validation.json": {"passed": True},
                "bootstrap_validation.json": {"passed": True},
            }
            for name, payload in payloads.items():
                (output / name).write_text(
                    json.dumps(payload, sort_keys=True) + "\n",
                    encoding="utf-8",
                )
            (output / "paired_tests.csv").write_text("x\n1\n", encoding="utf-8")

            files = {}
            for path in sorted(output.iterdir()):
                if path.name == "statistical_manifest.json":
                    continue
                files[path.name] = {
                    "sha256": sha(path),
                    "byte_count": path.stat().st_size,
                }
            manifest = {
                "gate": "STATISTICAL_CORE_READY",
                "freddie_gate": "FREDDIE_STATISTICAL_CORE_READY",
                "parent_statistical_input_lock": {"sha256": sha(lock)},
                "files": files,
            }
            (output / "statistical_manifest.json").write_text(
                json.dumps(manifest, sort_keys=True) + "\n",
                encoding="utf-8",
            )

            observed = reverify_existing_release(root, output, lock)
            self.assertEqual(observed["gate"], "STATISTICAL_CORE_READY")

            (output / "paired_tests.csv").write_text("x\n2\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                reverify_existing_release(root, output, lock)


if __name__ == "__main__":
    unittest.main()

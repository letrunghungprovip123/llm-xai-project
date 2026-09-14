"""Regression tests for the additive multi-dataset foundation."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from research.python.datasets.adapters.home_credit import (
    HomeCreditCompatibilityAdapter,
    REQUIRED_ARTIFACTS,
)
from research.python.datasets.contracts import CanonicalDatasetBundle
from research.python.datasets.execution import DatasetExecutionContext
from research.python.datasets.identity import canonical_case_id
from research.python.datasets.profile import (
    load_dataset_profile,
    load_experiment_profile,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[4]


class ContractTests(unittest.TestCase):
    def test_home_credit_profile_matches_legacy_identity_and_target(self) -> None:
        profile = load_dataset_profile(
            REPOSITORY_ROOT / "config/research/datasets/home_credit_v1.json"
        )
        self.assertEqual(profile.dataset_id, "home_credit_default_risk")
        self.assertEqual(profile.entity.source_id_column, "SK_ID_CURR")
        self.assertEqual(profile.target.source_column, "TARGET")
        self.assertEqual(
            profile.target.effective_prediction_semantics.positive_label,
            "high_default_risk",
        )
        self.assertEqual(
            profile.target.effective_prediction_semantics.negative_label,
            "low_default_risk",
        )
        self.assertEqual(profile.capabilities.feature_count, 166)

    def test_target_semantics_defaults_preserve_legacy_profiles(self) -> None:
        from research.python.datasets.contracts import TargetContract

        target = TargetContract.from_dict(
            {
                "source_column": "outcome",
                "canonical_name": "target",
                "positive_value": 1,
                "negative_value": 0,
                "semantic_name": "credit_event",
                "prediction_horizon": None,
            }
        )
        self.assertEqual(target.effective_prediction_semantics.positive_label, "high_default_risk")
        self.assertEqual(target.effective_prediction_semantics.negative_label, "low_default_risk")
        self.assertNotIn("prediction_semantics", target.to_dict())

    def test_experiment_profile_preserves_648_matrix(self) -> None:
        profile = load_experiment_profile(
            REPOSITORY_ROOT / "config/research/experiments/home_credit_experiment_v1.json"
        )
        self.assertEqual(len(profile.case_strata), 6)
        self.assertEqual(profile.cases_per_stratum, 6)
        self.assertEqual(len(profile.evidence_conditions), 6)
        self.assertEqual(profile.llm_count, 3)
        self.assertEqual(profile.expected_planned_generations, 648)

    def test_dataset_identity_prevents_cross_dataset_collision(self) -> None:
        home = canonical_case_id("home_credit_default_risk", "credit_application", 156227)
        other = canonical_case_id("dataset_b", "credit_application", 156227)
        self.assertNotEqual(home, other)
        self.assertEqual(
            home,
            canonical_case_id("home_credit_default_risk", "credit_application", 156227),
        )


class ExecutionIsolationTests(unittest.TestCase):
    def test_workspace_is_scoped_by_dataset_experiment_and_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            context = DatasetExecutionContext(
                project_root=root,
                dataset_id="dataset_b",
                experiment_id="replication_v1",
                run_id="run_001",
            )
            self.assertEqual(
                context.workspace_root,
                root.resolve()
                / ".researchops/workspaces/dataset_b/replication_v1/run_001",
            )
            self.assertEqual(
                context.paths.processed_dir,
                context.workspace_root / "data/processed",
            )
            self.assertNotEqual(context.paths.processed_dir, root / "data/processed")

    def test_unsafe_workspace_segment_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                DatasetExecutionContext(
                    project_root=Path(directory),
                    dataset_id="../dataset_b",
                    experiment_id="replication_v1",
                    run_id="run_001",
                )


class HomeCreditCompatibilityAdapterTests(unittest.TestCase):
    def test_adapter_wraps_existing_outputs_without_rewriting_them(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile_path = root / "config/research/datasets/home_credit_v1.json"
            profile_path.parent.mkdir(parents=True)
            source_profile = (
                REPOSITORY_ROOT / "config/research/datasets/home_credit_v1.json"
            ).read_text(encoding="utf-8")
            profile_path.write_text(source_profile, encoding="utf-8")

            for name, relative_path in REQUIRED_ARTIFACTS.items():
                path = root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"fixture:{name}".encode("utf-8"))

            raw_manifest = root / "data/manifests/raw_file_manifest.json"
            raw_manifest.parent.mkdir(parents=True, exist_ok=True)
            raw_manifest.write_text(
                json.dumps(
                    {
                        "dataset_name": "home_credit_default_risk",
                        "raw_files": {
                            "application_train.csv": {"sha256": "a" * 64},
                            "bureau.csv": {"sha256": "b" * 64},
                        },
                    }
                ),
                encoding="utf-8",
            )

            adapter = HomeCreditCompatibilityAdapter(
                project_root=root,
                profile_path=profile_path,
            )
            validation = adapter.validate_source()
            self.assertEqual(validation["status"], "passed")

            output = root / "data/manifests/canonical_dataset_bundle_home_credit_v1.json"
            bundle = adapter.build_canonical_bundle(output)
            self.assertTrue(output.is_file())
            self.assertEqual(bundle.dataset_id, "home_credit_default_risk")
            self.assertEqual(
                bundle.provenance["historical_outputs_wrapped_without_rewrite"], True
            )
            parsed = CanonicalDatasetBundle.from_dict(
                json.loads(output.read_text(encoding="utf-8"))
            )
            self.assertEqual(parsed.dataset_fingerprint, bundle.dataset_fingerprint)

    def test_adapter_can_read_historical_outputs_from_separate_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as project_directory, tempfile.TemporaryDirectory() as artifact_directory:
            project_root = Path(project_directory)
            artifact_root = Path(artifact_directory)
            profile_path = project_root / "config/research/datasets/home_credit_v1.json"
            profile_path.parent.mkdir(parents=True)
            profile_path.write_text(
                (REPOSITORY_ROOT / "config/research/datasets/home_credit_v1.json").read_text(encoding="utf-8"),
                encoding="utf-8",
            )

            for name, relative_path in REQUIRED_ARTIFACTS.items():
                path = artifact_root / relative_path
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(f"historical-fixture:{name}".encode("utf-8"))

            adapter = HomeCreditCompatibilityAdapter(
                project_root=project_root,
                profile_path=profile_path,
                artifact_root=artifact_root,
            )
            validation = adapter.validate_source()
            self.assertEqual(validation["status"], "passed")
            self.assertEqual(validation["artifact_root"], str(artifact_root.resolve()))

            output = project_root / "data/manifests/canonical_dataset_bundle_home_credit_v1.json"
            bundle = adapter.build_canonical_bundle(output)
            self.assertTrue(output.is_file())
            self.assertEqual(
                bundle.provenance["artifact_source_root_locator"],
                str(artifact_root.resolve()),
            )
            self.assertTrue(bundle.provenance["artifact_paths_relative_to_source_root"])


if __name__ == "__main__":
    unittest.main()

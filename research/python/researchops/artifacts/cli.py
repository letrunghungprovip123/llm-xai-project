from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from .catalog import project_root
from .manifest import load_manifest
from .models import ArtifactProducer, ArtifactSource
from .package_builder import ArtifactPackageBuilder
from .profiles import load_store


def _git_commit() -> str:
    completed = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=project_root(),
        text=True,
        check=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ResearchOps artifact tooling")
    parser.add_argument("--profile", default="development-filesystem")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate-manifest")
    validate.add_argument("path", type=Path)

    inspect = sub.add_parser("inspect")
    inspect.add_argument("artifact_id")

    verify = sub.add_parser("verify")
    verify.add_argument("artifact_id")

    bootstrap = sub.add_parser("bootstrap-s3")
    bootstrap.add_argument("--env-prefix", default="RESEARCHOPS_S3_")

    import_dir = sub.add_parser("import-directory")
    import_dir.add_argument("source", type=Path)
    import_dir.add_argument("--artifact-type", required=True)
    import_dir.add_argument("--schema-version", required=True)
    import_dir.add_argument("--stage-id", required=True)
    import_dir.add_argument("--stage-version", type=int, default=1)
    import_dir.add_argument("--registry-sha256", required=True)
    import_dir.add_argument("--artifact-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "bootstrap-s3":
        from .bootstrap import bootstrap_s3_bucket
        from .s3_settings import S3StoreSettings
        settings = S3StoreSettings.from_environment(args.env_prefix)
        result = bootstrap_s3_bucket(
            settings.create_client(), bucket=settings.bucket, region=settings.region
        )
        print(json.dumps(result.__dict__, indent=2))
        return 0 if result.versioning_enabled and result.read_write_probe_passed else 2
    if args.command == "validate-manifest":
        manifest = load_manifest(args.path)
        print(json.dumps({
            "artifact_id": manifest.artifact_id,
            "manifest_sha256": manifest.manifest_sha256,
            "result": "ARTIFACT_MANIFEST_VALID",
        }, indent=2))
        return 0

    store = load_store(args.profile)
    if args.command == "inspect":
        manifest = store.get_manifest(args.artifact_id)
        print(json.dumps(manifest.canonical_payload(), indent=2, ensure_ascii=False))
        return 0
    if args.command == "verify":
        result = store.verify(args.artifact_id)
        print(json.dumps(result.model_dump(mode="json"), indent=2))
        return 0 if result.passed else 2
    if args.command == "import-directory":
        builder = ArtifactPackageBuilder(
            artifact_id=args.artifact_id,
            artifact_type=args.artifact_type,
            schema_version=args.schema_version,
            producer=ArtifactProducer(
                stage_id=args.stage_id,
                stage_version=args.stage_version,
                stage_run_id=None,
                registry_sha256=args.registry_sha256,
            ),
            source=ArtifactSource(source_commit=_git_commit()),
        )
        package = builder.add_directory(args.source).build()
        reference = store.put_package(package)
        print(json.dumps(reference.model_dump(mode="json"), indent=2))
        return 0
    raise AssertionError(args.command)

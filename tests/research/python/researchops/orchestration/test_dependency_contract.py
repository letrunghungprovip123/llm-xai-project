from pathlib import Path


def test_prefect_dependencies_are_pinned_for_python_312_runtime():
    requirements = Path("research/python/requirements-researchops.txt").read_text(
        encoding="utf-8"
    ).splitlines()

    assert "prefect==3.7.8" in requirements
    assert "asyncpg>=0.30,<1" in requirements


def test_local_prefect_environment_is_git_ignored():
    ignore = Path(".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".env.researchops-prefect.local" in ignore

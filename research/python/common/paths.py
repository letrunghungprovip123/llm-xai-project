"""Định nghĩa đường dẫn mặc định mà không tạo file hoặc thư mục khi import."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResearchPaths:
    """Các đường dẫn repository dùng xuyên suốt pipeline ML/XAI."""

    project_root: Path

    @property
    def raw_dir(self) -> Path:
        return self.project_root / "data" / "raw"

    @property
    def interim_dir(self) -> Path:
        return self.project_root / "data" / "interim"

    @property
    def processed_dir(self) -> Path:
        return self.project_root / "data" / "processed"

    @property
    def report_dir(self) -> Path:
        return self.project_root / "data" / "reports"

    @property
    def manifest_dir(self) -> Path:
        return self.project_root / "data" / "manifests"

    @property
    def registry_dir(self) -> Path:
        return self.project_root / "ml" / "registry"

    def relative(self, path: Path) -> str:
        """Trả đường dẫn tương đối để manifest không phụ thuộc máy chạy."""

        return str(path.relative_to(self.project_root))


def find_project_root(start_path: Path) -> Path:
    """Find the repository root without depending on module depth."""

    resolved_start = start_path.resolve()

    current_path = (
        resolved_start.parent
        if resolved_start.is_file()
        else resolved_start
    )

    for candidate in [
        current_path,
        *current_path.parents,
    ]:
        has_package_json = (
            candidate / "package.json"
        ).is_file()

        has_research_folder = (
            candidate / "research"
        ).is_dir()

        has_data_folder = (
            candidate / "data"
        ).is_dir()

        if (
            has_package_json
            and has_research_folder
            and has_data_folder
        ):
            return candidate

    raise FileNotFoundError(
        f"Could not locate project root from: {start_path}"
    )


DEFAULT_PATHS = ResearchPaths(find_project_root(Path(__file__)))


def create_directories(*paths: Path) -> None:
    """Chỉ tạo output directory khi stage thực sự bắt đầu chạy."""

    for path in paths:
        path.mkdir(parents=True, exist_ok=True)

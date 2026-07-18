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


DEFAULT_PATHS = ResearchPaths(Path(__file__).resolve().parents[3])


def create_directories(*paths: Path) -> None:
    """Chỉ tạo output directory khi stage thực sự bắt đầu chạy."""

    for path in paths:
        path.mkdir(parents=True, exist_ok=True)

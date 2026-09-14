"""Các hàm hash phục vụ provenance artifact."""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_file(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    """Tính SHA-256 theo chunk để không nạp toàn bộ artifact vào bộ nhớ."""

    digest = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit


@dataclass(frozen=True)
class DatabaseSettings:
    url: str
    echo: bool = False
    pool_pre_ping: bool = True

    @classmethod
    def from_environment(
        cls,
        variable: str = "RESEARCHOPS_DATABASE_URL",
        *,
        required: bool = True,
    ) -> "DatabaseSettings | None":
        value = os.getenv(variable)
        if not value:
            if required:
                raise RuntimeError(f"Missing required environment variable {variable}")
            return None
        if not value.startswith("postgresql+"):
            raise RuntimeError("ResearchOps operational database must use PostgreSQL")
        return cls(url=value, echo=os.getenv("RESEARCHOPS_SQL_ECHO", "false").lower() == "true")

    @property
    def redacted_url(self) -> str:
        parts = urlsplit(self.url)
        if parts.password is None:
            return self.url
        username = parts.username or ""
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
        netloc = f"{username}:***@{host}{port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))

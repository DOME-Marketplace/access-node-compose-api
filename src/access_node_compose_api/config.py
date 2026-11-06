"""Runtime configuration, read from environment variables.

The variable names are the contract with the Kubernetes deployment in dome-gitops:
changing one here requires changing the deployment too.
"""

import re
from pathlib import Path, PurePosixPath

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_BASE_PATH_RE = re.compile(r"(/[A-Za-z0-9._~-]+)+")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(frozen=True, extra="ignore")

    gitops_repo_url: str = "https://github.com/DOME-Marketplace/dome-gitops.git"
    gitops_branch: str = "main"
    # Required on purpose: a wrong default would silently serve another environment.
    access_node_chart_path: str
    refresh_interval_seconds: int = Field(default=300, ge=30)
    work_dir: Path = Path("/work")
    base_path: str = ""
    port: int = Field(default=8080, ge=1, le=65535)
    # Authentication is disabled unless API_KEY is set to a non-empty value.
    api_key: SecretStr | None = None

    @field_validator("gitops_repo_url", "gitops_branch")
    @classmethod
    def _no_option_injection(cls, value: str) -> str:
        value = value.strip()
        if not value or value.startswith("-"):
            raise ValueError("must be non-empty and must not start with '-'")
        return value

    @field_validator("access_node_chart_path")
    @classmethod
    def _relative_chart_path(cls, value: str) -> str:
        path = PurePosixPath(value.strip().strip("/"))
        if not path.parts or path == PurePosixPath("."):
            raise ValueError("must not be empty")
        if ".." in path.parts or any(part.startswith("-") for part in path.parts):
            raise ValueError("must be a plain path inside the gitops repository")
        return str(path)

    @field_validator("base_path")
    @classmethod
    def _normalize_base_path(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if value and not _BASE_PATH_RE.fullmatch(value):
            raise ValueError("must be empty or look like '/segment[/segment...]'")
        return value

    @field_validator("api_key", mode="before")
    @classmethod
    def _empty_api_key_is_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def api_prefix(self) -> str:
        """Prefix of every route served by the application."""
        return f"{self.base_path}/v1"

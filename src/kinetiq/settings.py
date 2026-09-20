"""Kinetiq settings — loaded from environment variables (prefix KINETIQ_)."""
from __future__ import annotations
from pathlib import Path
import re
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_TOKEN_RE = re.compile(r"^[A-Za-z0-9_-]{48,128}$")


class Settings(BaseSettings):
    """Runtime configuration.

    Read from environment (prefix ``KINETIQ_``), falling back to a local ``.env``
    file in the working directory. Anything sensitive must never be logged;
    :func:`kinetiq.logging_config.setup_logging` installs a redaction filter.
    """

    model_config = SettingsConfigDict(
        env_prefix="KINETIQ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Core --------------------------------------------------------------
    data_dir: Path = Field(default=Path("./data"))
    db_path: Path | None = None  # derived from data_dir if unset
    timezone: str = "Asia/Kolkata"
    mcp_path_token: str = Field(default="")
    domain: str = Field(default="localhost")
    version: str = "0.1.0"

    # HTTP transport ---------------------------------------------------
    host: str = "0.0.0.0"
    port: int = 8765
    host_protection: str = "off"          # "off" | "strict"
    stateless_http: bool = True
    mask_error_details: bool = True

    # Rate / response limits -------------------------------------------
    rate_limit_rps: float = 10.0
    rate_limit_burst: int = 30
    response_max_size: int = 400_000

    # Research ---------------------------------------------------------
    research_daily_budget: int = 300
    ncbi_api_key: str | None = None
    s2_api_key: str | None = None
    openalex_mailto: str | None = None

    # Logging ----------------------------------------------------------
    log_level: str = "INFO"
    log_format: str = "json"              # "json" | "text"
    log_payloads: bool = False

    # Dev / test convenience -------------------------------------------
    allow_weak_token: bool = False

    # ------------------------------------------------------------------
    @field_validator("mcp_path_token")
    @classmethod
    def _validate_token(cls, v: str) -> str:
        # empty is allowed here so tests can construct Settings without it;
        # cli.serve enforces presence and format at startup.
        if v and not _TOKEN_RE.match(v):
            raise ValueError(
                "KINETIQ_MCP_PATH_TOKEN must be 48-128 url-safe chars "
                "(A-Z, a-z, 0-9, _, -)"
            )
        return v

    def resolved_db_path(self) -> Path:
        if self.db_path is not None:
            return self.db_path
        return self.data_dir / "kinetiq.db"

    def resolved_backup_dir(self) -> Path:
        return self.data_dir / "backups"

    def mcp_url_path(self) -> str:
        return f"/mcp/{self.mcp_path_token}"

    def sensitive_values(self) -> list[str]:
        """Substrings the log filter should scrub."""
        vals: list[str] = []
        if self.mcp_path_token:
            vals.append(self.mcp_path_token)
        for v in (self.ncbi_api_key, self.s2_api_key):
            if v:
                vals.append(v)
        return vals

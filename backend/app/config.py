"""Environment-driven configuration (matrix row D1, D2).

No hardcoded home directories, usernames, or executable paths: every
path is resolved through platformdirs and can be overridden by an
environment variable. Secrets are read from the environment / OS keychain,
never from source code.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from platformdirs import user_config_dir, user_data_dir, user_log_dir
from pydantic_settings import BaseSettings, SettingsConfigDict

DeploymentMode = Literal["local", "hybrid", "remote"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="JARVIS_", env_file=".env", extra="ignore")

    app_name: str = "jarvis"
    deployment_mode: DeploymentMode = "local"
    debug: bool = False

    # Path overrides; None -> platformdirs default for the running OS.
    data_dir: Path | None = None
    config_dir: Path | None = None
    log_dir: Path | None = None

    # Local worker allowlists. Default-deny: empty lists mean nothing runs.
    allowlist_commands: tuple[str, ...] = ()
    allowlist_apps: tuple[str, ...] = ()

    # If True, high-risk tools (e.g. shell) are blocked until interactive
    # human approval (ADR-0005 gate 3) — the client UI wires this later.
    require_approval: bool = False

    # Optional shared secret for worker pairing (see ADR-0005). Never committed.
    worker_token: str = ""

    # Provider layer (matrix row C7): llm_provider="mock" needs no API key.
    llm_provider: Literal["mock", "openai"] = "mock"
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_api_key: str = ""

    # Workflow layer (matrix row C6): n8n for Hybrid/Remote. An empty
    # n8n_base_url disables the bridge — tools and API then report the
    # workflow layer as unavailable (graceful degradation, never a crash).
    n8n_base_url: str = ""
    n8n_api_key: str = ""
    # Default-deny webhook allowlist for the workflow.run tool. Empty means
    # no workflow can be triggered through the agent (mirrors allowlists above).
    allowlist_webhooks: tuple[str, ...] = ()

    # Local store location (SQLite in local mode; Postgres later per ADR-0004).
    db_path: Path | None = None

    @property
    def workflow_enabled(self) -> bool:
        return bool(self.n8n_base_url)

    @property
    def resolved_db_path(self) -> Path:
        return self.db_path or self.resolved_data_dir / "jarvis.db"

    @property
    def resolved_data_dir(self) -> Path:
        return self.data_dir or Path(user_data_dir(self.app_name, appauthor=False))

    @property
    def resolved_config_dir(self) -> Path:
        return self.config_dir or Path(user_config_dir(self.app_name, appauthor=False))

    @property
    def resolved_log_dir(self) -> Path:
        return self.log_dir or Path(user_log_dir(self.app_name, appauthor=False))


@lru_cache
def get_settings() -> Settings:
    return Settings()
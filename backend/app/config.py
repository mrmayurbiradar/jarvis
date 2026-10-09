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

    # Local worker shell allowlist. Default-deny: an empty list means nothing runs.
    allowlist_commands: tuple[str, ...] = ()

    # Optional shared secret for worker pairing (see ADR-0005). Never committed.
    worker_token: str = ""

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
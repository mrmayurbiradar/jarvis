"""Module-level FastAPI dependencies, overridden per-app in `create_app`.

Defined at module level (not as closures inside the app factory) so lazy
string annotations under `from __future__ import annotations` resolve them
correctly — a closure in an annotation is silently dropped by FastAPI and
the parameter becomes a query param (see PROGRESS.md gotcha).
"""
from __future__ import annotations

from app.config import Settings, get_settings
from app.core.store import Store
from app.execution.platform.base import PlatformAdapter
from app.execution.platform.registry import adapter_for_platform
from app.orchestration.agent import Agent


def get_settings_dep() -> Settings:
    return get_settings()


def get_adapter_dep() -> PlatformAdapter:
    return adapter_for_platform()


def get_store_dep() -> Store:
    raise RuntimeError("store not configured — construct the app via create_app()")


def get_agent_dep() -> Agent:
    raise RuntimeError("agent not configured — construct the app via create_app()")
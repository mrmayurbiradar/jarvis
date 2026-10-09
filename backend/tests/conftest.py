"""Shared test fixtures."""
from __future__ import annotations

import pytest

from app.execution.platform.registry import adapter_for_platform


@pytest.fixture
def adapter() -> PlatformAdapter:
    """The adapter for the OS this test run is executing on."""
    return adapter_for_platform()


# Import PlatformAdapter for type annotation in the fixture above.
from app.execution.platform.base import PlatformAdapter
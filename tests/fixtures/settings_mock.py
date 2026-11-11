"""Shared configuration for tests that replace ``get_settings`` with a MagicMock.

A bare MagicMock answers every attribute with another MagicMock, so a typed
setting such as ``browser_proxy: SecretStr | None`` would arrive as a mock, not
as "unset". Pass ``**NO_PROXY`` to ``patch(".../get_settings")`` (#1036).
"""

from __future__ import annotations

NO_PROXY = {"return_value.browser_proxy": None}

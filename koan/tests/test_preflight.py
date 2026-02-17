"""Tests for app.preflight — pre-flight quota check."""

import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _env(monkeypatch, tmp_path):
    monkeypatch.setenv("KOAN_ROOT", str(tmp_path))


# Lazy imports inside preflight_quota_check:
#   from app.usage_tracker import _get_budget_mode  → patch at source
#   from app.provider import get_provider            → patch at source
BUDGET_MODE_PATCH = "app.usage_tracker._get_budget_mode"
GET_PROVIDER_PATCH = "app.provider.get_provider"


# ── Budget mode bypass ────────────────────────────────────────────


class TestBudgetModeBypass:
    """When budget_mode is disabled, preflight should skip the check."""

    def test_disabled_budget_returns_ok(self):
        with patch(BUDGET_MODE_PATCH, return_value="disabled"):
            from app.preflight import preflight_quota_check
            ok, err = preflight_quota_check("/some/path", "/some/instance")
        assert ok is True
        assert err is None

    def test_full_budget_does_not_bypass(self):
        mock_provider = MagicMock()
        mock_provider.check_quota_available.return_value = (True, "")
        with (
            patch(BUDGET_MODE_PATCH, return_value="full"),
            patch(GET_PROVIDER_PATCH, return_value=mock_provider),
        ):
            from app.preflight import preflight_quota_check
            ok, err = preflight_quota_check("/p", "/i")
        assert ok is True
        mock_provider.check_quota_available.assert_called_once_with("/p")

    def test_session_only_budget_does_not_bypass(self):
        mock_provider = MagicMock()
        mock_provider.check_quota_available.return_value = (True, "")
        with (
            patch(BUDGET_MODE_PATCH, return_value="session_only"),
            patch(GET_PROVIDER_PATCH, return_value=mock_provider),
        ):
            from app.preflight import preflight_quota_check
            ok, err = preflight_quota_check("/p", "/i")
        assert ok is True

    def test_budget_mode_import_error_proceeds(self):
        """If _get_budget_mode import fails, check should proceed."""
        mock_provider = MagicMock()
        mock_provider.check_quota_available.return_value = (True, "")
        with (
            patch(BUDGET_MODE_PATCH, side_effect=ImportError("no module")),
            patch(GET_PROVIDER_PATCH, return_value=mock_provider),
        ):
            from app.preflight import preflight_quota_check
            ok, err = preflight_quota_check("/p", "/i")
        assert ok is True


# ── Provider resolution ───────────────────────────────────────────


class TestProviderResolution:
    """Provider lookup failures should not block missions."""

    def test_provider_import_error_returns_ok(self):
        with (
            patch(BUDGET_MODE_PATCH, return_value="full"),
            patch(GET_PROVIDER_PATCH, side_effect=ImportError("nope")),
        ):
            from app.preflight import preflight_quota_check
            ok, err = preflight_quota_check("/p", "/i")
        assert ok is True
        assert err is None

    def test_provider_runtime_error_returns_ok(self):
        with (
            patch(BUDGET_MODE_PATCH, return_value="full"),
            patch(GET_PROVIDER_PATCH, side_effect=RuntimeError("bad config")),
        ):
            from app.preflight import preflight_quota_check
            ok, err = preflight_quota_check("/p", "/i")
        assert ok is True
        assert err is None


# ── Quota check outcomes ──────────────────────────────────────────


class TestQuotaCheckOutcomes:
    """Test the actual quota probe flow."""

    def test_quota_available(self):
        mock_provider = MagicMock()
        mock_provider.check_quota_available.return_value = (True, "")
        with (
            patch(BUDGET_MODE_PATCH, return_value="full"),
            patch(GET_PROVIDER_PATCH, return_value=mock_provider),
        ):
            from app.preflight import preflight_quota_check
            ok, err = preflight_quota_check("/project", "/instance", "myproject")
        assert ok is True
        assert err is None
        mock_provider.check_quota_available.assert_called_once_with("/project")

    def test_quota_exhausted(self):
        mock_provider = MagicMock()
        mock_provider.check_quota_available.return_value = (False, "Quota exceeded. Resets at 2pm.")
        with (
            patch(BUDGET_MODE_PATCH, return_value="full"),
            patch(GET_PROVIDER_PATCH, return_value=mock_provider),
        ):
            from app.preflight import preflight_quota_check
            ok, err = preflight_quota_check("/project", "/instance")
        assert ok is False
        assert "Quota exceeded" in err

    def test_quota_exhausted_empty_detail(self):
        mock_provider = MagicMock()
        mock_provider.check_quota_available.return_value = (False, "")
        with (
            patch(BUDGET_MODE_PATCH, return_value="full"),
            patch(GET_PROVIDER_PATCH, return_value=mock_provider),
        ):
            from app.preflight import preflight_quota_check
            ok, err = preflight_quota_check("/project", "/instance")
        assert ok is False
        assert err == ""

    def test_project_path_passed_to_provider(self):
        """Verify the project_path argument flows to the provider."""
        mock_provider = MagicMock()
        mock_provider.check_quota_available.return_value = (True, "")
        with (
            patch(BUDGET_MODE_PATCH, return_value="full"),
            patch(GET_PROVIDER_PATCH, return_value=mock_provider),
        ):
            from app.preflight import preflight_quota_check
            preflight_quota_check("/my/specific/path", "/inst")
        mock_provider.check_quota_available.assert_called_once_with("/my/specific/path")


# ── Edge cases ────────────────────────────────────────────────────


class TestEdgeCases:
    """Edge cases and defensive behavior."""

    def test_default_project_name_empty(self):
        """project_name defaults to empty string — doesn't affect flow."""
        mock_provider = MagicMock()
        mock_provider.check_quota_available.return_value = (True, "")
        with (
            patch(BUDGET_MODE_PATCH, return_value="full"),
            patch(GET_PROVIDER_PATCH, return_value=mock_provider),
        ):
            from app.preflight import preflight_quota_check
            ok, err = preflight_quota_check("/p", "/i")
        assert ok is True

    def test_budget_mode_exception_is_not_import_error(self):
        """Any exception from _get_budget_mode is caught, not just ImportError."""
        mock_provider = MagicMock()
        mock_provider.check_quota_available.return_value = (True, "")
        with (
            patch(BUDGET_MODE_PATCH, side_effect=ValueError("corrupt config")),
            patch(GET_PROVIDER_PATCH, return_value=mock_provider),
        ):
            from app.preflight import preflight_quota_check
            ok, err = preflight_quota_check("/p", "/i")
        assert ok is True

    def test_provider_check_raises_exception(self):
        """If the provider's check_quota_available raises, preflight should propagate."""
        mock_provider = MagicMock()
        mock_provider.check_quota_available.side_effect = OSError("network down")
        with (
            patch(BUDGET_MODE_PATCH, return_value="full"),
            patch(GET_PROVIDER_PATCH, return_value=mock_provider),
        ):
            from app.preflight import preflight_quota_check
            with pytest.raises(OSError, match="network down"):
                preflight_quota_check("/p", "/i")

"""Tests for x_auth.py — X (Twitter) OAuth 2.0 token management."""

import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from app.x_auth import (
    _get_x_credentials,
    _get_token_cache_path,
    _load_persisted_token,
    _persist_token,
    refresh_access_token,
    get_auth_header,
    is_configured,
    reset_token_cache,
)


@pytest.fixture(autouse=True)
def clean_token_cache():
    """Reset token cache between tests."""
    reset_token_cache()
    yield
    reset_token_cache()


class TestGetXCredentials:
    @patch.dict("os.environ", {
        "KOAN_X_CLIENT_ID": "test-client-id",
        "KOAN_X_CLIENT_SECRET": "test-secret",
        "KOAN_X_REFRESH_TOKEN": "test-refresh",
    })
    @patch("app.x_auth.load_dotenv")
    def test_reads_from_env(self, _mock_dotenv):
        creds = _get_x_credentials()
        assert creds["client_id"] == "test-client-id"
        assert creds["client_secret"] == "test-secret"
        assert creds["refresh_token"] == "test-refresh"

    @patch.dict("os.environ", {}, clear=True)
    @patch("app.x_auth.load_dotenv")
    def test_defaults_to_empty(self, _mock_dotenv):
        creds = _get_x_credentials()
        assert creds["client_id"] == ""
        assert creds["refresh_token"] == ""


class TestTokenCachePath:
    @patch.dict("os.environ", {"KOAN_ROOT": "/tmp/test-koan"})
    def test_returns_instance_path(self):
        path = _get_token_cache_path()
        assert path == Path("/tmp/test-koan/instance/.x-token-cache.json")


class TestPersistedToken:
    def test_returns_none_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
        assert _load_persisted_token() is None

    def test_returns_data_when_expired(self, tmp_path, monkeypatch):
        """Expired tokens are still returned — caller uses the refresh token."""
        monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
        cache_path = tmp_path / "instance" / ".x-token-cache.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "access_token": "old-token",
            "expires_at": time.time() - 100,
            "refresh_token": "old-refresh",
        }))
        data = _load_persisted_token()
        assert data is not None
        assert data["refresh_token"] == "old-refresh"

    def test_returns_valid_token(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
        cache_path = tmp_path / "instance" / ".x-token-cache.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "access_token": "valid-token",
            "expires_at": time.time() + 3600,
            "refresh_token": "refresh",
        }))
        result = _load_persisted_token()
        assert result is not None
        assert result["access_token"] == "valid-token"

    def test_persist_creates_file(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
        (tmp_path / "instance").mkdir()
        _persist_token("tok", time.time() + 3600, "ref")
        cache_path = tmp_path / "instance" / ".x-token-cache.json"
        assert cache_path.exists()
        data = json.loads(cache_path.read_text())
        assert data["access_token"] == "tok"
        assert data["refresh_token"] == "ref"


class TestRefreshAccessToken:
    @patch.dict("os.environ", {"KOAN_ROOT": "/tmp/nonexistent"})
    @patch("app.x_auth.load_dotenv")
    @patch("app.x_auth._get_x_credentials", return_value={
        "client_id": "", "client_secret": "", "refresh_token": "",
    })
    def test_fails_without_client_id(self, _creds, _dotenv):
        ok, msg = refresh_access_token()
        assert ok is False
        assert "CLIENT_ID" in msg

    @patch.dict("os.environ", {"KOAN_ROOT": "/tmp/nonexistent"})
    @patch("app.x_auth.load_dotenv")
    @patch("app.x_auth._get_x_credentials", return_value={
        "client_id": "cid", "client_secret": "", "refresh_token": "",
    })
    def test_fails_without_refresh_token(self, _creds, _dotenv):
        ok, msg = refresh_access_token()
        assert ok is False
        assert "REFRESH_TOKEN" in msg

    def test_uses_memory_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
        from app import x_auth
        x_auth._token_cache = {
            "access_token": "cached-token",
            "expires_at": time.time() + 3600,
        }
        ok, token = refresh_access_token()
        assert ok is True
        assert token == "cached-token"

    def test_uses_disk_cache(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
        cache_path = tmp_path / "instance" / ".x-token-cache.json"
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps({
            "access_token": "disk-token",
            "expires_at": time.time() + 3600,
            "refresh_token": "ref",
        }))
        ok, token = refresh_access_token()
        assert ok is True
        assert token == "disk-token"


class TestGetAuthHeader:
    def test_returns_bearer_header(self, tmp_path, monkeypatch):
        monkeypatch.setenv("KOAN_ROOT", str(tmp_path))
        from app import x_auth
        x_auth._token_cache = {
            "access_token": "my-token",
            "expires_at": time.time() + 3600,
        }
        ok, headers = get_auth_header()
        assert ok is True
        assert headers["Authorization"] == "Bearer my-token"

    @patch.dict("os.environ", {"KOAN_ROOT": "/tmp/nonexistent"})
    @patch("app.x_auth.load_dotenv")
    @patch("app.x_auth._get_x_credentials", return_value={
        "client_id": "", "client_secret": "", "refresh_token": "",
    })
    def test_returns_error_on_failure(self, _creds, _dotenv):
        ok, result = get_auth_header()
        assert ok is False
        assert isinstance(result, str)


class TestIsConfigured:
    @patch("app.x_auth.load_dotenv")
    @patch("app.x_auth._get_x_credentials", return_value={
        "client_id": "cid", "client_secret": "sec", "refresh_token": "ref",
    })
    def test_configured(self, _creds, _dotenv):
        ok, msg = is_configured()
        assert ok is True

    @patch("app.x_auth.load_dotenv")
    @patch("app.x_auth._get_x_credentials", return_value={
        "client_id": "", "client_secret": "", "refresh_token": "",
    })
    def test_not_configured(self, _creds, _dotenv):
        ok, msg = is_configured()
        assert ok is False
        assert "CLIENT_ID" in msg

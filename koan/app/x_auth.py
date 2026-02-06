#!/usr/bin/env python3
"""
Koan -- X (Twitter) OAuth 2.0 authentication

Manages OAuth 2.0 tokens for the X API v2.
Uses refresh tokens (PKCE flow) — no long-lived API secrets.

The initial OAuth 2.0 authorization must be done manually once:
1. Register app at developer.twitter.com
2. Enable OAuth 2.0 with PKCE
3. Authorize and get a refresh token
4. Store as KOAN_X_REFRESH_TOKEN in .env

This module handles token refresh at runtime.

Uses stdlib urllib.request — no extra dependencies.
"""

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple

from app.utils import load_config, load_dotenv


# X API endpoints
TOKEN_URL = "https://api.twitter.com/2/oauth2/token"

# Token cache (in-memory, refreshed as needed)
_token_cache = {
    "access_token": None,
    "expires_at": 0,
}


def _get_x_credentials() -> dict:
    """Get X API credentials from environment variables."""
    load_dotenv()
    return {
        "client_id": os.environ.get("KOAN_X_CLIENT_ID", ""),
        "client_secret": os.environ.get("KOAN_X_CLIENT_SECRET", ""),
        "refresh_token": os.environ.get("KOAN_X_REFRESH_TOKEN", ""),
    }


def _get_token_cache_path() -> Path:
    """Path for persisted token cache (access token + expiry)."""
    koan_root = Path(os.environ.get("KOAN_ROOT", "."))
    return koan_root / "instance" / ".x-token-cache.json"


def _load_persisted_token() -> Optional[dict]:
    """Load cached token from disk. Returns data even if access token expired
    (caller may need the refresh token)."""
    path = _get_token_cache_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _persist_token(access_token: str, expires_at: float, refresh_token: str):
    """Save token to disk for cross-process sharing."""
    path = _get_token_cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "access_token": access_token,
        "expires_at": expires_at,
        "refresh_token": refresh_token,
    }
    # Write atomically (temp file + rename)
    import tempfile
    tmp_fd, tmp_path = tempfile.mkstemp(dir=str(path.parent))
    try:
        os.write(tmp_fd, json.dumps(data).encode())
        os.close(tmp_fd)
        os.rename(tmp_path, str(path))
    except OSError:
        os.close(tmp_fd) if not os.get_inheritable(tmp_fd) else None
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def refresh_access_token() -> Tuple[bool, str]:
    """Refresh the OAuth 2.0 access token using the refresh token.

    Returns:
        (success, access_token_or_error)
    """
    # Check in-memory cache first
    if _token_cache["access_token"] and _token_cache["expires_at"] > time.time() + 60:
        return True, _token_cache["access_token"]

    # Check disk cache (valid access token)
    persisted = _load_persisted_token()
    if persisted and persisted.get("expires_at", 0) > time.time() + 60:
        _token_cache["access_token"] = persisted["access_token"]
        _token_cache["expires_at"] = persisted["expires_at"]
        return True, persisted["access_token"]

    # Need to refresh
    creds = _get_x_credentials()
    if not creds["client_id"]:
        return False, "KOAN_X_CLIENT_ID not configured"
    if not creds["refresh_token"]:
        return False, "KOAN_X_REFRESH_TOKEN not configured"

    # Prefer persisted refresh token (may have been rotated by a previous refresh)
    refresh_token = creds["refresh_token"]
    if persisted and persisted.get("refresh_token"):
        refresh_token = persisted["refresh_token"]

    data = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": creds["client_id"],
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    # Add client authentication if client_secret is available
    if creds["client_secret"]:
        credentials = base64.b64encode(
            f"{creds['client_id']}:{creds['client_secret']}".encode()
        ).decode()
        req.add_header("Authorization", f"Basic {credentials}")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        access_token = result.get("access_token", "")
        expires_in = result.get("expires_in", 7200)
        new_refresh = result.get("refresh_token", refresh_token)

        if not access_token:
            return False, "No access_token in response"

        expires_at = time.time() + expires_in
        _token_cache["access_token"] = access_token
        _token_cache["expires_at"] = expires_at

        # Persist (including rotated refresh token)
        _persist_token(access_token, expires_at, new_refresh)

        return True, access_token

    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        return False, f"Token refresh failed (HTTP {e.code}): {body[:200]}"
    except (urllib.error.URLError, OSError) as e:
        return False, f"Token refresh connection error: {e}"


def get_auth_header() -> Tuple[bool, dict]:
    """Get Authorization header for X API calls.

    Returns:
        (success, headers_dict_or_error_string)
    """
    ok, result = refresh_access_token()
    if not ok:
        return False, result
    return True, {"Authorization": f"Bearer {result}"}


def is_configured() -> Tuple[bool, str]:
    """Check if X API credentials are configured.

    Returns:
        (configured, message)
    """
    creds = _get_x_credentials()
    if not creds["client_id"]:
        return False, "KOAN_X_CLIENT_ID not set"
    if not creds["refresh_token"]:
        return False, "KOAN_X_REFRESH_TOKEN not set"
    return True, "X API credentials configured"


def reset_token_cache():
    """Reset in-memory token cache. For testing."""
    global _token_cache
    _token_cache = {"access_token": None, "expires_at": 0}

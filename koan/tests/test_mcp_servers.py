"""Tests for mcp_servers.py — MCP server discovery, listing, and integration."""

from unittest.mock import patch, MagicMock

import pytest

from app.mcp_servers import (
    list_mcp_servers,
    _parse_mcp_list,
    get_mcp_capabilities,
    get_mcp_server_names,
    format_mcp_list,
    build_mcp_flags,
    get_mcp_prompt_context,
)


# ---------------------------------------------------------------------------
# _parse_mcp_list
# ---------------------------------------------------------------------------

class TestParseMcpList:
    """Test parsing of `claude mcp list` output."""

    def test_empty_output(self):
        assert _parse_mcp_list("") == []

    def test_single_server_dash_format(self):
        output = "- gmail\n  Type: stdio\n  Status: connected"
        result = _parse_mcp_list(output)
        assert len(result) == 1
        assert result[0]["name"] == "gmail"
        assert result[0]["type"] == "stdio"
        assert result[0]["status"] == "connected"

    def test_multiple_servers(self):
        output = (
            "- gmail\n"
            "  Type: stdio\n"
            "  Status: connected\n"
            "\n"
            "- calendar\n"
            "  Type: http\n"
            "  Status: disconnected\n"
        )
        result = _parse_mcp_list(output)
        assert len(result) == 2
        assert result[0]["name"] == "gmail"
        assert result[1]["name"] == "calendar"
        assert result[1]["type"] == "http"

    def test_server_with_command(self):
        output = "- my-server\n  Type: stdio\n  Command: npx my-mcp\n  Status: connected"
        result = _parse_mcp_list(output)
        assert len(result) == 1
        assert result[0]["command"] == "npx my-mcp"

    def test_transport_alias(self):
        output = "- sentry\n  Transport: http\n  Status: connected"
        result = _parse_mcp_list(output)
        assert result[0]["type"] == "http"

    def test_name_with_colon_value(self):
        output = "- name: gmail\n  Type: stdio"
        result = _parse_mcp_list(output)
        assert len(result) == 1
        assert result[0]["name"] == "gmail"


# ---------------------------------------------------------------------------
# list_mcp_servers
# ---------------------------------------------------------------------------

class TestListMcpServers:
    """Test MCP server discovery via Claude CLI."""

    @patch("app.mcp_servers.subprocess.run")
    def test_no_servers_configured(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="No MCP servers configured. Use `claude mcp add` to add a server.",
            returncode=0,
        )
        assert list_mcp_servers() == []

    @patch("app.mcp_servers.subprocess.run")
    def test_servers_found(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="- gmail\n  Type: stdio\n  Status: connected\n",
            returncode=0,
        )
        result = list_mcp_servers()
        assert len(result) == 1
        assert result[0]["name"] == "gmail"

    @patch("app.mcp_servers.subprocess.run")
    def test_empty_output(self, mock_run):
        mock_run.return_value = MagicMock(stdout="", returncode=0)
        assert list_mcp_servers() == []

    @patch("app.mcp_servers.subprocess.run")
    def test_timeout_returns_empty(self, mock_run):
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="claude", timeout=10)
        assert list_mcp_servers() == []

    @patch("app.mcp_servers.subprocess.run")
    def test_file_not_found_returns_empty(self, mock_run):
        mock_run.side_effect = FileNotFoundError()
        assert list_mcp_servers() == []


# ---------------------------------------------------------------------------
# get_mcp_capabilities
# ---------------------------------------------------------------------------

class TestGetMcpCapabilities:
    """Test capability descriptions from config.yaml."""

    @patch("app.mcp_servers.load_config")
    def test_no_mcp_config(self, mock_config):
        mock_config.return_value = {}
        assert get_mcp_capabilities() == {}

    @patch("app.mcp_servers.load_config")
    def test_with_capabilities(self, mock_config):
        mock_config.return_value = {
            "mcp": {
                "capabilities": {
                    "gmail": "Read and send emails",
                    "calendar": "Manage calendar events",
                }
            }
        }
        caps = get_mcp_capabilities()
        assert caps["gmail"] == "Read and send emails"
        assert caps["calendar"] == "Manage calendar events"

    @patch("app.mcp_servers.load_config")
    def test_empty_capabilities(self, mock_config):
        mock_config.return_value = {"mcp": {"capabilities": {}}}
        assert get_mcp_capabilities() == {}


# ---------------------------------------------------------------------------
# get_mcp_server_names
# ---------------------------------------------------------------------------

class TestGetMcpServerNames:
    """Test server name extraction."""

    @patch("app.mcp_servers.list_mcp_servers")
    def test_returns_sorted_names(self, mock_list):
        mock_list.return_value = [
            {"name": "calendar", "type": "http"},
            {"name": "gmail", "type": "stdio"},
        ]
        names = get_mcp_server_names()
        assert names == ["calendar", "gmail"]

    @patch("app.mcp_servers.list_mcp_servers")
    def test_empty_list(self, mock_list):
        mock_list.return_value = []
        assert get_mcp_server_names() == []

    @patch("app.mcp_servers.list_mcp_servers")
    def test_filters_empty_names(self, mock_list):
        mock_list.return_value = [
            {"name": "gmail"},
            {"name": ""},
            {"type": "stdio"},  # No name key
        ]
        names = get_mcp_server_names()
        assert names == ["gmail"]


# ---------------------------------------------------------------------------
# format_mcp_list
# ---------------------------------------------------------------------------

class TestFormatMcpList:
    """Test MCP list formatting for Telegram."""

    def test_no_servers(self):
        result = format_mcp_list([], {})
        assert "Aucun serveur MCP" in result
        assert "claude mcp add" in result

    def test_with_servers(self):
        servers = [
            {"name": "gmail", "type": "stdio", "status": "connected"},
        ]
        result = format_mcp_list(servers, {})
        assert "gmail" in result
        assert "stdio" in result
        assert "connected" in result

    def test_with_capabilities(self):
        servers = [{"name": "gmail", "type": "stdio"}]
        caps = {"gmail": "Read and send emails"}
        result = format_mcp_list(servers, caps)
        assert "Read and send emails" in result

    def test_multiple_servers(self):
        servers = [
            {"name": "gmail", "type": "stdio"},
            {"name": "calendar", "type": "http"},
        ]
        result = format_mcp_list(servers, {})
        assert "gmail" in result
        assert "calendar" in result
        assert "disponibles" in result

    def test_server_no_type_no_status(self):
        servers = [{"name": "minimal"}]
        result = format_mcp_list(servers, {})
        assert "minimal" in result


# ---------------------------------------------------------------------------
# build_mcp_flags
# ---------------------------------------------------------------------------

class TestBuildMcpFlags:
    """Test MCP CLI flag building."""

    @patch("app.mcp_servers.load_config")
    def test_no_mcp_config(self, mock_config):
        mock_config.return_value = {}
        assert build_mcp_flags() == []

    @patch("app.mcp_servers.load_config")
    def test_empty_configs(self, mock_config):
        mock_config.return_value = {"mcp": {"configs": []}}
        assert build_mcp_flags() == []

    @patch("app.mcp_servers.load_config")
    def test_with_config_file(self, mock_config):
        mock_config.return_value = {
            "mcp": {"configs": ["/path/to/mcp.json"]}
        }
        flags = build_mcp_flags()
        assert flags == ["--mcp-config", "/path/to/mcp.json"]

    @patch("app.mcp_servers.load_config")
    def test_with_multiple_configs(self, mock_config):
        mock_config.return_value = {
            "mcp": {"configs": ["/a.json", "/b.json"]}
        }
        flags = build_mcp_flags()
        assert flags == ["--mcp-config", "/a.json", "/b.json"]


# ---------------------------------------------------------------------------
# get_mcp_prompt_context
# ---------------------------------------------------------------------------

class TestGetMcpPromptContext:
    """Test prompt context generation for MCP."""

    @patch("app.mcp_servers.get_mcp_capabilities")
    @patch("app.mcp_servers.list_mcp_servers")
    def test_no_servers(self, mock_list, mock_caps):
        mock_list.return_value = []
        assert get_mcp_prompt_context() == ""

    @patch("app.mcp_servers.get_mcp_capabilities")
    @patch("app.mcp_servers.list_mcp_servers")
    def test_with_servers_and_caps(self, mock_list, mock_caps):
        mock_list.return_value = [
            {"name": "gmail", "type": "stdio"},
            {"name": "calendar", "type": "http"},
        ]
        mock_caps.return_value = {
            "gmail": "Read and send emails",
            "calendar": "Manage calendar events",
        }
        context = get_mcp_prompt_context()
        assert "Available MCP servers" in context
        assert "gmail: Read and send emails" in context
        assert "calendar: Manage calendar events" in context

    @patch("app.mcp_servers.get_mcp_capabilities")
    @patch("app.mcp_servers.list_mcp_servers")
    def test_with_servers_no_caps(self, mock_list, mock_caps):
        mock_list.return_value = [{"name": "slack"}]
        mock_caps.return_value = {}
        context = get_mcp_prompt_context()
        assert "slack" in context
        assert "Available MCP servers" in context

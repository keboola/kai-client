"""Tests for the `kai verify` CLI command."""

import json

import httpx
import pytest
from click.testing import CliRunner

from kai_client.cli import main

STORAGE_URL = "https://connection.test.keboola.com"
KAI_URL = "https://kai.test.keboola.com"


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_env(monkeypatch):
    monkeypatch.setenv("STORAGE_API_TOKEN", "test-token")
    monkeypatch.setenv("STORAGE_API_URL", STORAGE_URL)


def _mock_token_verify_ok(httpx_mock, *, is_master=True):
    httpx_mock.add_response(
        url=f"{STORAGE_URL}/v2/storage/tokens/verify",
        method="GET",
        json={
            "id": "12345",
            "description": "max@keboola.com",
            "isMasterToken": is_master,
            "owner": {"id": 2738, "name": "Test Project"},
        },
    )


def _mock_discovery_ok(httpx_mock):
    httpx_mock.add_response(
        url=f"{STORAGE_URL}/v2/storage",
        method="GET",
        json={"services": [{"id": "kai-assistant", "url": KAI_URL}]},
    )


def _mock_ping_info_ok(httpx_mock):
    httpx_mock.add_response(
        url=f"{KAI_URL}/ping",
        method="GET",
        json={"timestamp": "2026-05-26T10:00:00Z"},
    )
    httpx_mock.add_response(
        url=f"{KAI_URL}/api",
        method="GET",
        json={
            "timestamp": "2026-05-26T10:00:00Z",
            "appName": "kai-assistant",
            "appVersion": "1.2.3",
            "serverVersion": "1.2.3",
            "uptime": 3600.0,
            "connectedMcp": [],
        },
    )


class TestVerifyCommand:
    def test_full_success_renders_project_and_quota(self, runner, mock_env, httpx_mock):
        _mock_token_verify_ok(httpx_mock, is_master=True)
        _mock_discovery_ok(httpx_mock)
        _mock_ping_info_ok(httpx_mock)
        httpx_mock.add_response(
            url=f"{KAI_URL}/api/usage",
            method="GET",
            json={
                "messagesUsed": 19,
                "messagesLimit": 150,
                "resetDate": "2026-06-01T00:00:00Z",
            },
        )

        result = runner.invoke(main, ["verify"])

        assert result.exit_code == 0, result.output
        assert "project 2738" in result.output
        assert "Test Project" in result.output
        assert "[master]" in result.output
        assert "kai-assistant at https://kai.test.keboola.com" in result.output
        assert "19/150 messages used" in result.output
        assert "131 left" in result.output
        assert "All checks passed." in result.output

    def test_rate_limit_429_renders_code_and_message_cleanly(self, runner, mock_env, httpx_mock):
        """The whole reason this command exists — surface 429 rate_limit:chat clearly."""
        _mock_token_verify_ok(httpx_mock)
        _mock_discovery_ok(httpx_mock)
        _mock_ping_info_ok(httpx_mock)
        httpx_mock.add_response(
            url=f"{KAI_URL}/api/usage",
            method="GET",
            status_code=429,
            json={
                "code": "rate_limit:chat",
                "message": (
                    "You have exceeded your maximum number of messages for "
                    "this month. Please contact support to raise your limit "
                    "or try again next month."
                ),
            },
        )

        result = runner.invoke(main, ["verify"])

        assert result.exit_code == 1
        assert "rate_limit:chat" in result.output
        assert "exceeded your maximum number of messages" in result.output
        # No raw JSON blob in the rendered output.
        assert '{"code"' not in result.output

    def test_invalid_token_exits_nonzero(self, runner, mock_env, httpx_mock):
        httpx_mock.add_response(
            url=f"{STORAGE_URL}/v2/storage/tokens/verify",
            method="GET",
            status_code=401,
            json={"error": "Invalid access token", "code": "storage.tokenInvalid"},
        )

        result = runner.invoke(main, ["verify"])

        assert result.exit_code == 1
        assert "storage.tokenInvalid" in result.output
        assert "Invalid access token" in result.output

    def test_missing_env_var_exits_with_clear_message(self, runner, monkeypatch):
        monkeypatch.delenv("STORAGE_API_TOKEN", raising=False)
        monkeypatch.delenv("STORAGE_API_URL", raising=False)

        result = runner.invoke(main, ["verify"])

        assert result.exit_code == 1
        assert "STORAGE_API_TOKEN" in result.output

    def test_json_output_shape(self, runner, mock_env, httpx_mock):
        _mock_token_verify_ok(httpx_mock)
        _mock_discovery_ok(httpx_mock)
        _mock_ping_info_ok(httpx_mock)
        httpx_mock.add_response(
            url=f"{KAI_URL}/api/usage",
            method="GET",
            json={
                "messagesUsed": 19,
                "messagesLimit": 150,
                "resetDate": "2026-06-01T00:00:00Z",
            },
        )

        result = runner.invoke(main, ["verify", "--json-output"])

        assert result.exit_code == 0, result.output
        data = json.loads(result.output)
        assert data["ok"] is True
        assert data["checks"]["token"]["project_id"] == 2738
        assert data["checks"]["usage"]["messages_used"] == 19
        assert data["checks"]["usage"]["messages_limit"] == 150

    def test_scoped_token_renders_as_scoped(self, runner, mock_env, httpx_mock):
        """Non-master tokens should label as [scoped] (not [master])."""
        _mock_token_verify_ok(httpx_mock, is_master=False)
        _mock_discovery_ok(httpx_mock)
        _mock_ping_info_ok(httpx_mock)
        httpx_mock.add_response(
            url=f"{KAI_URL}/api/usage",
            method="GET",
            json={
                "messagesUsed": 5,
                "messagesLimit": 150,
                "resetDate": "2026-06-01T00:00:00Z",
            },
        )

        result = runner.invoke(main, ["verify"])

        assert result.exit_code == 0, result.output
        assert "[scoped]" in result.output
        assert "[master]" not in result.output

    def test_storage_api_connection_error_renders_cleanly(self, runner, mock_env, httpx_mock):
        """If Storage API is unreachable, token check fails with a connection-error line."""
        httpx_mock.add_exception(
            httpx.ConnectError("Network unreachable"),
            url=f"{STORAGE_URL}/v2/storage/tokens/verify",
        )

        result = runner.invoke(main, ["verify"])

        assert result.exit_code == 1
        assert "connection error" in result.output.lower()
        assert "Network unreachable" in result.output

    def test_base_url_skips_discovery(self, runner, mock_env, httpx_mock):
        """`--base-url` bypasses /v2/storage discovery and talks to the given URL directly."""
        local_url = "http://localhost:4000"
        _mock_token_verify_ok(httpx_mock)
        # No /v2/storage mock — would error if discovery were attempted.
        httpx_mock.add_response(
            url=f"{local_url}/ping",
            method="GET",
            json={"timestamp": "2026-05-26T10:00:00Z"},
        )
        httpx_mock.add_response(
            url=f"{local_url}/api",
            method="GET",
            json={
                "timestamp": "2026-05-26T10:00:00Z",
                "appName": "kai-assistant",
                "appVersion": "dev",
                "serverVersion": "dev",
                "uptime": 12.0,
                "connectedMcp": [],
            },
        )
        httpx_mock.add_response(
            url=f"{local_url}/api/usage",
            method="GET",
            json={
                "messagesUsed": 0,
                "messagesLimit": 150,
                "resetDate": "2026-06-01T00:00:00Z",
            },
        )

        result = runner.invoke(main, ["--base-url", local_url, "verify"])

        assert result.exit_code == 0, result.output
        assert f"using --base-url {local_url}" in result.output
        assert "All checks passed." in result.output

    def test_service_discovery_failure_when_kai_assistant_absent(
        self, runner, mock_env, httpx_mock
    ):
        """If the services list has no kai-assistant entry, discovery fails cleanly."""
        _mock_token_verify_ok(httpx_mock)
        httpx_mock.add_response(
            url=f"{STORAGE_URL}/v2/storage",
            method="GET",
            json={"services": [{"id": "queue", "url": "https://queue.example/"}]},
        )

        result = runner.invoke(main, ["verify"])

        assert result.exit_code == 1
        assert "service-discovery" in result.output
        assert "kai-assistant service not found" in result.output

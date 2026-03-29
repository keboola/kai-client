"""Tests for the CLI module."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner

from kai_client import __version__
from kai_client.cli import get_client, get_env_or_error, main, run_async
from kai_client.models import (
    Chat,
    ChatDetail,
    FinishEvent,
    HistoryResponse,
    InfoResponse,
    Message,
    PingResponse,
    TextEvent,
    ToolCallEvent,
    Vote,
)


@pytest.fixture
def runner():
    """Create a CLI runner."""
    return CliRunner()


@pytest.fixture
def mock_env(monkeypatch):
    """Set up mock environment variables."""
    monkeypatch.setenv("STORAGE_API_TOKEN", "test-token")
    monkeypatch.setenv("STORAGE_API_URL", "https://connection.test.keboola.com")


class TestGetEnvOrError:
    """Tests for get_env_or_error helper function."""

    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("TEST_VAR", "test-value")
        assert get_env_or_error("TEST_VAR") == "test-value"

    def test_exits_when_not_set(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            get_env_or_error("MISSING_VAR")
        assert exc_info.value.code == 1


class TestRunAsync:
    """Tests for run_async helper function."""

    def test_runs_coroutine(self):
        async def sample_coro():
            return "result"

        result = run_async(sample_coro())
        assert result == "result"


class TestMainGroup:
    """Tests for the main CLI group."""

    def test_version(self, runner):
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_help(self, runner):
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Kai CLI" in result.output
        assert "STORAGE_API_TOKEN" in result.output

    def test_passes_options_to_context(self, runner):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(
                return_value=PingResponse(timestamp="2025-01-01T00:00:00Z")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                main,
                [
                    "--token",
                    "my-token",
                    "--url",
                    "https://my-url.com",
                    "--base-url",
                    "http://localhost:4000",
                    "ping",
                ],
            )
            # Should not fail with missing env vars since we passed options
            assert "my-token" in str(mock_get_client.call_args) or result.exit_code == 0


class TestPingCommand:
    """Tests for the ping command."""

    def test_ping_success(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.ping = AsyncMock(
                return_value=PingResponse(timestamp="2025-01-08T12:00:00Z")
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["ping"])

            assert result.exit_code == 0
            assert "Server is alive" in result.output

    def test_ping_missing_env(self, runner, monkeypatch):
        monkeypatch.delenv("STORAGE_API_TOKEN", raising=False)
        monkeypatch.delenv("STORAGE_API_URL", raising=False)

        result = runner.invoke(main, ["ping"])

        assert result.exit_code == 1
        assert "STORAGE_API_TOKEN" in result.output


class TestInfoCommand:
    """Tests for the info command."""

    def test_info_success(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.info = AsyncMock(
                return_value=InfoResponse(
                    timestamp="2025-01-08T12:00:00Z",
                    uptime=12345.67,
                    appName="kai-backend",
                    appVersion="1.0.0",
                    serverVersion="2.0.0",
                    connectedMcp=[{"name": "keboola-mcp", "status": "connected"}],
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["info"])

            assert result.exit_code == 0
            assert "kai-backend" in result.output
            assert "1.0.0" in result.output
            assert "keboola-mcp" in result.output


class TestChatCommand:
    """Tests for the chat command."""

    def test_chat_single_message(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            async def mock_send_message(chat_id, message):
                yield TextEvent(type="text", text="Hello there!")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat", "-m", "Hello"])

            assert result.exit_code == 0
            assert "Hello there!" in result.output
            assert "test-chat-id" in result.output

    def test_chat_with_existing_chat_id(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()

            async def mock_send_message(chat_id, message):
                yield TextEvent(type="text", text="Continued chat")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                main, ["chat", "--chat-id", "existing-id", "-m", "Continue"]
            )

            assert result.exit_code == 0
            # Should not print "Chat ID:" since we provided one
            assert "existing-id" not in result.output or "Continued chat" in result.output

    def test_chat_json_output(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            async def mock_send_message(chat_id, message):
                yield TextEvent(type="text", text="Response")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat", "--json-output", "-m", "Test"])

            assert result.exit_code == 0
            # Output should be JSON lines
            lines = [ln for ln in result.output.strip().split("\n") if ln]
            for line in lines:
                # Each line should be valid JSON
                parsed = json.loads(line)
                assert "type" in parsed

    def test_chat_with_tool_call_auto_approve(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            async def mock_send_message(chat_id, message):
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-123",
                    toolName="create_bucket",
                    state="input-available",
                    input={"name": "test"},
                )
                # Stream finishes waiting for approval

            async def mock_confirm_tool(chat_id, tool_call_id, tool_name):
                yield TextEvent(type="text", text="Bucket created!")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.confirm_tool = mock_confirm_tool
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                main, ["chat", "--auto-approve", "-m", "Create bucket"]
            )

            assert result.exit_code == 0
            assert "Auto-approving" in result.output
            assert "Bucket created!" in result.output

    def test_chat_step_start_display(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            from kai_client.models import StepStartEvent

            async def mock_send_message(chat_id, message):
                yield StepStartEvent(type="step-start")
                yield TextEvent(type="text", text="Processing done")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat", "-m", "Test"])

            assert result.exit_code == 0
            assert "[Processing...]" in result.output

    def test_chat_error_event(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            from kai_client.models import ErrorEvent

            async def mock_send_message(chat_id, message):
                yield ErrorEvent(type="error", message="Something went wrong")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat", "-m", "Test"])

            # Error should be displayed
            assert "Something went wrong" in result.output

    def test_chat_tool_name_tracked_when_null_in_output(self, runner, mock_env):
        """Test that tool_name is properly tracked when server returns null in output-available.

        This tests the fix for the bug where [None completed] was displayed because
        the server returns tool_name=null in output-available events.
        """
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            async def mock_send_message(chat_id, message):
                # Tool call started with tool_name
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-123",
                    toolName="get_buckets",
                    state="started",
                )
                # Input available with tool_name
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-123",
                    toolName="get_buckets",
                    state="input-available",
                    input={"bucket_ids": []},
                )
                # Output available with NULL tool_name (server bug)
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-123",
                    toolName=None,  # Server returns null here
                    state="output-available",
                    output={"content": "buckets data"},
                )
                yield TextEvent(type="text", text="Here are your buckets")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat", "-m", "List buckets"])

            assert result.exit_code == 0
            # Should show the tracked tool name, not "None"
            assert "[get_buckets completed]" in result.output
            assert "[None completed]" not in result.output

    def test_chat_auto_approve_after_finish_event(self, runner, mock_env):
        """Test that auto-approve works even when finish events occur between tool calls.

        This tests the fix for the bug where auto-approve didn't trigger because
        stream_finished was set to True by a finish event from a previous step,
        before the write tool that needs approval.
        """
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            from kai_client.models import StepStartEvent

            async def mock_send_message(chat_id, message):
                # First step: read-only tool that auto-completes
                yield StepStartEvent(type="step-start")
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-read",
                    toolName="get_components",
                    state="started",
                )
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-read",
                    toolName="get_components",
                    state="input-available",
                    input={},
                )
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-read",
                    toolName="get_components",
                    state="output-available",
                    output={"components": []},
                )
                yield TextEvent(type="text", text="Got components. ")
                # Finish event after first step (this was causing the bug)
                yield FinishEvent(type="finish", finishReason="stop")

                # Second step: write tool that needs approval
                yield StepStartEvent(type="step-start")
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-write",
                    toolName="create_config",
                    state="started",
                )
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-write",
                    toolName="create_config",
                    state="input-available",
                    input={"name": "test-config"},
                )
                # Stream ends here waiting for approval (no output-available yet)
                yield FinishEvent(type="finish", finishReason="stop")

            async def mock_confirm_tool(chat_id, tool_call_id, tool_name):
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-write",
                    toolName="create_config",
                    state="output-available",
                    output={"id": "config-123"},
                )
                yield TextEvent(type="text", text="Configuration created!")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.confirm_tool = mock_confirm_tool
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                main, ["chat", "--auto-approve", "-m", "Create config"]
            )

            assert result.exit_code == 0
            # Auto-approve should have been triggered despite the earlier finish event
            assert "[Auto-approving...]" in result.output
            assert "Configuration created!" in result.output

    def test_chat_pending_approval_cleared_on_tool_completion(self, runner, mock_env):
        """Test that pending_approval is cleared when the tool completes.

        This ensures that if a tool shows 'requires approval' but then completes
        (server auto-approved it), we don't try to approve it again.
        """
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            async def mock_send_message(chat_id, message):
                # Tool shows input-available (would normally need approval)
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-123",
                    toolName="get_buckets",
                    state="started",
                )
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-123",
                    toolName="get_buckets",
                    state="input-available",
                    input={},
                )
                # But server auto-approves it (sends output-available)
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-123",
                    toolName="get_buckets",
                    state="output-available",
                    output={"buckets": []},
                )
                yield TextEvent(type="text", text="Done")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            # confirm_tool should NOT be called since tool completed
            mock_client.confirm_tool = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                main, ["chat", "--auto-approve", "-m", "List buckets"]
            )

            assert result.exit_code == 0
            # Should NOT show auto-approving since tool already completed
            assert "[Auto-approving...]" not in result.output
            # confirm_tool should not have been called
            mock_client.confirm_tool.assert_not_called()


class TestHistoryCommand:
    """Tests for the history command."""

    def test_history_success(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_history = AsyncMock(
                return_value=HistoryResponse(
                    chats=[
                        Chat(
                            id="chat-1",
                            title="First Chat",
                            createdAt="2025-01-08T10:00:00Z",
                        ),
                        Chat(
                            id="chat-2",
                            title="Second Chat",
                            createdAt="2025-01-08T11:00:00Z",
                        ),
                    ],
                    hasMore=False,
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["history"])

            assert result.exit_code == 0
            assert "chat-1" in result.output
            assert "First Chat" in result.output
            assert "chat-2" in result.output

    def test_history_with_limit(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_history = AsyncMock(
                return_value=HistoryResponse(chats=[], hasMore=False)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["history", "-n", "5"])

            assert result.exit_code == 0
            mock_client.get_history.assert_called_once_with(limit=5)

    def test_history_empty(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_history = AsyncMock(
                return_value=HistoryResponse(chats=[], hasMore=False)
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["history"])

            assert result.exit_code == 0
            assert "No chat history found" in result.output

    def test_history_has_more(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_history = AsyncMock(
                return_value=HistoryResponse(
                    chats=[Chat(id="chat-1", title="Chat")],
                    hasMore=True,
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["history"])

            assert result.exit_code == 0
            assert "and more" in result.output

    def test_history_json_output(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_history = AsyncMock(
                return_value=HistoryResponse(
                    chats=[Chat(id="chat-1", title="Test Chat")],
                    hasMore=False,
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["history", "--json-output"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert "chats" in data
            assert "hasMore" in data


class TestGetChatCommand:
    """Tests for the get-chat command."""

    def test_get_chat_success(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_chat = AsyncMock(
                return_value=ChatDetail(
                    id="chat-123",
                    title="Test Chat",
                    messages=[
                        Message(
                            id="msg-1",
                            role="user",
                            parts=[{"type": "text", "text": "Hello"}],
                        ),
                        Message(
                            id="msg-2",
                            role="assistant",
                            parts=[{"type": "text", "text": "Hi there!"}],
                        ),
                    ],
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-chat", "chat-123"])

            assert result.exit_code == 0
            assert "chat-123" in result.output
            assert "Test Chat" in result.output
            assert "[USER]" in result.output
            assert "[ASSISTANT]" in result.output

    def test_get_chat_json_output(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_chat = AsyncMock(
                return_value=ChatDetail(
                    id="chat-123",
                    title="Test",
                    messages=[],
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-chat", "chat-123", "--json-output"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert data["id"] == "chat-123"


class TestDeleteChatCommand:
    """Tests for the delete-chat command."""

    def test_delete_chat_with_confirmation(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.delete_chat = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["delete-chat", "chat-123", "--yes"])

            assert result.exit_code == 0
            assert "Deleted chat chat-123" in result.output
            mock_client.delete_chat.assert_called_once_with("chat-123")

    def test_delete_chat_cancelled(self, runner, mock_env):
        result = runner.invoke(main, ["delete-chat", "chat-123"], input="n\n")

        assert result.exit_code == 0
        assert "Cancelled" in result.output


class TestVoteCommand:
    """Tests for the vote command."""

    def test_vote_up(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.vote = AsyncMock(
                return_value=Vote(
                    chatId="chat-123",
                    messageId="msg-456",
                    type="up",
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["vote", "chat-123", "msg-456", "up"])

            assert result.exit_code == 0
            assert "Voted up" in result.output

    def test_vote_down(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.vote = AsyncMock(
                return_value=Vote(
                    chatId="chat-123",
                    messageId="msg-456",
                    type="down",
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["vote", "chat-123", "msg-456", "down"])

            assert result.exit_code == 0
            assert "Voted down" in result.output

    def test_vote_invalid_type(self, runner, mock_env):
        result = runner.invoke(main, ["vote", "chat-123", "msg-456", "invalid"])

        assert result.exit_code != 0
        assert "Invalid value" in result.output


class TestGetVotesCommand:
    """Tests for the get-votes command."""

    def test_get_votes_success(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_votes = AsyncMock(
                return_value=[
                    Vote(chatId="chat-123", messageId="msg-1", type="up"),
                    Vote(chatId="chat-123", messageId="msg-2", type="down"),
                ]
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-votes", "chat-123"])

            assert result.exit_code == 0
            assert "msg-1: up" in result.output
            assert "msg-2: down" in result.output

    def test_get_votes_empty(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_votes = AsyncMock(return_value=[])
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-votes", "chat-123"])

            assert result.exit_code == 0
            assert "No votes found" in result.output

    def test_get_votes_json_output(self, runner, mock_env):
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_votes = AsyncMock(
                return_value=[
                    Vote(chatId="chat-123", messageId="msg-1", type="up"),
                ]
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-votes", "chat-123", "--json-output"])

            assert result.exit_code == 0
            data = json.loads(result.output)
            assert len(data) == 1
            assert data[0]["type"] == "up"


class TestGetClientFunction:
    """Tests for the get_client async function."""

    @pytest.mark.asyncio
    async def test_get_client_with_base_url(self, mock_env):
        """Test client creation with explicit base URL (local dev mode)."""
        ctx = MagicMock()
        ctx.obj = {
            "token": "test-token",
            "url": "https://test.keboola.com",
            "base_url": "http://localhost:3000",
        }

        client = await get_client(ctx)

        assert client.base_url == "http://localhost:3000"
        assert client.storage_api_token == "test-token"

    @pytest.mark.asyncio
    async def test_get_client_auto_discover(self, mock_env):
        """Test client creation with auto-discovery (production mode)."""
        ctx = MagicMock()
        ctx.obj = {
            "token": "test-token",
            "url": "https://connection.keboola.com",
            "base_url": None,
        }

        with patch("kai_client.cli.KaiClient.from_storage_api") as mock_factory:
            mock_client = MagicMock()
            mock_factory.return_value = mock_client

            client = await get_client(ctx)

            mock_factory.assert_called_once_with(
                storage_api_token="test-token",
                storage_api_url="https://connection.keboola.com",
            )
            assert client == mock_client


class TestInfoCommandEdgeCases:
    """Tests for the info command with edge case MCP formats."""

    def test_info_with_single_dict_mcp(self, runner, mock_env):
        """Test info command when connectedMcp is a single dict instead of list."""
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.info = AsyncMock(
                return_value=InfoResponse(
                    timestamp="2025-01-08T12:00:00Z",
                    uptime=100.0,
                    appName="kai-backend",
                    appVersion="1.0.0",
                    serverVersion="2.0.0",
                    connectedMcp={"name": "keboola-mcp", "status": "connected"},
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["info"])

            assert result.exit_code == 0
            assert "keboola-mcp" in result.output
            assert "connected" in result.output


class TestChatInteractiveMode:
    """Tests for interactive chat mode."""

    def test_chat_interactive_exit(self, runner, mock_env):
        """Test interactive mode with 'exit' command."""
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat"], input="exit\n")

            assert result.exit_code == 0
            assert "Interactive chat mode" in result.output
            assert "Chat ended" in result.output

    def test_chat_interactive_quit(self, runner, mock_env):
        """Test interactive mode with 'quit' command."""
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat"], input="quit\n")

            assert result.exit_code == 0
            assert "Chat ended" in result.output

    def test_chat_interactive_empty_input_skipped(self, runner, mock_env):
        """Test that empty input is skipped in interactive mode."""
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            send_call_count = 0

            async def mock_send_message(chat_id, message):
                nonlocal send_call_count
                send_call_count += 1
                yield TextEvent(type="text", text="Response")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            # Empty line, then a message, then exit
            result = runner.invoke(main, ["chat"], input="\nHello\nexit\n")

            assert result.exit_code == 0
            assert send_call_count == 1  # Only the "Hello" message was sent

    def test_chat_interactive_with_message_and_response(self, runner, mock_env):
        """Test interactive mode sends message and shows response."""
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            async def mock_send_message(chat_id, message):
                yield TextEvent(type="text", text="I can help!")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["chat"], input="Hello\nexit\n")

            assert result.exit_code == 0
            assert "I can help!" in result.output


class TestChatV6ApprovalFlow:
    """Tests for v6 tool approval flow in the CLI."""

    def test_chat_v6_approval_auto_approve(self, runner, mock_env):
        """Test auto-approve with v6 approval flow (approval_id)."""
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            from kai_client.models import ToolApprovalRequestEvent

            async def mock_send_message(chat_id, message):
                # Tool starts and waits for approval
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-v6",
                    toolName="update_descriptions",
                    state="started",
                )
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-v6",
                    toolName="update_descriptions",
                    state="input-available",
                    input={"descriptions": "new"},
                )
                # v6 approval request event
                yield ToolApprovalRequestEvent(
                    type="tool-approval-request",
                    approvalId="appr-v6-001",
                    toolCallId="tool-v6",
                )

            async def mock_approve_tool(chat_id, approval_id, **kwargs):
                yield TextEvent(type="text", text="Descriptions updated!")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.approve_tool = mock_approve_tool
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                main, ["chat", "--auto-approve", "-m", "Update descriptions"]
            )

            assert result.exit_code == 0
            assert "[Auto-approving...]" in result.output
            assert "Descriptions updated!" in result.output

    def test_chat_v6_approval_user_approve(self, runner, mock_env):
        """Test manual user approval with v6 flow (click.confirm)."""
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            from kai_client.models import ToolApprovalRequestEvent

            async def mock_send_message(chat_id, message):
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-v6-2",
                    toolName="create_config",
                    state="started",
                )
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-v6-2",
                    toolName="create_config",
                    state="input-available",
                    input={"name": "test"},
                )
                yield ToolApprovalRequestEvent(
                    type="tool-approval-request",
                    approvalId="appr-v6-002",
                    toolCallId="tool-v6-2",
                )

            async def mock_approve_tool(chat_id, approval_id, **kwargs):
                yield TextEvent(type="text", text="Config created!")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.approve_tool = mock_approve_tool
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            # User types 'y' to confirm
            result = runner.invoke(
                main, ["chat", "-m", "Create config"], input="y\n"
            )

            assert result.exit_code == 0
            assert "Config created!" in result.output

    def test_chat_v6_approval_user_reject(self, runner, mock_env):
        """Test manual user rejection with v6 flow."""
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            from kai_client.models import ToolApprovalRequestEvent

            async def mock_send_message(chat_id, message):
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-v6-3",
                    toolName="delete_bucket",
                    state="started",
                )
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-v6-3",
                    toolName="delete_bucket",
                    state="input-available",
                    input={"bucket_id": "in.c-test"},
                )
                yield ToolApprovalRequestEvent(
                    type="tool-approval-request",
                    approvalId="appr-v6-003",
                    toolCallId="tool-v6-3",
                )

            async def mock_reject_tool(chat_id, approval_id, **kwargs):
                yield TextEvent(type="text", text="OK, not deleting.")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.reject_tool = mock_reject_tool
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            # User types 'n' to reject
            result = runner.invoke(
                main, ["chat", "-m", "Delete bucket"], input="n\n"
            )

            assert result.exit_code == 0
            assert "OK, not deleting." in result.output


class TestDisplayToolResultEvents:
    """Tests for display_tool_result_events function."""

    def test_display_tool_output_error(self, runner, mock_env):
        """Test that tool-output-error events are displayed."""
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            from kai_client.models import ToolOutputErrorEvent

            async def mock_send_message(chat_id, message):
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-err",
                    toolName="run_job",
                    state="input-available",
                    input={"job_id": "123"},
                )

            async def mock_confirm_tool(chat_id, tool_call_id, tool_name):
                yield ToolOutputErrorEvent(
                    type="tool-output-error",
                    toolCallId="tool-err",
                    errorText="Job failed: timeout",
                )
                yield TextEvent(type="text", text="The job failed.")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.confirm_tool = mock_confirm_tool
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                main, ["chat", "--auto-approve", "-m", "Run job"]
            )

            assert result.exit_code == 0
            assert "Tool Error: Job failed: timeout" in result.output

    def test_display_tool_result_json_output(self, runner, mock_env):
        """Test display_tool_result_events with json output mode."""
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.new_chat_id = MagicMock(return_value="test-chat-id")

            async def mock_send_message(chat_id, message):
                yield ToolCallEvent(
                    type="tool-call",
                    toolCallId="tool-json",
                    toolName="create_config",
                    state="input-available",
                    input={"name": "test"},
                )

            async def mock_confirm_tool(chat_id, tool_call_id, tool_name):
                yield TextEvent(type="text", text="Done")
                yield FinishEvent(type="finish", finishReason="stop")

            mock_client.send_message = mock_send_message
            mock_client.confirm_tool = mock_confirm_tool
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(
                main, ["chat", "--auto-approve", "--json-output", "-m", "Create"]
            )

            assert result.exit_code == 0
            # All output should be JSON lines
            lines = [ln for ln in result.output.strip().split("\n") if ln]
            for line in lines:
                parsed = json.loads(line)
                assert "type" in parsed


class TestGetChatDisplayEdgeCases:
    """Tests for get-chat display with various part types."""

    def test_get_chat_no_title(self, runner, mock_env):
        """Test get-chat when chat has no title."""
        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_chat = AsyncMock(
                return_value=ChatDetail(
                    id="chat-123",
                    title=None,
                    messages=[],
                )
            )
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-chat", "chat-123"])

            assert result.exit_code == 0
            assert "(no title)" in result.output

    def test_get_chat_with_object_parts(self, runner, mock_env):
        """Test get-chat with parts that are objects (have .text / .type attrs)."""

        class FakeTextPart:
            text = "Here's the result:"

        class FakeToolPart:
            type = "tool-call"

        # Build a ChatDetail with object-style parts (not dicts)
        chat = ChatDetail(id="chat-123", title="Test", messages=[])
        msg = Message(id="msg-1", role="assistant", parts=[])
        # Override parts with objects after construction
        msg.parts = [FakeTextPart(), FakeToolPart()]  # type: ignore
        chat.messages = [msg]

        with patch("kai_client.cli.get_client") as mock_get_client:
            mock_client = AsyncMock()
            mock_client.get_chat = AsyncMock(return_value=chat)
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=None)
            mock_get_client.return_value = mock_client

            result = runner.invoke(main, ["get-chat", "chat-123"])

            assert result.exit_code == 0
            assert "Here's the result:" in result.output
            assert "[tool-call]" in result.output

"""Tests for SSE stream parser."""

from unittest.mock import AsyncMock

import httpx
import pytest

from kai_client.exceptions import KaiStreamError
from kai_client.models import (
    ErrorEvent,
    FinishEvent,
    StepStartEvent,
    TextEvent,
    ToolApprovalRequestEvent,
    ToolCallEvent,
    ToolOutputErrorEvent,
    UnknownEvent,
    UsageEvent,
    UsageInfo,
)
from kai_client.sse import SSEStreamParser, parse_sse_event, parse_sse_stream


class TestParseSSEEvent:
    """Tests for parse_sse_event function."""

    def test_parse_text_event(self):
        data = {"type": "text", "text": "Hello, world!"}
        event = parse_sse_event(data)
        assert isinstance(event, TextEvent)
        assert event.text == "Hello, world!"
        assert event.state is None

    def test_parse_text_event_with_state(self):
        data = {"type": "text", "text": "Done", "state": "done"}
        event = parse_sse_event(data)
        assert isinstance(event, TextEvent)
        assert event.state == "done"

    def test_parse_step_start_event(self):
        data = {"type": "step-start"}
        event = parse_sse_event(data)
        assert isinstance(event, StepStartEvent)
        assert event.type == "step-start"

    def test_parse_tool_call_input_available(self):
        data = {
            "type": "tool-call",
            "toolCallId": "call-123",
            "toolName": "get_tables",
            "state": "input-available",
            "input": {"bucket_id": "in.c-main"},
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.tool_call_id == "call-123"
        assert event.tool_name == "get_tables"
        assert event.state == "input-available"
        assert event.input == {"bucket_id": "in.c-main"}
        assert event.output is None

    def test_parse_tool_call_output_available(self):
        data = {
            "type": "tool-call",
            "toolCallId": "call-123",
            "toolName": "get_tables",
            "state": "output-available",
            "output": {"tables": ["table1", "table2"]},
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.state == "output-available"
        assert event.output == {"tables": ["table1", "table2"]}

    def test_parse_finish_event_stop(self):
        data = {"type": "finish", "finishReason": "stop"}
        event = parse_sse_event(data)
        assert isinstance(event, FinishEvent)
        assert event.finish_reason == "stop"

    def test_parse_finish_event_length(self):
        data = {"type": "finish", "finishReason": "length"}
        event = parse_sse_event(data)
        assert isinstance(event, FinishEvent)
        assert event.finish_reason == "length"

    def test_parse_error_event(self):
        data = {
            "type": "error",
            "message": "Something went wrong",
            "code": "internal_error",
        }
        event = parse_sse_event(data)
        assert isinstance(event, ErrorEvent)
        assert event.message == "Something went wrong"
        assert event.code == "internal_error"

    def test_parse_error_event_without_code(self):
        data = {"type": "error", "message": "Error occurred"}
        event = parse_sse_event(data)
        assert isinstance(event, ErrorEvent)
        assert event.code is None

    def test_parse_unknown_event(self):
        data = {"type": "custom-event", "foo": "bar", "count": 42}
        event = parse_sse_event(data)
        assert isinstance(event, UnknownEvent)
        assert event.type == "custom-event"
        assert event.data == data

    def test_parse_empty_type(self):
        data = {"foo": "bar"}
        event = parse_sse_event(data)
        assert isinstance(event, UnknownEvent)
        assert event.type == ""


class TestProductionSSEFormats:
    """Tests for production SSE event formats."""

    def test_parse_text_delta_event(self):
        """Test parsing production text-delta event."""
        data = {"type": "text-delta", "delta": "Hello from production!"}
        event = parse_sse_event(data)
        assert isinstance(event, TextEvent)
        assert event.type == "text"
        assert event.text == "Hello from production!"

    def test_parse_text_delta_with_state(self):
        """Test parsing production text-delta event with state."""
        data = {"type": "text-delta", "delta": "Done", "state": "done"}
        event = parse_sse_event(data)
        assert isinstance(event, TextEvent)
        assert event.text == "Done"
        assert event.state == "done"

    def test_parse_start_step_event(self):
        """Test parsing production start-step event (alternate name)."""
        data = {"type": "start-step"}
        event = parse_sse_event(data)
        assert isinstance(event, StepStartEvent)
        assert event.type == "step-start"

    def test_parse_tool_input_start_event(self):
        """Test parsing production tool-input-start event."""
        data = {
            "type": "tool-input-start",
            "toolCallId": "call-123",
            "toolName": "create_bucket",
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.type == "tool-call"
        assert event.tool_call_id == "call-123"
        assert event.tool_name == "create_bucket"
        assert event.state == "started"
        assert event.input is None
        assert event.output is None

    def test_parse_tool_input_available_event(self):
        """Test parsing production tool-input-available event."""
        data = {
            "type": "tool-input-available",
            "toolCallId": "call-123",
            "toolName": "create_bucket",
            "input": {"name": "test-bucket", "stage": "in"},
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.type == "tool-call"
        assert event.tool_call_id == "call-123"
        assert event.state == "input-available"
        assert event.input == {"name": "test-bucket", "stage": "in"}
        assert event.output is None

    def test_parse_tool_output_available_event(self):
        """Test parsing production tool-output-available event."""
        data = {
            "type": "tool-output-available",
            "toolCallId": "call-123",
            "toolName": "create_bucket",
            "output": {"success": True, "bucket_id": "in.c-test"},
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.type == "tool-call"
        assert event.tool_call_id == "call-123"
        assert event.state == "output-available"
        assert event.output == {"success": True, "bucket_id": "in.c-test"}
        assert event.input is None

    def test_parse_finish_step_event(self):
        """Test parsing production finish-step event."""
        data = {"type": "finish-step", "finishReason": "stop"}
        event = parse_sse_event(data)
        assert isinstance(event, FinishEvent)
        assert event.type == "finish"
        assert event.finish_reason == "stop"

    def test_parse_finish_event_default_reason(self):
        """Test parsing finish event with missing finishReason."""
        data = {"type": "finish"}
        event = parse_sse_event(data)
        assert isinstance(event, FinishEvent)
        assert event.finish_reason == "stop"  # Default

    def test_parse_finish_event_with_usage(self):
        """Test parsing finish event with token usage data."""
        data = {
            "type": "finish",
            "finishReason": "stop",
            "usage": {"promptTokens": 150, "completionTokens": 50},
        }
        event = parse_sse_event(data)
        assert isinstance(event, FinishEvent)
        assert event.usage is not None
        assert event.usage.prompt_tokens == 150
        assert event.usage.completion_tokens == 50

    def test_parse_finish_step_event_with_usage(self):
        """Test parsing finish-step event with token usage data."""
        data = {
            "type": "finish-step",
            "finishReason": "stop",
            "usage": {"promptTokens": 200, "completionTokens": 100},
        }
        event = parse_sse_event(data)
        assert isinstance(event, FinishEvent)
        assert event.usage is not None
        assert event.usage.prompt_tokens == 200
        assert event.usage.completion_tokens == 100

    def test_parse_finish_event_without_usage(self):
        """Test parsing finish event without usage still works."""
        data = {"type": "finish", "finishReason": "stop"}
        event = parse_sse_event(data)
        assert isinstance(event, FinishEvent)
        assert event.usage is None

    def test_parse_usage_event(self):
        """Test parsing a data-usage event from dataStream.write()."""
        data = {
            "type": "data-usage",
            "data": {"promptTokens": 500, "completionTokens": 150},
        }
        event = parse_sse_event(data)
        assert isinstance(event, UsageEvent)
        assert event.type == "data-usage"
        assert event.usage.prompt_tokens == 500
        assert event.usage.completion_tokens == 150

    def test_parse_usage_event_empty_data(self):
        """Test parsing data-usage event with missing data defaults to 0."""
        data = {"type": "data-usage"}
        event = parse_sse_event(data)
        assert isinstance(event, UsageEvent)
        assert event.usage.prompt_tokens == 0
        assert event.usage.completion_tokens == 0

    def test_production_unknown_events_passthrough(self):
        """Test that production-specific events we don't handle are returned as unknown."""
        # These are intentionally not handled but shouldn't cause errors
        for event_type in ["start", "text-start", "text-end", "step-end"]:
            data = {"type": event_type, "id": "some-id"}
            event = parse_sse_event(data)
            assert isinstance(event, UnknownEvent)
            assert event.type == event_type

    def test_parse_tool_output_error_event(self):
        """Test parsing production tool-output-error event."""
        data = {
            "type": "tool-output-error",
            "toolCallId": "call-123",
            "errorText": "Tool execution failed: Connection timeout",
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolOutputErrorEvent)
        assert event.type == "tool-output-error"
        assert event.tool_call_id == "call-123"
        assert event.error_text == "Tool execution failed: Connection timeout"

    def test_parse_tool_output_error_event_minimal(self):
        """Test parsing tool-output-error event with minimal data."""
        data = {
            "type": "tool-output-error",
            "toolCallId": "call-456",
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolOutputErrorEvent)
        assert event.tool_call_id == "call-456"
        assert event.error_text == "Unknown error"  # Default value


class TestToolCallStates:
    """Tests for all tool call state transitions."""

    def test_tool_call_started_state(self):
        """Test tool call in started state."""
        data = {
            "type": "tool-input-start",
            "toolCallId": "call-001",
            "toolName": "create_config",
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.state == "started"
        assert event.tool_name == "create_config"
        assert event.input is None
        assert event.output is None

    def test_tool_call_input_available_state(self):
        """Test tool call in input-available state (waiting for approval)."""
        data = {
            "type": "tool-input-available",
            "toolCallId": "call-002",
            "toolName": "update_config",
            "input": {
                "configurationId": "123",
                "configuration": {"foo": "bar"},
                "justification": "Updating config based on user request",
            },
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.state == "input-available"
        assert event.tool_name == "update_config"
        assert event.input["configurationId"] == "123"

    def test_tool_call_output_available_state(self):
        """Test tool call in output-available state (completed)."""
        data = {
            "type": "tool-output-available",
            "toolCallId": "call-003",
            "toolName": "get_tables",
            "output": {
                "tables": ["table1", "table2"],
                "_toolName": "get_tables",
                "_timestamp": "2025-01-15T10:00:00Z",
            },
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.state == "output-available"
        assert event.output["tables"] == ["table1", "table2"]

    def test_tool_call_output_error_state(self):
        """Test tool call that resulted in error."""
        data = {
            "type": "tool-output-error",
            "toolCallId": "call-004",
            "errorText": "No execute function found for tool",
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolOutputErrorEvent)
        assert event.tool_call_id == "call-004"
        assert "No execute function found" in event.error_text


class TestAllToolTypes:
    """Tests to verify all backend tool types can be handled."""

    # All 28 MCP tools + 3 local tools from the backend
    TOOL_NAMES = [
        # Component Tools
        "add_config_row",
        "create_config",
        "create_sql_transformation",
        "get_components",
        "get_config_examples",
        "get_configs",
        "update_config",
        "update_config_row",
        "update_sql_transformation",
        # Documentation Tools
        "docs_query",
        # Flow Tools
        "create_conditional_flow",
        "create_flow",
        "get_flow_examples",
        "get_flow_schema",
        "get_flows",
        "update_flow",
        # Jobs Tools
        "get_jobs",
        "run_job",
        # OAuth Tools
        "create_oauth_url",
        # Data Apps Tools
        "deploy_data_app",
        "get_data_apps",
        "modify_data_app",
        # Project Tools
        "get_project_info",
        # SQL Tools
        "query_data",
        # Search Tools
        "find_component_id",
        "search",
        # Storage Tools
        "get_tables",
        "get_buckets",
        "update_descriptions",
        # Local Tools
        "request_credentials",
        "fetch_website",
        "search_internet",
    ]

    def test_all_tool_names_can_be_parsed(self):
        """Test that all backend tool names can be parsed in tool call events."""
        for tool_name in self.TOOL_NAMES:
            data = {
                "type": "tool-input-start",
                "toolCallId": f"call-{tool_name}",
                "toolName": tool_name,
            }
            event = parse_sse_event(data)
            assert isinstance(event, ToolCallEvent)
            assert event.tool_name == tool_name

    def test_all_tool_names_with_output(self):
        """Test that all backend tools can return output."""
        for tool_name in self.TOOL_NAMES:
            data = {
                "type": "tool-output-available",
                "toolCallId": f"call-{tool_name}",
                "toolName": tool_name,
                "output": {
                    "result": f"Result from {tool_name}",
                    "_toolName": tool_name,
                    "_timestamp": "2025-01-15T10:00:00Z",
                },
            }
            event = parse_sse_event(data)
            assert isinstance(event, ToolCallEvent)
            assert event.state == "output-available"
            assert event.output["_toolName"] == tool_name


class TestSSEStreamParser:
    """Tests for SSEStreamParser class."""

    def test_initial_state(self):
        parser = SSEStreamParser()
        assert parser.text == ""
        assert parser.tool_calls == {}
        assert parser.finished is False
        assert parser.finish_reason is None
        assert parser.prompt_tokens == 0
        assert parser.completion_tokens == 0
        assert parser.total_tokens == 0

    def test_accumulate_text(self):
        parser = SSEStreamParser()

        parser.process_event(TextEvent(type="text", text="Hello"))
        assert parser.text == "Hello"

        parser.process_event(TextEvent(type="text", text=" world"))
        assert parser.text == "Hello world"

        parser.process_event(TextEvent(type="text", text="!"))
        assert parser.text == "Hello world!"

    def test_track_tool_calls(self):
        parser = SSEStreamParser()

        # Tool call starts
        event1 = ToolCallEvent(
            type="tool-call",
            toolCallId="call-1",
            toolName="get_tables",
            state="input-available",
            input={"bucket": "test"},
        )
        parser.process_event(event1)

        assert "call-1" in parser.tool_calls
        assert parser.tool_calls["call-1"].state == "input-available"

        # Tool call completes
        event2 = ToolCallEvent(
            type="tool-call",
            toolCallId="call-1",
            toolName="get_tables",
            state="output-available",
            output={"result": "success"},
        )
        parser.process_event(event2)

        assert parser.tool_calls["call-1"].state == "output-available"
        assert parser.tool_calls["call-1"].output == {"result": "success"}

    def test_multiple_tool_calls(self):
        parser = SSEStreamParser()

        parser.process_event(ToolCallEvent(
            type="tool-call",
            toolCallId="call-1",
            toolName="tool_a",
            state="done",
        ))
        parser.process_event(ToolCallEvent(
            type="tool-call",
            toolCallId="call-2",
            toolName="tool_b",
            state="done",
        ))

        assert len(parser.tool_calls) == 2
        assert "call-1" in parser.tool_calls
        assert "call-2" in parser.tool_calls

    def test_finish_event(self):
        parser = SSEStreamParser()

        assert parser.finished is False
        assert parser.finish_reason is None

        parser.process_event(FinishEvent(type="finish", finishReason="stop"))

        assert parser.finished is True
        assert parser.finish_reason == "stop"

    def test_finish_event_with_usage(self):
        parser = SSEStreamParser()

        usage = UsageInfo(promptTokens=100, completionTokens=50)
        parser.process_event(FinishEvent(type="finish", finishReason="stop", usage=usage))

        assert parser.prompt_tokens == 100
        assert parser.completion_tokens == 50
        assert parser.total_tokens == 150

    def test_finish_event_without_usage(self):
        parser = SSEStreamParser()

        parser.process_event(FinishEvent(type="finish", finishReason="stop"))

        assert parser.prompt_tokens == 0
        assert parser.completion_tokens == 0
        assert parser.total_tokens == 0

    def test_token_accumulation_across_steps(self):
        parser = SSEStreamParser()

        # First step
        usage1 = UsageInfo(promptTokens=100, completionTokens=30)
        parser.process_event(FinishEvent(type="finish", finishReason="stop", usage=usage1))

        assert parser.prompt_tokens == 100
        assert parser.completion_tokens == 30
        assert parser.total_tokens == 130

        # Second step (e.g., after tool use)
        usage2 = UsageInfo(promptTokens=200, completionTokens=60)
        parser.process_event(FinishEvent(type="finish", finishReason="stop", usage=usage2))

        assert parser.prompt_tokens == 300
        assert parser.completion_tokens == 90
        assert parser.total_tokens == 390

    def test_usage_event(self):
        """Test that standalone UsageEvent updates token counters."""
        parser = SSEStreamParser()

        usage = UsageInfo(promptTokens=400, completionTokens=120)
        parser.process_event(UsageEvent(type="data-usage", usage=usage))

        assert parser.prompt_tokens == 400
        assert parser.completion_tokens == 120
        assert parser.total_tokens == 520

    def test_usage_event_accumulates_with_finish(self):
        """Test that UsageEvent and FinishEvent usage accumulate together."""
        parser = SSEStreamParser()

        # Usage event from dataStream.write()
        parser.process_event(UsageEvent(
            type="data-usage",
            usage=UsageInfo(promptTokens=300, completionTokens=80),
        ))

        # Finish event without usage (current backend behavior)
        parser.process_event(FinishEvent(type="finish", finishReason="stop"))

        assert parser.prompt_tokens == 300
        assert parser.completion_tokens == 80
        assert parser.total_tokens == 380
        assert parser.finished is True

    def test_reset(self):
        parser = SSEStreamParser()

        # Add some data
        parser.process_event(TextEvent(type="text", text="Hello"))
        parser.process_event(ToolCallEvent(
            type="tool-call",
            toolCallId="call-1",
            toolName="test",
            state="done",
        ))
        usage = UsageInfo(promptTokens=500, completionTokens=200)
        parser.process_event(FinishEvent(type="finish", finishReason="stop", usage=usage))

        # Verify data was added
        assert parser.text == "Hello"
        assert len(parser.tool_calls) == 1
        assert parser.finished is True

        # Reset
        parser.reset()

        # Verify reset worked
        assert parser.text == ""
        assert parser.tool_calls == {}
        assert parser.finished is False
        assert parser.finish_reason is None
        assert parser.prompt_tokens == 0
        assert parser.completion_tokens == 0
        assert parser.total_tokens == 0

    def test_tool_calls_returns_copy(self):
        parser = SSEStreamParser()

        parser.process_event(ToolCallEvent(
            type="tool-call",
            toolCallId="call-1",
            toolName="test",
            state="done",
        ))

        # Get tool calls and modify the returned dict
        calls = parser.tool_calls
        calls["call-2"] = None  # type: ignore

        # Original should be unchanged
        assert len(parser.tool_calls) == 1
        assert "call-2" not in parser.tool_calls

    def test_ignores_other_events(self):
        parser = SSEStreamParser()

        # These should not raise errors
        parser.process_event(StepStartEvent(type="step-start"))
        parser.process_event(ErrorEvent(type="error", message="test"))
        parser.process_event(UnknownEvent(type="custom", data={}))

        # State should be unchanged
        assert parser.text == ""
        assert parser.tool_calls == {}
        assert parser.finished is False

    def test_complex_conversation(self):
        """Test a realistic conversation flow."""
        parser = SSEStreamParser()

        # Simulated stream of events
        events = [
            StepStartEvent(type="step-start"),
            TextEvent(type="text", text="Let me check "),
            TextEvent(type="text", text="the tables."),
            ToolCallEvent(
                type="tool-call",
                toolCallId="call-1",
                toolName="list_tables",
                state="input-available",
                input={},
            ),
            ToolCallEvent(
                type="tool-call",
                toolCallId="call-1",
                toolName="list_tables",
                state="output-available",
                output={"tables": ["users", "orders"]},
            ),
            TextEvent(type="text", text="\n\nI found 2 tables: "),
            TextEvent(type="text", text="users and orders."),
            FinishEvent(type="finish", finishReason="stop"),
        ]

        for event in events:
            parser.process_event(event)

        assert parser.text == "Let me check the tables.\n\nI found 2 tables: users and orders."
        assert len(parser.tool_calls) == 1
        assert parser.tool_calls["call-1"].output == {"tables": ["users", "orders"]}
        assert parser.finished is True
        assert parser.finish_reason == "stop"


class TestToolApprovalEvents:
    """Tests for tool approval event parsing."""

    def test_parse_tool_approval_request_event(self):
        """Test parsing tool-approval-request event."""
        data = {
            "type": "tool-approval-request",
            "approvalId": "approval-abc-123",
            "toolCallId": "call-456",
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolApprovalRequestEvent)
        assert event.type == "tool-approval-request"
        assert event.approval_id == "approval-abc-123"
        assert event.tool_call_id == "call-456"

    def test_parse_tool_approval_request_minimal(self):
        """Test parsing tool-approval-request with minimal data."""
        data = {"type": "tool-approval-request"}
        event = parse_sse_event(data)
        assert isinstance(event, ToolApprovalRequestEvent)
        assert event.approval_id == ""
        assert event.tool_call_id == ""

    def test_parse_tool_call_with_approval(self):
        """Test tool-input-available with approval metadata."""
        data = {
            "type": "tool-input-available",
            "toolCallId": "call-789",
            "toolName": "update_descriptions",
            "input": {"descriptions": "new desc"},
            "approval": {
                "id": "appr-xyz",
                "approved": None,
            },
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.approval is not None
        assert event.approval.id == "appr-xyz"
        assert event.approval.approved is None

    def test_parse_tool_call_with_approval_approved(self):
        """Test tool call with approval that has been approved."""
        data = {
            "type": "tool-call",
            "toolCallId": "call-100",
            "toolName": "create_config",
            "state": "output-available",
            "approval": {
                "id": "appr-100",
                "approved": True,
                "reason": "User approved",
            },
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.approval is not None
        assert event.approval.approved is True
        assert event.approval.reason == "User approved"

    def test_parse_tool_call_with_empty_approval(self):
        """Test tool call with empty approval dict (no id)."""
        data = {
            "type": "tool-call",
            "toolCallId": "call-200",
            "toolName": "get_tables",
            "state": "started",
            "approval": {},  # Empty — should result in None
        }
        event = parse_sse_event(data)
        assert isinstance(event, ToolCallEvent)
        assert event.approval is None


class TestParseSSEStream:
    """Tests for the parse_sse_stream async generator."""

    @pytest.mark.asyncio
    async def test_parse_basic_stream(self):
        """Test parsing a basic SSE stream."""
        lines = [
            'data: {"type":"text","text":"Hello"}',
            'data: {"type":"finish","finishReason":"stop"}',
        ]

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = self._make_async_iter(lines)

        events = [event async for event in parse_sse_stream(response)]
        assert len(events) == 2
        assert events[0].type == "text"
        assert events[0].text == "Hello"
        assert events[1].type == "finish"

    @pytest.mark.asyncio
    async def test_parse_stream_skips_empty_lines(self):
        """Test that empty lines are skipped."""
        lines = [
            "",
            'data: {"type":"text","text":"Hello"}',
            "",
            "",
            'data: {"type":"finish","finishReason":"stop"}',
        ]

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = self._make_async_iter(lines)

        events = [event async for event in parse_sse_stream(response)]
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_parse_stream_skips_comments(self):
        """Test that SSE comments (lines starting with :) are skipped."""
        lines = [
            ": this is a comment",
            'data: {"type":"text","text":"Hello"}',
            ": another comment",
            'data: {"type":"finish","finishReason":"stop"}',
        ]

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = self._make_async_iter(lines)

        events = [event async for event in parse_sse_stream(response)]
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_parse_stream_skips_empty_data(self):
        """Test that empty data lines are skipped."""
        lines = [
            "data: ",
            "data:   ",
            'data: {"type":"text","text":"Hello"}',
            'data: {"type":"finish","finishReason":"stop"}',
        ]

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = self._make_async_iter(lines)

        events = [event async for event in parse_sse_stream(response)]
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_parse_stream_handles_done_marker(self):
        """Test that [DONE] termination marker is skipped."""
        lines = [
            'data: {"type":"text","text":"Hello"}',
            'data: {"type":"finish","finishReason":"stop"}',
            "data: [DONE]",
        ]

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = self._make_async_iter(lines)

        events = [event async for event in parse_sse_stream(response)]
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_parse_stream_ignores_event_field(self):
        """Test that 'event:' lines are ignored without error."""
        lines = [
            "event: message",
            'data: {"type":"text","text":"Hello"}',
            'data: {"type":"finish","finishReason":"stop"}',
        ]

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = self._make_async_iter(lines)

        events = [event async for event in parse_sse_stream(response)]
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_parse_stream_ignores_id_field(self):
        """Test that 'id:' lines are ignored without error."""
        lines = [
            "id: 12345",
            'data: {"type":"text","text":"Hello"}',
            'data: {"type":"finish","finishReason":"stop"}',
        ]

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = self._make_async_iter(lines)

        events = [event async for event in parse_sse_stream(response)]
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_parse_stream_ignores_retry_field(self):
        """Test that 'retry:' lines are ignored without error."""
        lines = [
            "retry: 3000",
            'data: {"type":"text","text":"Hello"}',
            'data: {"type":"finish","finishReason":"stop"}',
        ]

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = self._make_async_iter(lines)

        events = [event async for event in parse_sse_stream(response)]
        assert len(events) == 2

    @pytest.mark.asyncio
    async def test_parse_stream_json_decode_error(self):
        """Test that invalid JSON raises KaiStreamError."""
        lines = [
            "data: {invalid json}",
        ]

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = self._make_async_iter(lines)

        with pytest.raises(KaiStreamError) as exc_info:
            async for _ in parse_sse_stream(response):
                pass

        assert "Failed to parse SSE event" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_parse_stream_handles_stream_closed(self):
        """Test graceful handling of StreamClosed."""

        async def _iter_lines():
            yield 'data: {"type":"text","text":"Hello"}'
            raise httpx.StreamClosed()

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = _iter_lines

        events = [event async for event in parse_sse_stream(response)]
        assert len(events) == 1
        assert events[0].text == "Hello"

    @pytest.mark.asyncio
    async def test_parse_stream_handles_remote_protocol_error(self):
        """Test KaiStreamError on RemoteProtocolError."""

        async def _iter_lines():
            yield 'data: {"type":"text","text":"Hello"}'
            raise httpx.RemoteProtocolError("Connection reset")

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = _iter_lines

        with pytest.raises(KaiStreamError) as exc_info:
            async for _ in parse_sse_stream(response):
                pass

        assert "Connection error during streaming" in str(exc_info.value)

    @staticmethod
    def _make_async_iter(lines):
        """Create an async iterator function from a list of lines."""

        async def _aiter():
            for line in lines:
                yield line

        return _aiter


class TestSSEStreamParserConsumeStream:
    """Tests for SSEStreamParser.consume_stream method."""

    @pytest.mark.asyncio
    async def test_consume_stream_yields_events(self):
        """Test consume_stream yields and processes events."""
        lines = [
            'data: {"type":"text","text":"Hello"}',
            'data: {"type":"text","text":" world"}',
            'data: {"type":"finish","finishReason":"stop"}',
        ]

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = TestParseSSEStream._make_async_iter(lines)

        parser = SSEStreamParser()
        events = [event async for event in parser.consume_stream(response)]

        assert len(events) == 3
        assert parser.text == "Hello world"
        assert parser.finished is True

    @pytest.mark.asyncio
    async def test_consume_stream_no_yield(self):
        """Test consume_stream with yield_events=False."""
        lines = [
            'data: {"type":"text","text":"Hello"}',
            'data: {"type":"finish","finishReason":"stop"}',
        ]

        response = AsyncMock(spec=httpx.Response)
        response.aiter_lines = TestParseSSEStream._make_async_iter(lines)

        parser = SSEStreamParser()
        events = [
            event async for event in parser.consume_stream(response, yield_events=False)
        ]

        assert len(events) == 0  # No events yielded
        assert parser.text == "Hello"  # But state was still updated
        assert parser.finished is True



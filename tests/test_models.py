"""Tests for Pydantic models."""

from datetime import datetime

from kai_client.models import (
    Chat,
    ChatDetail,
    ChatRequest,
    ErrorEvent,
    ErrorResponse,
    FinishEvent,
    HistoryResponse,
    InfoResponse,
    MessageMetadata,
    MessageRequest,
    PingResponse,
    RequestContext,
    StepStartEvent,
    TextEvent,
    TextPart,
    ToolCallEvent,
    ToolCallPart,
    ToolResultPart,
    Vote,
    VoteRequest,
)


class TestTextPart:
    """Tests for TextPart model."""

    def test_basic_creation(self):
        part = TextPart(type="text", text="Hello, world!")
        assert part.type == "text"
        assert part.text == "Hello, world!"
        assert part.state is None

    def test_with_state(self):
        part = TextPart(type="text", text="Done", state="done")
        assert part.state == "done"

    def test_serialization(self):
        part = TextPart(type="text", text="Test")
        data = part.model_dump()
        assert data["type"] == "text"
        assert data["text"] == "Test"


class TestToolResultPart:
    """Tests for ToolResultPart model."""

    def test_basic_creation(self):
        part = ToolResultPart(
            type="tool-result",
            toolCallId="call-123",
            toolName="get_tables",
            result={"tables": ["table1", "table2"]},
        )
        assert part.type == "tool-result"
        assert part.tool_call_id == "call-123"
        assert part.tool_name == "get_tables"
        assert part.result == {"tables": ["table1", "table2"]}

    def test_serialization_with_alias(self):
        part = ToolResultPart(
            type="tool-result",
            toolCallId="call-123",
            toolName="test_tool",
            result="success",
        )
        data = part.model_dump(by_alias=True)
        assert data["toolCallId"] == "call-123"
        assert data["toolName"] == "test_tool"


class TestToolCallPart:
    """Tests for ToolCallPart model."""

    def test_with_input(self):
        part = ToolCallPart(
            type="tool-get_tables",
            toolCallId="call-456",
            state="input-available",
            input={"bucket_id": "in.c-main"},
        )
        assert part.tool_call_id == "call-456"
        assert part.state == "input-available"
        assert part.input == {"bucket_id": "in.c-main"}
        assert part.output is None

    def test_with_output(self):
        part = ToolCallPart(
            type="tool-get_tables",
            toolCallId="call-456",
            state="output-available",
            output={"result": "success"},
        )
        assert part.state == "output-available"
        assert part.output == {"result": "success"}


class TestMessageRequest:
    """Tests for MessageRequest model."""

    def test_basic_creation(self):
        request = MessageRequest(
            id="msg-123",
            role="user",
            parts=[TextPart(type="text", text="Hello")],
        )
        assert request.id == "msg-123"
        assert request.role == "user"
        assert len(request.parts) == 1
        assert request.parts[0].text == "Hello"

    def test_with_metadata(self):
        request = MessageRequest(
            id="msg-123",
            role="user",
            parts=[TextPart(type="text", text="Test")],
            metadata=MessageMetadata(
                hidden=True,
                request_context=RequestContext(path="/test"),
            ),
        )
        assert request.metadata is not None
        assert request.metadata.hidden is True
        assert request.metadata.request_context.path == "/test"


class TestChatRequest:
    """Tests for ChatRequest model."""

    def test_basic_creation(self):
        request = ChatRequest(
            id="chat-123",
            message=MessageRequest(
                id="msg-456",
                role="user",
                parts=[TextPart(type="text", text="Hello")],
            ),
            selectedChatModel="chat-model",
            selectedVisibilityType="private",
        )
        assert request.id == "chat-123"
        assert request.selected_chat_model == "chat-model"
        assert request.selected_visibility_type == "private"
        assert request.branch_id is None

    def test_with_branch_id(self):
        request = ChatRequest(
            id="chat-123",
            message=MessageRequest(
                id="msg-456",
                role="user",
                parts=[TextPart(type="text", text="Test")],
            ),
            selectedChatModel="chat-model-reasoning",
            selectedVisibilityType="public",
            branchId=12345,
        )
        assert request.branch_id == 12345

    def test_serialization_with_aliases(self):
        request = ChatRequest(
            id="chat-123",
            message=MessageRequest(
                id="msg-456",
                role="user",
                parts=[TextPart(type="text", text="Test")],
            ),
            selectedChatModel="chat-model",
            selectedVisibilityType="private",
            branchId=999,
        )
        data = request.model_dump(by_alias=True)
        assert data["selectedChatModel"] == "chat-model"
        assert data["selectedVisibilityType"] == "private"
        assert data["branchId"] == 999

    def test_is_headless_defaults_to_none(self):
        request = ChatRequest(
            id="chat-123",
            message=MessageRequest(
                id="msg-456",
                role="user",
                parts=[TextPart(type="text", text="Hello")],
            ),
            selectedChatModel="chat-model",
            selectedVisibilityType="private",
        )
        assert request.is_headless is None
        # Omitted from the payload when unset, keeping the request backward-compatible.
        assert "isHeadless" not in request.model_dump(by_alias=True, exclude_none=True)

    def test_is_headless_serializes_with_alias(self):
        request = ChatRequest(
            id="chat-123",
            message=MessageRequest(
                id="msg-456",
                role="user",
                parts=[TextPart(type="text", text="Test")],
            ),
            selectedChatModel="chat-model",
            selectedVisibilityType="private",
            isHeadless=True,
        )
        assert request.is_headless is True
        assert request.model_dump(by_alias=True)["isHeadless"] is True


class TestPingResponse:
    """Tests for PingResponse model."""

    def test_parsing(self):
        response = PingResponse.model_validate(
            {"timestamp": "2025-12-24T16:24:10.641Z"}
        )
        assert isinstance(response.timestamp, datetime)


class TestInfoResponse:
    """Tests for InfoResponse model."""

    def test_parsing(self):
        data = {
            "timestamp": "2025-12-24T16:24:10.641Z",
            "uptime": 12345.67,
            "appName": "kai-backend",
            "appVersion": "1.0.0",
            "serverVersion": "2.0.0",
            "connectedMcp": [
                {"name": "keboola-mcp", "status": "connected"}
            ],
        }
        response = InfoResponse.model_validate(data)
        assert response.app_name == "kai-backend"
        assert response.app_version == "1.0.0"
        assert response.server_version == "2.0.0"
        assert len(response.connected_mcp) == 1
        # connected_mcp is typed as Any, so items are dicts
        assert response.connected_mcp[0]["name"] == "keboola-mcp"


class TestChatModels:
    """Tests for Chat and ChatDetail models."""

    def test_chat_basic(self):
        chat = Chat.model_validate({
            "id": "chat-123",
            "title": "Test Chat",
            "createdAt": "2025-12-24T10:00:00Z",
            "visibility": "private",
        })
        assert chat.id == "chat-123"
        assert chat.title == "Test Chat"
        assert chat.visibility == "private"

    def test_chat_detail_with_messages(self):
        data = {
            "id": "chat-123",
            "title": "Test Chat",
            "messages": [
                {
                    "id": "msg-1",
                    "role": "user",
                    "parts": [{"type": "text", "text": "Hello"}],
                },
                {
                    "id": "msg-2",
                    "role": "assistant",
                    "parts": [{"type": "text", "text": "Hi there!"}],
                },
            ],
        }
        detail = ChatDetail.model_validate(data)
        assert len(detail.messages) == 2
        assert detail.messages[0].role == "user"
        assert detail.messages[1].role == "assistant"


class TestHistoryResponse:
    """Tests for HistoryResponse model."""

    def test_parsing(self):
        data = {
            "chats": [
                {"id": "chat-1", "title": "Chat 1"},
                {"id": "chat-2", "title": "Chat 2"},
            ],
            "hasMore": True,
        }
        response = HistoryResponse.model_validate(data)
        assert len(response.chats) == 2
        assert response.has_more is True


class TestVoteModels:
    """Tests for Vote models."""

    def test_vote_request(self):
        request = VoteRequest(
            chatId="chat-123",
            messageId="msg-456",
            type="up",
        )
        assert request.chat_id == "chat-123"
        assert request.message_id == "msg-456"
        assert request.type == "up"

    def test_vote_response(self):
        vote = Vote.model_validate({
            "id": "vote-1",
            "chatId": "chat-123",
            "messageId": "msg-456",
            "type": "down",
        })
        assert vote.chat_id == "chat-123"
        assert vote.type == "down"


class TestSSEEventModels:
    """Tests for SSE event models."""

    def test_text_event(self):
        event = TextEvent(type="text", text="Hello", state="done")
        assert event.type == "text"
        assert event.text == "Hello"
        assert event.state == "done"

    def test_step_start_event(self):
        event = StepStartEvent(type="step-start")
        assert event.type == "step-start"

    def test_tool_call_event(self):
        event = ToolCallEvent(
            type="tool-call",
            toolCallId="call-123",
            toolName="get_tables",
            state="input-available",
            input={"bucket": "test"},
        )
        assert event.tool_call_id == "call-123"
        assert event.tool_name == "get_tables"
        assert event.state == "input-available"

    def test_finish_event(self):
        event = FinishEvent(type="finish", finishReason="stop")
        assert event.finish_reason == "stop"
        assert event.usage is None

    def test_finish_event_with_usage(self):
        from kai_client.models import UsageInfo

        usage = UsageInfo(promptTokens=100, completionTokens=50)
        event = FinishEvent(type="finish", finishReason="stop", usage=usage)
        assert event.usage is not None
        assert event.usage.prompt_tokens == 100
        assert event.usage.completion_tokens == 50

    def test_usage_info_defaults(self):
        from kai_client.models import UsageInfo

        usage = UsageInfo()
        assert usage.prompt_tokens == 0
        assert usage.completion_tokens == 0

    def test_usage_info_from_camel_case(self):
        from kai_client.models import UsageInfo

        usage = UsageInfo.model_validate({"promptTokens": 250, "completionTokens": 75})
        assert usage.prompt_tokens == 250
        assert usage.completion_tokens == 75

    def test_usage_info_extra_fields(self):
        from kai_client.models import UsageInfo

        usage = UsageInfo.model_validate(
            {"promptTokens": 10, "completionTokens": 5, "totalTokens": 15}
        )
        assert usage.prompt_tokens == 10
        assert usage.completion_tokens == 5

    def test_usage_event(self):
        from kai_client.models import UsageEvent, UsageInfo

        usage = UsageInfo(promptTokens=300, completionTokens=75)
        event = UsageEvent(type="data-usage", usage=usage)
        assert event.type == "data-usage"
        assert event.usage.prompt_tokens == 300
        assert event.usage.completion_tokens == 75

    def test_usage_event_from_dict(self):
        from kai_client.models import UsageEvent

        event = UsageEvent.model_validate({
            "type": "data-usage",
            "usage": {"promptTokens": 600, "completionTokens": 200},
        })
        assert event.usage.prompt_tokens == 600
        assert event.usage.completion_tokens == 200

    def test_error_event(self):
        event = ErrorEvent(
            type="error",
            message="Something went wrong",
            code="internal_error",
        )
        assert event.message == "Something went wrong"
        assert event.code == "internal_error"

    def test_tool_output_error_event(self):
        from kai_client.models import ToolOutputErrorEvent

        event = ToolOutputErrorEvent(
            type="tool-output-error",
            toolCallId="call-123",
            errorText="Tool execution failed: Connection timeout",
        )
        assert event.type == "tool-output-error"
        assert event.tool_call_id == "call-123"
        assert event.error_text == "Tool execution failed: Connection timeout"

    def test_tool_output_error_event_serialization(self):
        from kai_client.models import ToolOutputErrorEvent

        event = ToolOutputErrorEvent(
            type="tool-output-error",
            toolCallId="call-456",
            errorText="No execute function found",
        )
        data = event.model_dump(by_alias=True)
        assert data["toolCallId"] == "call-456"
        assert data["errorText"] == "No execute function found"


class TestErrorResponse:
    """Tests for ErrorResponse model."""

    def test_basic_error(self):
        response = ErrorResponse.model_validate({
            "code": "unauthorized:chat",
            "message": "Invalid token",
        })
        assert response.code == "unauthorized:chat"
        assert response.message == "Invalid token"
        assert response.cause is None

    def test_error_with_cause(self):
        response = ErrorResponse.model_validate({
            "code": "bad_request:api",
            "message": "Validation failed",
            "cause": "Missing required field",
        })
        assert response.cause == "Missing required field"


class TestStepStartPart:
    """Tests for StepStartPart model."""

    def test_basic_creation(self):
        from kai_client.models import StepStartPart

        part = StepStartPart(type="step-start")
        assert part.type == "step-start"

    def test_serialization(self):
        from kai_client.models import StepStartPart

        part = StepStartPart(type="step-start")
        data = part.model_dump()
        assert data["type"] == "step-start"


class TestMessage:
    """Tests for Message model."""

    def test_basic_creation(self):
        from kai_client.models import Message

        message = Message.model_validate({
            "id": "msg-123",
            "role": "user",
            "parts": [{"type": "text", "text": "Hello"}],
        })
        assert message.id == "msg-123"
        assert message.role == "user"
        assert len(message.parts) == 1

    def test_with_timestamps(self):
        from kai_client.models import Message

        message = Message.model_validate({
            "id": "msg-123",
            "role": "assistant",
            "parts": [],
            "createdAt": "2025-01-08T12:00:00Z",
        })
        assert message.created_at is not None
        assert message.created_at.year == 2025

    def test_with_metadata(self):
        from kai_client.models import Message

        message = Message.model_validate({
            "id": "msg-123",
            "role": "user",
            "parts": [],
            "metadata": {"hidden": True, "extra": "data"},
        })
        assert message.metadata is not None
        assert message.metadata["hidden"] is True


class TestMcpConnection:
    """Tests for McpConnection model."""

    def test_basic_creation(self):
        from kai_client.models import McpConnection

        mcp = McpConnection(name="keboola-mcp", status="connected")
        assert mcp.name == "keboola-mcp"
        assert mcp.status == "connected"

    def test_extra_fields_allowed(self):
        from kai_client.models import McpConnection

        mcp = McpConnection.model_validate({
            "name": "test-mcp",
            "status": "disconnected",
            "extra_field": "value",
        })
        assert mcp.name == "test-mcp"


class TestUnknownEvent:
    """Tests for UnknownEvent model."""

    def test_basic_creation(self):
        from kai_client.models import UnknownEvent

        event = UnknownEvent(type="custom-event", data={"foo": "bar"})
        assert event.type == "custom-event"
        assert event.data == {"foo": "bar"}

    def test_default_data(self):
        from kai_client.models import UnknownEvent

        event = UnknownEvent(type="minimal")
        assert event.data == {}


class TestRequestContext:
    """Tests for RequestContext model."""

    def test_basic_creation(self):
        ctx = RequestContext(path="/some/path")
        assert ctx.path == "/some/path"

    def test_none_path(self):
        ctx = RequestContext()
        assert ctx.path is None


class TestMessageMetadataFields:
    """Tests for MessageMetadata serialization."""

    def test_serialization_with_alias(self):
        metadata = MessageMetadata(
            hidden=True,
            request_context=RequestContext(path="/test"),
        )
        data = metadata.model_dump(by_alias=True)
        assert data["hidden"] is True
        assert data["requestContext"]["path"] == "/test"


class TestChatOptionalFields:
    """Tests for optional fields in Chat model."""

    def test_chat_all_fields(self):
        chat = Chat.model_validate({
            "id": "chat-123",
            "title": "My Chat",
            "createdAt": "2025-01-08T10:00:00Z",
            "updatedAt": "2025-01-08T11:00:00Z",
            "visibility": "private",
            "userId": "user-456",
        })
        assert chat.id == "chat-123"
        assert chat.title == "My Chat"
        assert chat.created_at is not None
        assert chat.updated_at is not None
        assert chat.visibility == "private"
        assert chat.user_id == "user-456"

    def test_chat_minimal_fields(self):
        chat = Chat.model_validate({"id": "chat-123"})
        assert chat.id == "chat-123"
        assert chat.title is None
        assert chat.created_at is None


class TestVoteOptionalFields:
    """Tests for optional fields in Vote model."""

    def test_vote_all_fields(self):
        vote = Vote.model_validate({
            "id": "vote-123",
            "chatId": "chat-456",
            "messageId": "msg-789",
            "type": "up",
            "createdAt": "2025-01-08T12:00:00Z",
        })
        assert vote.id == "vote-123"
        assert vote.created_at is not None

    def test_vote_minimal_fields(self):
        vote = Vote.model_validate({
            "chatId": "chat-456",
            "messageId": "msg-789",
            "type": "down",
        })
        assert vote.id is None
        assert vote.created_at is None



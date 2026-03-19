"""Tests for the KaiClient."""

import json
import uuid

import pytest
from pytest_httpx import HTTPXMock

from kai_client import (
    KaiAuthenticationError,
    KaiBadRequestError,
    KaiClient,
    KaiError,
    KaiForbiddenError,
    KaiNotFoundError,
    KaiRateLimitError,
)


@pytest.fixture
def client():
    """Create a KaiClient instance for testing."""
    return KaiClient(
        storage_api_token="test-token",
        storage_api_url="https://connection.test.keboola.com",
        base_url="http://localhost:3000",
    )


class TestKaiClientInit:
    """Tests for KaiClient initialization."""

    def test_default_base_url(self):
        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
        )
        assert client.base_url == "http://localhost:3000"

    def test_custom_base_url(self):
        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
            base_url="https://kai.example.com/",
        )
        assert client.base_url == "https://kai.example.com"

    def test_custom_timeouts(self):
        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
            timeout=60.0,
            stream_timeout=120.0,
        )
        assert client.timeout == 60.0
        assert client.stream_timeout == 120.0


class TestUUIDGeneration:
    """Tests for UUID generation methods."""

    def test_new_chat_id_format(self):
        chat_id = KaiClient.new_chat_id()
        # Should be a valid UUID
        uuid.UUID(chat_id)

    def test_new_chat_id_unique(self):
        ids = [KaiClient.new_chat_id() for _ in range(100)]
        assert len(set(ids)) == 100

    def test_new_message_id_format(self):
        message_id = KaiClient.new_message_id()
        uuid.UUID(message_id)

    def test_new_message_id_unique(self):
        ids = [KaiClient.new_message_id() for _ in range(100)]
        assert len(set(ids)) == 100


class TestPing:
    """Tests for the ping endpoint."""

    @pytest.mark.asyncio
    async def test_ping_success(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/ping",
            json={"timestamp": "2025-12-24T16:24:10.641Z"},
        )

        async with client:
            response = await client.ping()

        assert response.timestamp.year == 2025
        assert response.timestamp.month == 12

    @pytest.mark.asyncio
    async def test_ping_no_auth_headers(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Ping should not send auth headers."""
        httpx_mock.add_response(
            url="http://localhost:3000/ping",
            json={"timestamp": "2025-12-24T16:24:10.641Z"},
        )

        async with client:
            await client.ping()

        request = httpx_mock.get_request()
        assert "x-storageapi-token" not in request.headers
        assert "x-storageapi-url" not in request.headers


class TestInfo:
    """Tests for the info endpoint."""

    @pytest.mark.asyncio
    async def test_info_success(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api",
            json={
                "timestamp": "2025-12-24T16:24:10.641Z",
                "uptime": 12345.67,
                "appName": "kai-backend",
                "appVersion": "1.0.0",
                "serverVersion": "2.0.0",
                "connectedMcp": [
                    {"name": "keboola-mcp", "status": "connected"}
                ],
            },
        )

        async with client:
            response = await client.info()

        assert response.app_name == "kai-backend"
        assert response.app_version == "1.0.0"
        assert len(response.connected_mcp) == 1


class TestGetChat:
    """Tests for get_chat endpoint."""

    @pytest.mark.asyncio
    async def test_get_chat_success(self, client: KaiClient, httpx_mock: HTTPXMock):
        chat_id = "chat-123"
        httpx_mock.add_response(
            url=f"http://localhost:3000/api/chat/{chat_id}",
            json={
                "id": chat_id,
                "title": "Test Chat",
                "messages": [
                    {"id": "msg-1", "role": "user", "parts": []},
                    {"id": "msg-2", "role": "assistant", "parts": []},
                ],
            },
        )

        async with client:
            chat = await client.get_chat(chat_id)

        assert chat.id == chat_id
        assert chat.title == "Test Chat"
        assert len(chat.messages) == 2

    @pytest.mark.asyncio
    async def test_get_chat_includes_auth(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            json={"id": "chat-123", "messages": []},
        )

        async with client:
            await client.get_chat("chat-123")

        request = httpx_mock.get_request()
        assert request.headers["x-storageapi-token"] == "test-token"
        assert request.headers["x-storageapi-url"] == "https://connection.test.keboola.com"


class TestDeleteChat:
    """Tests for delete_chat endpoint."""

    @pytest.mark.asyncio
    async def test_delete_chat_success(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat?id=chat-123",
            method="DELETE",
            status_code=200,
            json={},
        )

        async with client:
            await client.delete_chat("chat-123")

        request = httpx_mock.get_request()
        assert request.method == "DELETE"


class TestGetHistory:
    """Tests for get_history endpoint."""

    @pytest.mark.asyncio
    async def test_get_history_success(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/history?limit=10",
            json={
                "chats": [
                    {"id": "chat-1", "title": "Chat 1"},
                    {"id": "chat-2", "title": "Chat 2"},
                ],
                "hasMore": True,
            },
        )

        async with client:
            history = await client.get_history(limit=10)

        assert len(history.chats) == 2
        assert history.has_more is True

    @pytest.mark.asyncio
    async def test_get_history_with_pagination(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/history?limit=20&starting_after=chat-5",
            json={"chats": [], "hasMore": False},
        )

        async with client:
            await client.get_history(limit=20, starting_after="chat-5")

        request = httpx_mock.get_request()
        assert "starting_after=chat-5" in str(request.url)


class TestVoting:
    """Tests for voting endpoints."""

    @pytest.mark.asyncio
    async def test_get_votes(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/vote?chatId=chat-123",
            json=[
                {"chatId": "chat-123", "messageId": "msg-1", "type": "up"},
            ],
        )

        async with client:
            votes = await client.get_votes("chat-123")

        assert len(votes) == 1
        assert votes[0].type == "up"

    @pytest.mark.asyncio
    async def test_vote(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/vote",
            method="PATCH",
            text="Message voted",
        )

        async with client:
            vote = await client.vote("chat-123", "msg-456", "up")

        assert vote.chat_id == "chat-123"
        assert vote.message_id == "msg-456"
        assert vote.type == "up"

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["chatId"] == "chat-123"
        assert body["messageId"] == "msg-456"
        assert body["type"] == "up"

    @pytest.mark.asyncio
    async def test_upvote(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/vote",
            method="PATCH",
            text="Message voted",
        )

        async with client:
            vote = await client.upvote("chat-123", "msg-456")

        assert vote.type == "up"

    @pytest.mark.asyncio
    async def test_downvote(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/vote",
            method="PATCH",
            text="Message voted",
        )

        async with client:
            vote = await client.downvote("chat-123", "msg-456")

        assert vote.type == "down"


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_authentication_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=401,
            json={
                "code": "unauthorized:chat",
                "message": "Invalid token",
            },
        )

        async with client:
            with pytest.raises(KaiAuthenticationError) as exc_info:
                await client.get_chat("chat-123")

        assert exc_info.value.code == "unauthorized:chat"
        assert "Invalid token" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_forbidden_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=403,
            json={
                "code": "forbidden:chat",
                "message": "Access denied",
            },
        )

        async with client:
            with pytest.raises(KaiForbiddenError):
                await client.get_chat("chat-123")

    @pytest.mark.asyncio
    async def test_not_found_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=404,
            json={
                "code": "not_found:chat",
                "message": "Chat not found",
            },
        )

        async with client:
            with pytest.raises(KaiNotFoundError):
                await client.get_chat("chat-123")

    @pytest.mark.asyncio
    async def test_rate_limit_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=429,
            json={
                "code": "rate_limit:chat",
                "message": "Too many requests",
            },
        )

        async with client:
            with pytest.raises(KaiRateLimitError):
                await client.get_chat("chat-123")

    @pytest.mark.asyncio
    async def test_bad_request_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=400,
            json={
                "code": "bad_request:api",
                "message": "Invalid request",
            },
        )

        async with client:
            with pytest.raises(KaiBadRequestError):
                await client.get_chat("chat-123")

    @pytest.mark.asyncio
    async def test_generic_error(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=500,
            json={
                "code": "internal_error",
                "message": "Server error",
            },
        )

        async with client:
            with pytest.raises(KaiError):
                await client.get_chat("chat-123")

    @pytest.mark.asyncio
    async def test_error_with_cause(self, client: KaiClient, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=400,
            json={
                "code": "bad_request:api",
                "message": "Validation failed",
                "cause": "Missing required field: message",
            },
        )

        async with client:
            with pytest.raises(KaiBadRequestError) as exc_info:
                await client.get_chat("chat-123")

        assert exc_info.value.cause == "Missing required field: message"


class TestContextManager:
    """Tests for async context manager functionality."""

    @pytest.mark.asyncio
    async def test_context_manager(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/ping",
            json={"timestamp": "2025-12-24T16:24:10.641Z"},
        )

        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
        )

        async with client:
            await client.ping()

        # Client should be closed after context
        assert client._client is None

    @pytest.mark.asyncio
    async def test_manual_close(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://localhost:3000/ping",
            json={"timestamp": "2025-12-24T16:24:10.641Z"},
        )

        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
        )

        async with client:
            await client.ping()
            await client.close()

        assert client._client is None


class TestSendMessage:
    """Tests for send_message endpoint."""

    @pytest.mark.asyncio
    async def test_send_message_request_format(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test that send_message sends correctly formatted request."""
        sse_response = (
            'data: {"type":"text","text":"Hello"}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.send_message("chat-123", "Hi there"):
                events.append(event)

        # Verify request format
        request = httpx_mock.get_request()
        body = json.loads(request.content)

        assert body["id"] == "chat-123"
        assert body["message"]["role"] == "user"
        assert body["message"]["parts"][0]["type"] == "text"
        assert body["message"]["parts"][0]["text"] == "Hi there"
        assert body["selectedChatModel"] == "chat-model"
        assert body["selectedVisibilityType"] == "private"

    @pytest.mark.asyncio
    async def test_send_message_streams_events(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test that events are properly streamed."""
        sse_response = (
            'data: {"type":"step-start"}\n'
            'data: {"type":"text","text":"Hello "}\n'
            'data: {"type":"text","text":"world!"}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.send_message("chat-123", "Test"):
                events.append(event)

        assert len(events) == 4
        assert events[0].type == "step-start"
        assert events[1].type == "text"
        assert events[1].text == "Hello "
        assert events[2].text == "world!"
        assert events[3].type == "finish"


class TestChat:
    """Tests for the convenience chat method."""

    @pytest.mark.asyncio
    async def test_chat_returns_full_response(self, client: KaiClient, httpx_mock: HTTPXMock):
        sse_response = (
            'data: {"type":"text","text":"The answer "}\n'
            'data: {"type":"text","text":"is 42."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            chat_id, response = await client.chat("What is the answer?")

        assert response == "The answer is 42."
        # Chat ID should be a valid UUID
        uuid.UUID(chat_id)

    @pytest.mark.asyncio
    async def test_chat_with_existing_id(self, client: KaiClient, httpx_mock: HTTPXMock):
        sse_response = 'data: {"type":"finish","finishReason":"stop"}\n'

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            chat_id, _ = await client.chat("Test", chat_id="existing-chat-id")

        assert chat_id == "existing-chat-id"


class TestToolApproval:
    """Tests for tool approval functionality."""

    @pytest.mark.asyncio
    async def test_send_tool_result_request_format(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test that send_tool_result sends correctly formatted request."""
        sse_response = (
            'data: {"type":"text","text":"Tool executed successfully."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.send_tool_result(
                chat_id="chat-123",
                tool_call_id="tool-call-456",
                tool_name="create_bucket",
                result="confirmed",
            ):
                events.append(event)

        # Verify request format
        request = httpx_mock.get_request()
        body = json.loads(request.content)

        assert body["id"] == "chat-123"
        assert body["message"]["role"] == "user"
        assert len(body["message"]["parts"]) == 1

        part = body["message"]["parts"][0]
        assert part["type"] == "tool-result"
        assert part["toolCallId"] == "tool-call-456"
        assert part["toolName"] == "create_bucket"
        assert part["result"] == "confirmed"

    @pytest.mark.asyncio
    async def test_send_tool_result_denied(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test sending a denial result."""
        sse_response = (
            'data: {"type":"text","text":"Understood, I won\'t proceed."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.send_tool_result(
                chat_id="chat-123",
                tool_call_id="tool-call-456",
                tool_name="delete_bucket",
                result="denied",
            ):
                events.append(event)

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["message"]["parts"][0]["result"] == "denied"

    @pytest.mark.asyncio
    async def test_confirm_tool_sends_confirmed(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test that confirm_tool sends 'confirmed' as the result."""
        sse_response = 'data: {"type":"finish","finishReason":"stop"}\n'

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            async for _ in client.confirm_tool(
                chat_id="chat-123",
                tool_call_id="tool-456",
                tool_name="run_job",
            ):
                pass

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["message"]["parts"][0]["result"] == "confirmed"
        assert body["message"]["parts"][0]["toolCallId"] == "tool-456"
        assert body["message"]["parts"][0]["toolName"] == "run_job"

    @pytest.mark.asyncio
    async def test_deny_tool_sends_denied(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test that deny_tool sends 'denied' as the result."""
        sse_response = 'data: {"type":"finish","finishReason":"stop"}\n'

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            async for _ in client.deny_tool(
                chat_id="chat-123",
                tool_call_id="tool-789",
                tool_name="create_config",
            ):
                pass

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["message"]["parts"][0]["result"] == "denied"
        assert body["message"]["parts"][0]["toolCallId"] == "tool-789"
        assert body["message"]["parts"][0]["toolName"] == "create_config"

    @pytest.mark.asyncio
    async def test_tool_result_streams_events(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test that tool result properly streams response events."""
        tool_event = (
            '{"type":"tool-call","toolCallId":"tool-456","toolName":"create_bucket",'
            '"state":"output-available","output":{"bucket_id":"new-bucket"}}'
        )
        sse_response = (
            f'data: {tool_event}\n'
            'data: {"type":"text","text":"I created the bucket."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.confirm_tool(
                chat_id="chat-123",
                tool_call_id="tool-456",
                tool_name="create_bucket",
            ):
                events.append(event)

        assert len(events) == 3
        assert events[0].type == "tool-call"
        assert events[0].state == "output-available"
        assert events[1].type == "text"
        assert events[1].text == "I created the bucket."
        assert events[2].type == "finish"

    @pytest.mark.asyncio
    async def test_tool_result_includes_auth_headers(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test that tool result requests include authentication headers."""
        sse_response = 'data: {"type":"finish","finishReason":"stop"}\n'

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            async for _ in client.confirm_tool(
                chat_id="chat-123",
                tool_call_id="tool-456",
                tool_name="test_tool",
            ):
                pass

        request = httpx_mock.get_request()
        assert request.headers["x-storageapi-token"] == "test-token"
        assert request.headers["x-storageapi-url"] == "https://connection.test.keboola.com"


class TestFromStorageApi:
    """Tests for from_storage_api factory method."""

    @pytest.mark.asyncio
    async def test_from_storage_api_success(self, httpx_mock: HTTPXMock):
        """Test successful URL discovery from Storage API."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            json={
                "services": [
                    {"id": "kai-assistant", "url": "https://kai.keboola.com"},
                    {"id": "other-service", "url": "https://other.keboola.com"},
                ]
            },
        )

        client = await KaiClient.from_storage_api(
            storage_api_token="test-token",
            storage_api_url="https://connection.keboola.com",
        )

        assert client.base_url == "https://kai.keboola.com"
        assert client.storage_api_token == "test-token"
        await client.close()

    @pytest.mark.asyncio
    async def test_from_storage_api_service_not_found(self, httpx_mock: HTTPXMock):
        """Test error when kai-assistant service is not in the list."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            json={
                "services": [
                    {"id": "other-service", "url": "https://other.keboola.com"},
                ]
            },
        )

        with pytest.raises(KaiError) as exc_info:
            await KaiClient.from_storage_api(
                storage_api_token="test-token",
                storage_api_url="https://connection.keboola.com",
            )

        assert "kai-assistant service not found" in str(exc_info.value)
        assert exc_info.value.code == "discovery:service_not_found"

    @pytest.mark.asyncio
    async def test_from_storage_api_no_url(self, httpx_mock: HTTPXMock):
        """Test error when kai-assistant service has no URL."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            json={
                "services": [
                    {"id": "kai-assistant"},  # No URL
                ]
            },
        )

        with pytest.raises(KaiError) as exc_info:
            await KaiClient.from_storage_api(
                storage_api_token="test-token",
                storage_api_url="https://connection.keboola.com",
            )

        assert "no URL" in str(exc_info.value)
        assert exc_info.value.code == "discovery:no_url"

    @pytest.mark.asyncio
    async def test_from_storage_api_http_error(self, httpx_mock: HTTPXMock):
        """Test error when Storage API returns HTTP error."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            status_code=401,
            json={"message": "Unauthorized"},
        )

        with pytest.raises(KaiError) as exc_info:
            await KaiClient.from_storage_api(
                storage_api_token="bad-token",
                storage_api_url="https://connection.keboola.com",
            )

        assert "HTTP 401" in str(exc_info.value)
        assert exc_info.value.code == "discovery:http_error"

    @pytest.mark.asyncio
    async def test_from_storage_api_custom_timeouts(self, httpx_mock: HTTPXMock):
        """Test that custom timeouts are passed to the client."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            json={
                "services": [
                    {"id": "kai-assistant", "url": "https://kai.keboola.com"},
                ]
            },
        )

        client = await KaiClient.from_storage_api(
            storage_api_token="test-token",
            storage_api_url="https://connection.keboola.com",
            timeout=60.0,
            stream_timeout=120.0,
        )

        assert client.timeout == 60.0
        assert client.stream_timeout == 120.0
        await client.close()


class TestGetAllHistory:
    """Tests for get_all_history pagination method."""

    @pytest.mark.asyncio
    async def test_get_all_history_single_page(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test iteration when all results fit in one page."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/history?limit=100",
            json={
                "chats": [
                    {"id": "chat-1", "title": "Chat 1"},
                    {"id": "chat-2", "title": "Chat 2"},
                ],
                "hasMore": False,
            },
        )

        async with client:
            chats = [chat async for chat in client.get_all_history()]

        assert len(chats) == 2
        assert chats[0].id == "chat-1"
        assert chats[1].id == "chat-2"

    @pytest.mark.asyncio
    async def test_get_all_history_multiple_pages(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test pagination across multiple pages."""
        # First page
        httpx_mock.add_response(
            url="http://localhost:3000/api/history?limit=100",
            json={
                "chats": [
                    {"id": "chat-1", "title": "Chat 1"},
                    {"id": "chat-2", "title": "Chat 2"},
                ],
                "hasMore": True,
            },
        )
        # Second page
        httpx_mock.add_response(
            url="http://localhost:3000/api/history?limit=100&starting_after=chat-2",
            json={
                "chats": [
                    {"id": "chat-3", "title": "Chat 3"},
                ],
                "hasMore": False,
            },
        )

        async with client:
            chats = [chat async for chat in client.get_all_history()]

        assert len(chats) == 3
        assert [c.id for c in chats] == ["chat-1", "chat-2", "chat-3"]

    @pytest.mark.asyncio
    async def test_get_all_history_empty(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test when there's no history."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/history?limit=100",
            json={"chats": [], "hasMore": False},
        )

        async with client:
            chats = [chat async for chat in client.get_all_history()]

        assert len(chats) == 0

    @pytest.mark.asyncio
    async def test_get_all_history_custom_batch_size(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test custom batch size."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/history?limit=50",
            json={"chats": [], "hasMore": False},
        )

        async with client:
            chats = [chat async for chat in client.get_all_history(batch_size=50)]

        assert len(chats) == 0


class TestResumeStream:
    """Tests for resume_stream method."""

    @pytest.mark.asyncio
    async def test_resume_stream_success(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test resuming an active stream."""
        sse_response = (
            'data: {"type":"text","text":"Resumed content"}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123/stream",
            method="GET",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = [event async for event in client.resume_stream("chat-123")]

        assert len(events) == 2
        assert events[0].type == "text"
        assert events[0].text == "Resumed content"

    @pytest.mark.asyncio
    async def test_resume_stream_no_stream_available(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test when no stream is available (204 response)."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123/stream",
            method="GET",
            status_code=204,
        )

        async with client:
            events = [event async for event in client.resume_stream("chat-123")]

        assert len(events) == 0


class TestConnectionErrors:
    """Tests for connection error handling."""

    @pytest.mark.asyncio
    async def test_connection_error(self, httpx_mock: HTTPXMock):
        """Test handling of connection errors."""
        import httpx

        from kai_client import KaiConnectionError

        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="http://localhost:3000/ping",
        )

        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
        )

        async with client:
            with pytest.raises(KaiConnectionError) as exc_info:
                await client.ping()

        assert "Failed to connect" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_timeout_error(self, httpx_mock: HTTPXMock):
        """Test handling of timeout errors."""
        import httpx

        from kai_client import KaiTimeoutError

        httpx_mock.add_exception(
            httpx.TimeoutException("Request timed out"),
            url="http://localhost:3000/api/chat/chat-123",
        )

        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
        )

        async with client:
            with pytest.raises(KaiTimeoutError) as exc_info:
                await client.get_chat("chat-123")

        assert "timed out" in str(exc_info.value)


class TestVotingWithEnum:
    """Tests for voting with VoteType enum."""

    @pytest.mark.asyncio
    async def test_vote_with_enum(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test voting using VoteType enum."""
        from kai_client.types import VoteType

        httpx_mock.add_response(
            url="http://localhost:3000/api/vote",
            method="PATCH",
            text="Message voted",
        )

        async with client:
            vote = await client.vote("chat-123", "msg-456", VoteType.UP)

        assert vote.type == "up"

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["type"] == "up"


class TestSendMessageOptions:
    """Tests for send_message with various options."""

    @pytest.mark.asyncio
    async def test_send_message_with_visibility(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test send_message with visibility type enum."""
        from kai_client.types import VisibilityType

        sse_response = 'data: {"type":"finish","finishReason":"stop"}\n'

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            async for _ in client.send_message(
                "chat-123",
                "Test",
                visibility=VisibilityType.PUBLIC,
            ):
                pass

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["selectedVisibilityType"] == "public"

    @pytest.mark.asyncio
    async def test_send_message_with_branch_id(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test send_message with branch ID."""
        sse_response = 'data: {"type":"finish","finishReason":"stop"}\n'

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            async for _ in client.send_message(
                "chat-123",
                "Test",
                branch_id=12345,
            ):
                pass

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["branchId"] == 12345

    @pytest.mark.asyncio
    async def test_send_message_with_metadata(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test send_message with hidden and request_path metadata."""
        sse_response = 'data: {"type":"finish","finishReason":"stop"}\n'

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            async for _ in client.send_message(
                "chat-123",
                "Test",
                hidden=True,
                request_path="/some/path",
            ):
                pass

        request = httpx_mock.get_request()
        body = json.loads(request.content)
        assert body["message"]["metadata"]["hidden"] is True
        assert body["message"]["metadata"]["requestContext"]["path"] == "/some/path"


class TestStreamErrorHandling:
    """Tests for streaming error handling."""

    @pytest.mark.asyncio
    async def test_stream_http_error_with_json(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test error handling when stream endpoint returns JSON error."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            status_code=400,
            json={
                "code": "bad_request:api",
                "message": "Invalid message format",
            },
        )

        async with client:
            with pytest.raises(KaiBadRequestError) as exc_info:
                async for _ in client.send_message("chat-123", "Test"):
                    pass

        assert exc_info.value.code == "bad_request:api"

    @pytest.mark.asyncio
    async def test_stream_http_error_plain_text(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test error handling when stream endpoint returns plain text error."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            status_code=500,
            content=b"Internal Server Error",
        )

        async with client:
            with pytest.raises(KaiError) as exc_info:
                async for _ in client.send_message("chat-123", "Test"):
                    pass

        assert "500" in str(exc_info.value)


class TestGetVotesFormats:
    """Tests for get_votes with different response formats."""

    @pytest.mark.asyncio
    async def test_get_votes_list_format(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test get_votes when API returns a list directly."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/vote?chatId=chat-123",
            json=[
                {"chatId": "chat-123", "messageId": "msg-1", "type": "up"},
            ],
        )

        async with client:
            votes = await client.get_votes("chat-123")

        assert len(votes) == 1

    @pytest.mark.asyncio
    async def test_get_votes_object_format(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test get_votes when API returns an object with votes field."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/vote?chatId=chat-123",
            json={
                "votes": [
                    {"chatId": "chat-123", "messageId": "msg-1", "type": "up"},
                ]
            },
        )

        async with client:
            votes = await client.get_votes("chat-123")

        assert len(votes) == 1


class TestToolOutputError:
    """Tests for handling tool output error events."""

    @pytest.mark.asyncio
    async def test_tool_output_error_event(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test that tool-output-error events are properly streamed."""
        tool_error_event = (
            '{"type":"tool-output-error","toolCallId":"tool-123",'
            '"errorText":"Tool execution failed: Connection timeout"}'
        )
        sse_response = (
            f'data: {tool_error_event}\n'
            'data: {"type":"text","text":"The tool failed. Let me try another approach."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.send_message("chat-123", "Test"):
                events.append(event)

        assert len(events) == 3
        assert events[0].type == "tool-output-error"
        assert events[0].tool_call_id == "tool-123"
        assert events[0].error_text == "Tool execution failed: Connection timeout"
        assert events[1].type == "text"
        assert events[2].type == "finish"

    @pytest.mark.asyncio
    async def test_tool_output_error_after_confirmation(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test tool error after user confirmation."""
        sse_response = (
            'data: {"type":"tool-output-error","toolCallId":"tool-456",'
            '"errorText":"No execute function found for tool create_bucket"}\n'
            'data: {"type":"text","text":"I encountered an error with that tool."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.confirm_tool(
                chat_id="chat-123",
                tool_call_id="tool-456",
                tool_name="create_bucket",
            ):
                events.append(event)

        # Should receive error event followed by text and finish
        assert events[0].type == "tool-output-error"
        assert "No execute function found" in events[0].error_text


class TestToolApprovalWorkflow:
    """Tests for complete tool approval workflow scenarios."""

    @pytest.mark.asyncio
    async def test_full_tool_approval_workflow(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test complete workflow: message -> tool call -> approval -> result."""
        # First response: tool call waiting for approval
        first_response = (
            'data: {"type":"text","text":"I will create a bucket for you."}\n'
            'data: {"type":"tool-input-start","toolCallId":"call-001","toolName":"create_bucket"}\n'
            'data: {"type":"tool-input-available","toolCallId":"call-001",'
            '"toolName":"create_bucket","input":{"name":"test-bucket"}}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        # Second response: after approval
        second_response = (
            'data: {"type":"tool-output-available","toolCallId":"call-001",'
            '"toolName":"create_bucket","output":{"bucket_id":"in.c-test"}}\n'
            'data: {"type":"text","text":"I created the bucket successfully."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=first_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            # First message: should receive tool call waiting for approval
            events = []
            pending_tool = None
            async for event in client.send_message("chat-123", "Create a bucket"):
                events.append(event)
                if event.type == "tool-call" and event.state == "input-available":
                    pending_tool = event

            assert pending_tool is not None
            assert pending_tool.tool_name == "create_bucket"

            # Add second response for confirmation
            httpx_mock.add_response(
                url="http://localhost:3000/api/chat",
                method="POST",
                content=second_response.encode(),
                headers={"content-type": "text/event-stream"},
            )

            # Confirm the tool
            confirm_events = []
            async for event in client.confirm_tool(
                chat_id="chat-123",
                tool_call_id=pending_tool.tool_call_id,
                tool_name=pending_tool.tool_name,
            ):
                confirm_events.append(event)

            # Should receive output-available with result
            assert confirm_events[0].type == "tool-call"
            assert confirm_events[0].state == "output-available"
            assert confirm_events[0].output["bucket_id"] == "in.c-test"

    @pytest.mark.asyncio
    async def test_tool_denial_workflow(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test workflow when user denies tool execution."""
        # Response after denial
        denial_response = (
            'data: {"type":"tool-output-available","toolCallId":"call-002",'
            '"toolName":"delete_bucket","output":{"_declined":true,'
            '"message":"User declined to execute the tool call."}}\n'
            'data: {"type":"text","text":"Understood, I won\'t delete the bucket."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=denial_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.deny_tool(
                chat_id="chat-123",
                tool_call_id="call-002",
                tool_name="delete_bucket",
            ):
                events.append(event)

            # Should receive declined output
            assert events[0].type == "tool-call"
            assert events[0].output["_declined"] is True

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_sequence(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test handling multiple sequential tool calls."""
        sse_response = (
            'data: {"type":"text","text":"I will query the tables."}\n'
            # First tool call (pre-approved, no confirmation needed)
            'data: {"type":"tool-input-start","toolCallId":"call-001","toolName":"get_tables"}\n'
            'data: {"type":"tool-output-available","toolCallId":"call-001",'
            '"toolName":"get_tables","output":{"tables":["users","orders"]}}\n'
            # Second tool call (pre-approved)
            'data: {"type":"tool-input-start","toolCallId":"call-002","toolName":"get_buckets"}\n'
            'data: {"type":"tool-output-available","toolCallId":"call-002",'
            '"toolName":"get_buckets","output":{"buckets":["in.c-main"]}}\n'
            'data: {"type":"text","text":"Found 2 tables and 1 bucket."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            tool_calls = []
            async for event in client.send_message("chat-123", "List my data"):
                if event.type == "tool-call":
                    tool_calls.append(event)

            # Should have 4 tool events (2 started + 2 output-available)
            assert len(tool_calls) == 4
            # First tool
            assert tool_calls[0].tool_name == "get_tables"
            assert tool_calls[0].state == "started"
            assert tool_calls[1].state == "output-available"
            # Second tool
            assert tool_calls[2].tool_name == "get_buckets"
            assert tool_calls[3].output["buckets"] == ["in.c-main"]


class TestAllBackendTools:
    """Tests to verify client can handle all backend tool types."""

    # Preapproved tools (read-only) from backend
    PREAPPROVED_TOOLS = [
        "get_components",
        "get_config_examples",
        "get_configs",
        "docs_query",
        "get_flow_examples",
        "get_flow_schema",
        "get_flows",
        "get_jobs",
        "get_data_apps",
        "get_project_info",
        "query_data",
        "find_component_id",
        "search",
        "get_buckets",
        "get_tables",
    ]

    # Write tools (require confirmation) from backend
    WRITE_TOOLS = [
        "add_config_row",
        "create_config",
        "create_sql_transformation",
        "update_config",
        "update_config_row",
        "update_sql_transformation",
        "create_flow",
        "create_conditional_flow",
        "update_flow",
        "run_job",
        "create_oauth_url",
        "deploy_data_app",
        "modify_data_app",
        "update_descriptions",
    ]

    @pytest.mark.asyncio
    async def test_preapproved_tool_flow(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test that preapproved tools return output directly."""
        for tool_name in self.PREAPPROVED_TOOLS[:3]:  # Test first 3
            sse_response = (
                f'data: {{"type":"tool-input-start","toolCallId":"call-{tool_name}",'
                f'"toolName":"{tool_name}"}}\n'
                f'data: {{"type":"tool-output-available","toolCallId":"call-{tool_name}",'
                f'"toolName":"{tool_name}","output":{{"result":"data"}}}}\n'
                'data: {"type":"finish","finishReason":"stop"}\n'
            )

            httpx_mock.add_response(
                url="http://localhost:3000/api/chat",
                method="POST",
                content=sse_response.encode(),
                headers={"content-type": "text/event-stream"},
            )

            async with client:
                events = []
                async for event in client.send_message(f"chat-{tool_name}", "Test"):
                    events.append(event)

                # Find tool output event
                output_events = [e for e in events if e.type == "tool-call"
                                 and getattr(e, 'state', None) == "output-available"]
                assert len(output_events) == 1
                assert output_events[0].tool_name == tool_name

    @pytest.mark.asyncio
    async def test_write_tool_requires_approval(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test that write tools wait for approval (input-available state)."""
        tool_name = "create_config"
        sse_response = (
            f'data: {{"type":"tool-input-start","toolCallId":"call-{tool_name}",'
            f'"toolName":"{tool_name}"}}\n'
            f'data: {{"type":"tool-input-available","toolCallId":"call-{tool_name}",'
            f'"toolName":"{tool_name}","input":{{"name":"new-config"}}}}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )

        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            pending_tools = []
            async for event in client.send_message("chat-123", "Create config"):
                if event.type == "tool-call" and getattr(event, 'state', None) == "input-available":
                    pending_tools.append(event)

            # Should have a pending tool awaiting approval
            assert len(pending_tools) == 1
            assert pending_tools[0].tool_name == tool_name
            assert pending_tools[0].input is not None


class TestFromStorageApiConnectionError:
    """Tests for from_storage_api when connection fails."""

    @pytest.mark.asyncio
    async def test_from_storage_api_connection_error(self, httpx_mock: HTTPXMock):
        """Test error when Storage API is unreachable."""
        import httpx as httpx_lib

        from kai_client import KaiConnectionError

        httpx_mock.add_exception(
            httpx_lib.RequestError("Connection refused"),
            url="https://connection.keboola.com/v2/storage",
        )

        with pytest.raises(KaiConnectionError) as exc_info:
            await KaiClient.from_storage_api(
                storage_api_token="test-token",
                storage_api_url="https://connection.keboola.com",
            )

        assert "Failed to connect to Storage API" in str(exc_info.value)


class TestLazyClientInit:
    """Tests for lazy client initialization (without context manager)."""

    @pytest.mark.asyncio
    async def test_get_client_creates_client_lazily(self, httpx_mock: HTTPXMock):
        """Test that _get_client creates client on first use."""
        httpx_mock.add_response(
            url="http://localhost:3000/ping",
            json={"timestamp": "2025-12-24T16:24:10.641Z"},
        )

        client = KaiClient(
            storage_api_token="token",
            storage_api_url="https://connection.keboola.com",
        )

        # No context manager — lazy init
        assert client._client is None
        await client.ping()
        assert client._client is not None
        await client.close()


class TestNonJsonHttpError:
    """Tests for HTTP errors with non-JSON response bodies."""

    @pytest.mark.asyncio
    async def test_non_json_error_response(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test _request when server returns non-JSON error body."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            status_code=502,
            content=b"Bad Gateway",
        )

        async with client:
            with pytest.raises(KaiError) as exc_info:
                await client.get_chat("chat-123")

        assert "502" in str(exc_info.value)
        assert exc_info.value.code == "http:502"


class TestStreamRequestErrorEdgeCases:
    """Tests for _stream_request error handling edge cases."""

    @pytest.mark.asyncio
    async def test_stream_error_empty_body_uses_reason_phrase(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test streaming error with empty body falls back to reason phrase."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            status_code=503,
            content=b"",
        )

        async with client:
            with pytest.raises(KaiError) as exc_info:
                async for _ in client.send_message("chat-123", "Test"):
                    pass

        assert "503" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_stream_error_non_json_body(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test streaming error with non-JSON body that starts with '{'."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            status_code=500,
            content=b"{broken json",
        )

        async with client:
            with pytest.raises(KaiError) as exc_info:
                async for _ in client.send_message("chat-123", "Test"):
                    pass

        assert "500" in str(exc_info.value)


class TestV6ToolApprovalFlow:
    """Tests for the Vercel AI SDK v6 tool approval flow."""

    @pytest.mark.asyncio
    async def test_send_tool_approval_response_approve(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test approving a tool via the v6 flow."""
        # Mock get_chat to return assistant message with pending approval
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            json={
                "id": "chat-123",
                "messages": [
                    {
                        "id": "msg-user",
                        "role": "user",
                        "parts": [{"type": "text", "text": "Update descriptions"}],
                    },
                    {
                        "id": "msg-assistant",
                        "role": "assistant",
                        "parts": [
                            {"type": "text", "text": "I'll update the descriptions."},
                            {
                                "type": "tool-update_descriptions",
                                "toolCallId": "call-001",
                                "state": "approval-required",
                                "approval": {
                                    "id": "approval-abc",
                                    "approved": None,
                                },
                                "input": {"descriptions": "new desc"},
                            },
                        ],
                    },
                ],
            },
        )

        # Mock the streaming response after approval
        sse_response = (
            'data: {"type":"text","text":"Descriptions updated."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.send_tool_approval_response(
                chat_id="chat-123",
                approval_id="approval-abc",
                approved=True,
            ):
                events.append(event)

        assert len(events) == 2
        assert events[0].type == "text"
        assert events[0].text == "Descriptions updated."

        # Verify the POST payload has the updated assistant message
        requests = httpx_mock.get_requests()
        post_request = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_request.content)
        assert body["id"] == "chat-123"
        assert body["message"]["id"] == "msg-assistant"
        assert body["message"]["role"] == "assistant"

        # Find the updated tool part
        tool_parts = [p for p in body["message"]["parts"] if "approval" in p]
        assert len(tool_parts) == 1
        assert tool_parts[0]["state"] == "approval-responded"
        assert tool_parts[0]["approval"]["approved"] is True

    @pytest.mark.asyncio
    async def test_send_tool_approval_response_reject_with_reason(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test rejecting a tool with a reason via the v6 flow."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            json={
                "id": "chat-123",
                "messages": [
                    {
                        "id": "msg-assistant",
                        "role": "assistant",
                        "parts": [
                            {
                                "type": "tool-delete_bucket",
                                "toolCallId": "call-002",
                                "state": "approval-required",
                                "approval": {"id": "approval-def"},
                                "input": {"bucket_id": "in.c-test"},
                            },
                        ],
                    },
                ],
            },
        )

        sse_response = (
            'data: {"type":"text","text":"Understood, I won\'t delete it."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.send_tool_approval_response(
                chat_id="chat-123",
                approval_id="approval-def",
                approved=False,
                reason="Too dangerous",
            ):
                events.append(event)

        # Verify rejection payload
        requests = httpx_mock.get_requests()
        post_request = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_request.content)
        tool_part = body["message"]["parts"][0]
        assert tool_part["approval"]["approved"] is False
        assert tool_part["approval"]["reason"] == "Too dangerous"

    @pytest.mark.asyncio
    async def test_send_tool_approval_response_not_found(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test error when approval ID is not found in chat messages."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            json={
                "id": "chat-123",
                "messages": [
                    {
                        "id": "msg-user",
                        "role": "user",
                        "parts": [{"type": "text", "text": "Hello"}],
                    },
                ],
            },
        )

        async with client:
            with pytest.raises(KaiError) as exc_info:
                async for _ in client.send_tool_approval_response(
                    chat_id="chat-123",
                    approval_id="nonexistent-approval",
                    approved=True,
                ):
                    pass

        assert exc_info.value.code == "approval:not_found"

    @pytest.mark.asyncio
    async def test_send_tool_approval_response_with_branch_id(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test v6 approval with branch_id parameter."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            json={
                "id": "chat-123",
                "messages": [
                    {
                        "id": "msg-assistant",
                        "role": "assistant",
                        "parts": [
                            {
                                "type": "tool-create_config",
                                "toolCallId": "call-003",
                                "state": "approval-required",
                                "approval": {"id": "approval-xyz"},
                                "input": {"name": "test"},
                            },
                        ],
                    },
                ],
            },
        )

        sse_response = 'data: {"type":"finish","finishReason":"stop"}\n'
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            async for _ in client.send_tool_approval_response(
                chat_id="chat-123",
                approval_id="approval-xyz",
                approved=True,
                branch_id=42,
            ):
                pass

        requests = httpx_mock.get_requests()
        post_request = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_request.content)
        assert body["branchId"] == 42


class TestApproveRejectToolConvenience:
    """Tests for approve_tool and reject_tool convenience methods."""

    @pytest.mark.asyncio
    async def test_approve_tool(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test approve_tool convenience method."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            json={
                "id": "chat-123",
                "messages": [
                    {
                        "id": "msg-a",
                        "role": "assistant",
                        "parts": [
                            {
                                "type": "tool-run_job",
                                "toolCallId": "call-010",
                                "state": "approval-required",
                                "approval": {"id": "appr-001"},
                                "input": {"job_id": "123"},
                            },
                        ],
                    },
                ],
            },
        )

        sse_response = (
            'data: {"type":"text","text":"Job started."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.approve_tool(
                chat_id="chat-123",
                approval_id="appr-001",
            ):
                events.append(event)

        assert len(events) == 2
        assert events[0].text == "Job started."

        # Verify approved=True was sent
        requests = httpx_mock.get_requests()
        post_request = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_request.content)
        tool_part = body["message"]["parts"][0]
        assert tool_part["approval"]["approved"] is True

    @pytest.mark.asyncio
    async def test_reject_tool(self, client: KaiClient, httpx_mock: HTTPXMock):
        """Test reject_tool convenience method."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat/chat-123",
            json={
                "id": "chat-123",
                "messages": [
                    {
                        "id": "msg-a",
                        "role": "assistant",
                        "parts": [
                            {
                                "type": "tool-deploy_data_app",
                                "toolCallId": "call-020",
                                "state": "approval-required",
                                "approval": {"id": "appr-002"},
                                "input": {"app_id": "456"},
                            },
                        ],
                    },
                ],
            },
        )

        sse_response = (
            'data: {"type":"text","text":"OK, cancelled."}\n'
            'data: {"type":"finish","finishReason":"stop"}\n'
        )
        httpx_mock.add_response(
            url="http://localhost:3000/api/chat",
            method="POST",
            content=sse_response.encode(),
            headers={"content-type": "text/event-stream"},
        )

        async with client:
            events = []
            async for event in client.reject_tool(
                chat_id="chat-123",
                approval_id="appr-002",
                reason="Not needed",
            ):
                events.append(event)

        assert events[0].text == "OK, cancelled."

        requests = httpx_mock.get_requests()
        post_request = [r for r in requests if r.method == "POST"][0]
        body = json.loads(post_request.content)
        tool_part = body["message"]["parts"][0]
        assert tool_part["approval"]["approved"] is False
        assert tool_part["approval"]["reason"] == "Not needed"


class TestGetHistoryEndingBefore:
    """Tests for get_history with ending_before parameter."""

    @pytest.mark.asyncio
    async def test_get_history_with_ending_before(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test backward pagination with ending_before."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/history?limit=10&ending_before=chat-10",
            json={"chats": [{"id": "chat-9"}], "hasMore": True},
        )

        async with client:
            history = await client.get_history(limit=10, ending_before="chat-10")

        assert len(history.chats) == 1
        request = httpx_mock.get_request()
        assert "ending_before=chat-10" in str(request.url)


class TestParseVoteIsUpvotedFormat:
    """Tests for _parse_vote with isUpvoted response format."""

    def test_parse_vote_is_upvoted_true(self):
        """Test parsing vote in isUpvoted format (upvoted)."""
        data = {"chatId": "chat-1", "messageId": "msg-1", "isUpvoted": True}
        vote = KaiClient._parse_vote(data)
        assert vote.type == "up"
        assert vote.chat_id == "chat-1"
        assert vote.message_id == "msg-1"

    def test_parse_vote_is_upvoted_false(self):
        """Test parsing vote in isUpvoted format (downvoted)."""
        data = {"chatId": "chat-1", "messageId": "msg-1", "isUpvoted": False}
        vote = KaiClient._parse_vote(data)
        assert vote.type == "down"

    def test_parse_vote_is_upvoted_missing(self):
        """Test parsing vote in isUpvoted format when field is missing."""
        data = {"chatId": "chat-1", "messageId": "msg-1"}
        vote = KaiClient._parse_vote(data)
        assert vote.type == "down"  # Default when isUpvoted missing

    @pytest.mark.asyncio
    async def test_get_votes_is_upvoted_format(
        self, client: KaiClient, httpx_mock: HTTPXMock
    ):
        """Test get_votes when API returns isUpvoted format."""
        httpx_mock.add_response(
            url="http://localhost:3000/api/vote?chatId=chat-123",
            json=[
                {"chatId": "chat-123", "messageId": "msg-1", "isUpvoted": True},
                {"chatId": "chat-123", "messageId": "msg-2", "isUpvoted": False},
            ],
        )

        async with client:
            votes = await client.get_votes("chat-123")

        assert len(votes) == 2
        assert votes[0].type == "up"
        assert votes[1].type == "down"



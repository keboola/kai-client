"""Main Kai client implementation."""

import uuid
from contextlib import asynccontextmanager
from json import JSONDecodeError
from types import TracebackType
from typing import Any, AsyncIterator, Optional, Union

import httpx

from kai_client.exceptions import (
    KaiConnectionError,
    KaiError,
    KaiTimeoutError,
    raise_for_error_response,
)
from kai_client.models import (
    AgentSettings,
    ApprovalResponse,
    Chat,
    ChatDetail,
    ChatRequest,
    HistoryResponse,
    InfoResponse,
    MessageMetadata,
    MessageRequest,
    PingResponse,
    RequestContext,
    SSEEvent,
    SuggestionsResponse,
    TextPart,
    ToolInfo,
    ToolResultPart,
    ToolsListResponse,
    UsageResponse,
    UserAgentSettings,
    Vote,
    VoteRequest,
)
from kai_client.sse import parse_sse_stream
from kai_client.types import VisibilityType, VoteType

# Sentinel for "caller did not pass this argument" — distinct from None (explicit clear).
_UNSET: Any = object()


def _normalize_visibility(visibility: str | VisibilityType) -> str:
    """Convert visibility to string value."""
    if isinstance(visibility, VisibilityType):
        return visibility.value
    return visibility


class KaiClient:
    """
    Async client for the Keboola AI Assistant Backend API.

    This client provides methods for interacting with all API endpoints,
    including chat creation, message streaming, history management, and voting.

    Example:
        ```python
        # Local development
        async with KaiClient(
            storage_api_token="your-token",
            storage_api_url="https://connection.canary-orion.keboola.dev"
        ) as client:
            # Start a new chat
            chat_id = client.new_chat_id()

            # Send a message and stream the response
            async for event in client.send_message(chat_id, "Hello!"):
                if event.type == "text":
                    print(event.text, end="", flush=True)

        # Production (auto-discovers kai-assistant URL)
        client = await KaiClient.from_storage_api(
            storage_api_token="your-token",
            storage_api_url="https://connection.keboola.com"
        )
        async with client:
            chat_id, response = await client.chat("Hello!")
        ```
    """

    @classmethod
    async def from_storage_api(
        cls,
        storage_api_token: str,
        storage_api_url: str,
        timeout: float = 300.0,
        stream_timeout: float = 600.0,
    ) -> "KaiClient":
        """
        Auto-discover the kai-assistant URL from the Keboola Storage API.

        This factory method queries the Storage API to find the kai-assistant
        service URL for your stack, then creates a client configured for production.

        Args:
            storage_api_token: Keboola Storage API token for authentication.
            storage_api_url: Keboola Storage API URL (e.g., https://connection.keboola.com).
            timeout: Default timeout for non-streaming requests in seconds.
            stream_timeout: Timeout for streaming requests in seconds.

        Returns:
            A configured KaiClient instance.

        Raises:
            KaiError: If the kai-assistant service is not found or discovery fails.

        Example:
            ```python
            client = await KaiClient.from_storage_api(
                storage_api_token="your-token",
                storage_api_url="https://connection.us-east4.gcp.keboola.com"
            )
            ```
        """
        async with httpx.AsyncClient() as http_client:
            try:
                response = await http_client.get(
                    f"{storage_api_url.rstrip('/')}/v2/storage",
                    headers={"x-storageapi-token": storage_api_token},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
            except httpx.HTTPStatusError as e:
                raise KaiError(
                    message=f"Failed to discover kai-assistant URL: HTTP {e.response.status_code}",
                    code="discovery:http_error",
                ) from e
            except httpx.RequestError as e:
                raise KaiConnectionError(
                    message=f"Failed to connect to Storage API: {storage_api_url}",
                    cause=str(e),
                ) from e

        services = data.get("services", [])
        kai_service = next(
            (s for s in services if s.get("id") == "kai-assistant"),
            None,
        )

        if not kai_service:
            available = [s.get("id") for s in services]
            raise KaiError(
                message=f"kai-assistant service not found. Available services: {available}",
                code="discovery:service_not_found",
            )

        kai_url = kai_service.get("url")
        if not kai_url:
            raise KaiError(
                message="kai-assistant service has no URL",
                code="discovery:no_url",
            )

        return cls(
            storage_api_token=storage_api_token,
            storage_api_url=storage_api_url,
            base_url=kai_url,
            timeout=timeout,
            stream_timeout=stream_timeout,
        )

    def __init__(
        self,
        storage_api_token: str,
        storage_api_url: str,
        base_url: str = "http://localhost:3000",
        timeout: float = 300.0,
        stream_timeout: float = 600.0,
    ) -> None:
        """
        Initialize the Kai client.

        Args:
            storage_api_token: Keboola Storage API token for authentication.
            storage_api_url: Keboola Storage API URL (e.g., https://connection.keboola.com).
            base_url: Base URL for the Kai API (default: http://localhost:3000).
            timeout: Default timeout for non-streaming requests in seconds.
            stream_timeout: Timeout for streaming requests in seconds.
        """
        self.base_url = base_url.rstrip("/")
        self.storage_api_token = storage_api_token
        self.storage_api_url = storage_api_url
        self.timeout = timeout
        self.stream_timeout = stream_timeout
        self._client: Optional[httpx.AsyncClient] = None

    def _get_auth_headers(self) -> dict[str, str]:
        """Get authentication headers for API requests."""
        return {
            "x-storageapi-token": self.storage_api_token,
            "x-storageapi-url": self.storage_api_url,
        }

    def _get_client(self) -> httpx.AsyncClient:
        """Get the HTTP client, creating it if necessary."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def __aenter__(self) -> "KaiClient":
        """Enter the async context manager."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(self.timeout),
        )
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Optional[TracebackType],
    ) -> None:
        """Exit the async context manager and close the client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
        auth: bool = True,
    ) -> httpx.Response:
        """
        Make an HTTP request.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE).
            path: API endpoint path.
            json: JSON body for the request.
            params: Query parameters.
            auth: Whether to include authentication headers.

        Returns:
            The HTTP response.

        Raises:
            KaiError: If the request fails.
        """
        client = self._get_client()
        headers = self._get_auth_headers() if auth else {}

        try:
            response = await client.request(
                method=method,
                url=path,
                json=json,
                params=params,
                headers=headers,
            )

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    raise_for_error_response(error_data)
                except JSONDecodeError:
                    raise KaiError(
                        message=f"HTTP {response.status_code}: {response.text}",
                        code=f"http:{response.status_code}",
                    )

            return response

        except httpx.ConnectError as e:
            raise KaiConnectionError(
                message=f"Failed to connect to {self.base_url}",
                cause=str(e),
            ) from e
        except httpx.TimeoutException as e:
            raise KaiTimeoutError(
                message="Request timed out",
                cause=str(e),
            ) from e

    @staticmethod
    def new_chat_id() -> str:
        """
        Generate a new unique chat ID.

        Returns:
            A UUID string for the chat session.
        """
        return str(uuid.uuid4())

    @staticmethod
    def new_message_id() -> str:
        """
        Generate a new unique message ID.

        Returns:
            A UUID string for the message.
        """
        return str(uuid.uuid4())

    # =========================================================================
    # Health & Info Endpoints (No Auth Required)
    # =========================================================================

    async def ping(self) -> PingResponse:
        """
        Check if the server is alive.

        Returns:
            PingResponse with the server timestamp.
        """
        response = await self._request("GET", "/ping", auth=False)
        return PingResponse.model_validate(response.json())

    async def info(self) -> InfoResponse:
        """
        Get server information including MCP connection status.

        Returns:
            InfoResponse with server details.
        """
        response = await self._request("GET", "/api", auth=False)
        return InfoResponse.model_validate(response.json())

    # =========================================================================
    # Chat Endpoints
    # =========================================================================

    @asynccontextmanager
    async def _stream_request(
        self,
        method: str,
        path: str,
        *,
        json: Optional[dict[str, Any]] = None,
        params: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[httpx.Response]:
        """
        Make a streaming HTTP request.

        Args:
            method: HTTP method.
            path: API endpoint path.
            json: JSON body for the request.
            params: Query parameters.

        Yields:
            The HTTP response for streaming.
        """
        client = self._get_client()
        headers = self._get_auth_headers()

        async with client.stream(
            method=method,
            url=path,
            json=json,
            params=params,
            headers=headers,
            timeout=httpx.Timeout(self.stream_timeout),
        ) as response:
            if response.status_code >= 400:
                # Read the error body for non-streaming errors
                await response.aread()
                content = response.content.decode("utf-8", errors="replace").strip()

                # Try to parse as JSON error response
                if content.startswith("{"):
                    try:
                        error_data = response.json()
                        raise_for_error_response(error_data)
                    except KaiError:
                        raise
                    except Exception:
                        pass  # Fall through to generic error

                # Generic error with text content or reason phrase
                error_msg = content if content else response.reason_phrase
                raise KaiError(
                    message=f"HTTP {response.status_code}: {error_msg}",
                    code=f"http:{response.status_code}",
                )
            yield response

    async def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
        hidden: bool = False,
        request_path: Optional[str] = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Send a message and stream the response.

        This method sends a user message to an existing or new chat and yields
        SSE events as they arrive from the server.

        Args:
            chat_id: The chat session ID (use new_chat_id() to create one).
            text: The message text to send.
            visibility: Chat visibility (default: private).
            branch_id: Optional Keboola branch ID.
            hidden: Whether the message should be hidden.
            request_path: Optional path context for the request.

        Yields:
            SSE events from the response stream.

        Example:
            ```python
            chat_id = client.new_chat_id()
            async for event in client.send_message(chat_id, "Hello!"):
                if event.type == "text":
                    print(event.text, end="")
            ```
        """
        # Build metadata if needed
        metadata: Optional[MessageMetadata] = None
        if hidden or request_path:
            metadata = MessageMetadata(
                hidden=hidden,
                request_context=RequestContext(path=request_path) if request_path else None,
            )

        # Build the request
        request = ChatRequest(
            id=chat_id,
            message=MessageRequest(
                id=self.new_message_id(),
                role="user",
                parts=[TextPart(type="text", text=text)],
                metadata=metadata,
            ),
            selected_chat_model="chat-model",
            selected_visibility_type=_normalize_visibility(visibility),
            branch_id=branch_id,
        )

        # Serialize with aliases
        payload = request.model_dump(by_alias=True, exclude_none=True)

        async with self._stream_request("POST", "/api/chat", json=payload) as response:
            async for event in parse_sse_stream(response):
                yield event

    async def send_tool_approval_response(
        self,
        chat_id: str,
        approval_id: str,
        approved: bool,
        *,
        reason: Optional[str] = None,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Respond to a tool approval request (Vercel AI SDK v6 approval flow).

        .. deprecated::
            Use :meth:`submit_approval` instead. This method uses the old
            Vercel AI SDK v6 protocol (fetch-chat → mutate-message → re-POST)
            which is not supported by the kai-agent backend.

        This works by fetching the chat, finding the assistant message that
        contains the tool call requiring approval, updating its state to
        ``approval-responded``, and re-sending the updated assistant message
        to the backend. This mirrors how the Keboola frontend handles tool
        approvals.

        Args:
            chat_id: The chat session ID.
            approval_id: The approval ID from the ToolApprovalRequestEvent.
            approved: Whether to approve (True) or deny (False) the tool call.
            reason: Optional reason for the decision.
            visibility: Chat visibility (should match the original request).
            branch_id: Optional Keboola branch ID.

        Yields:
            SSE events from the continued response stream.

        Example:
            ```python
            chat_id = client.new_chat_id()
            pending_approval_id = None
            async for event in client.send_message(chat_id, "Update descriptions"):
                if event.type == "tool-approval-request":
                    pending_approval_id = event.approval_id
                elif event.type == "text":
                    print(event.text, end="")

            if pending_approval_id:
                async for event in client.approve_tool(
                    chat_id=chat_id,
                    approval_id=pending_approval_id,
                ):
                    if event.type == "text":
                        print(event.text, end="")
            ```
        """
        # Fetch the chat to get the latest assistant message with the tool call
        chat = await self.get_chat(chat_id)

        # Find the assistant message containing the tool call with this approval ID
        assistant_msg = None
        for msg in reversed(chat.messages):
            if msg.role != "assistant":
                continue
            for part in msg.parts:
                if (
                    isinstance(part, dict)
                    and part.get("approval", {}).get("id") == approval_id
                ):
                    assistant_msg = msg
                    break
            if assistant_msg:
                break

        if not assistant_msg:
            raise KaiError(
                message=f"Could not find assistant message with approval ID {approval_id}",
                code="approval:not_found",
            )

        # Update the tool call part: state → approval-responded, approval.approved → value
        updated_parts = []
        for part in assistant_msg.parts:
            if (
                isinstance(part, dict)
                and part.get("approval", {}).get("id") == approval_id
            ):
                updated_part = {**part}
                updated_part["state"] = "approval-responded"
                updated_part["approval"] = {
                    "id": approval_id,
                    "approved": approved,
                }
                if reason is not None:
                    updated_part["approval"]["reason"] = reason
                updated_parts.append(updated_part)
            else:
                updated_parts.append(part)

        # Build payload: send the updated assistant message back
        payload: dict[str, Any] = {
            "id": chat_id,
            "message": {
                "id": assistant_msg.id,
                "role": "assistant",
                "parts": updated_parts,
            },
            "selectedChatModel": "chat-model",
            "selectedVisibilityType": _normalize_visibility(visibility),
        }
        if branch_id is not None:
            payload["branchId"] = branch_id

        async with self._stream_request("POST", "/api/chat", json=payload) as response:
            async for event in parse_sse_stream(response):
                yield event

    async def approve_tool(
        self,
        chat_id: str,
        approval_id: str,
        *,
        reason: Optional[str] = None,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Approve a pending tool call and continue the stream.

        .. deprecated::
            Use :meth:`submit_approval` instead. This method uses the old
            Vercel AI SDK v6 protocol not supported by the kai-agent backend.

        Args:
            chat_id: The chat session ID.
            approval_id: The approval ID from the tool-call event's approval.id field.
            reason: Optional reason for approval.
            visibility: Chat visibility.
            branch_id: Optional Keboola branch ID.

        Yields:
            SSE events from the continued response stream.
        """
        async for event in self.send_tool_approval_response(
            chat_id=chat_id,
            approval_id=approval_id,
            approved=True,
            reason=reason,
            visibility=visibility,
            branch_id=branch_id,
        ):
            yield event

    async def reject_tool(
        self,
        chat_id: str,
        approval_id: str,
        *,
        reason: Optional[str] = None,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Reject a pending tool call and continue the stream.

        .. deprecated::
            Use :meth:`submit_approval` with ``approved=False`` instead. This
            method uses the old Vercel AI SDK v6 protocol not supported by the
            kai-agent backend.

        Args:
            chat_id: The chat session ID.
            approval_id: The approval ID from the tool-call event's approval.id field.
            reason: Optional reason for rejection.
            visibility: Chat visibility.
            branch_id: Optional Keboola branch ID.

        Yields:
            SSE events from the continued response stream.
        """
        async for event in self.send_tool_approval_response(
            chat_id=chat_id,
            approval_id=approval_id,
            approved=False,
            reason=reason,
            visibility=visibility,
            branch_id=branch_id,
        ):
            yield event

    async def send_tool_result(
        self,
        chat_id: str,
        tool_call_id: str,
        tool_name: str,
        result: str,
        *,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Send a tool result (legacy method, prefer send_tool_approval_response).

        .. deprecated::
            Use :meth:`submit_approval` for the kai-agent backend.
            Use send_tool_approval_response / approve_tool / reject_tool for the
            old Vercel AI SDK v6 backend. This method uses the old tool-result
            protocol which can cause empty user message errors.

        Args:
            chat_id: The chat session ID.
            tool_call_id: The ID of the tool call to respond to.
            tool_name: The name of the tool.
            result: The result to send.
            visibility: Chat visibility.
            branch_id: Optional Keboola branch ID.

        Yields:
            SSE events from the continued response stream.
        """
        request = ChatRequest(
            id=chat_id,
            message=MessageRequest(
                id=self.new_message_id(),
                role="user",
                parts=[
                    ToolResultPart(
                        type="tool-result",
                        tool_call_id=tool_call_id,
                        tool_name=tool_name,
                        result=result,
                    )
                ],
            ),
            selected_chat_model="chat-model",
            selected_visibility_type=_normalize_visibility(visibility),
            branch_id=branch_id,
        )

        payload = request.model_dump(by_alias=True, exclude_none=True)

        async with self._stream_request("POST", "/api/chat", json=payload) as response:
            async for event in parse_sse_stream(response):
                yield event

    async def confirm_tool(
        self,
        chat_id: str,
        tool_call_id: str,
        tool_name: str,
        *,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Confirm a pending tool call (legacy method, prefer approve_tool).

        .. deprecated::
            Use approve_tool instead for the v6 approval flow.
        """
        async for event in self.send_tool_result(
            chat_id=chat_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            result="confirmed",
            visibility=visibility,
            branch_id=branch_id,
        ):
            yield event

    async def deny_tool(
        self,
        chat_id: str,
        tool_call_id: str,
        tool_name: str,
        *,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
    ) -> AsyncIterator[SSEEvent]:
        """
        Deny a pending tool call (legacy method, prefer reject_tool).

        .. deprecated::
            Use reject_tool instead for the v6 approval flow.
        """
        async for event in self.send_tool_result(
            chat_id=chat_id,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            result="denied",
            visibility=visibility,
            branch_id=branch_id,
        ):
            yield event

    async def get_chat(self, chat_id: str) -> ChatDetail:
        """
        Get detailed information about a chat including message history.

        Args:
            chat_id: The chat session ID.

        Returns:
            ChatDetail with full message history.
        """
        response = await self._request("GET", f"/api/chat/{chat_id}")
        return ChatDetail.model_validate(response.json())

    async def resume_stream(self, chat_id: str) -> AsyncIterator[SSEEvent]:
        """
        Resume a chat stream if one is available.

        .. deprecated::
            The kai-agent backend does not expose a stream-resume endpoint.
            This method is only functional against older backends.

        This can be used to reconnect to an ongoing stream after a disconnect.

        Args:
            chat_id: The chat session ID.

        Yields:
            SSE events from the resumed stream.

        Note:
            Returns nothing if no stream is available (server returns 204).
        """
        async with self._stream_request("GET", f"/api/chat/{chat_id}/stream") as response:
            if response.status_code == 204:
                return
            async for event in parse_sse_stream(response):
                yield event

    async def delete_chat(self, chat_id: str) -> None:
        """
        Delete a chat.

        Args:
            chat_id: The chat session ID to delete.
        """
        await self._request("DELETE", "/api/chat", params={"id": chat_id})

    async def submit_approval(
        self,
        chat_id: str,
        tool_use_id: str,
        approved: bool,
        *,
        reason: Optional[str] = None,
        updated_input: Optional[dict[str, Any]] = None,
        answers: Optional[dict[str, Any]] = None,
    ) -> ApprovalResponse:
        """
        Approve or deny a pending tool call (kai-agent backend).

        This is a non-streaming call that unblocks the live SSE stream still
        running from the original send_message call. The toolCallId from the
        ``tool-input-available`` SSE event is the ``tool_use_id`` to pass here.

        Args:
            chat_id: The chat session ID.
            tool_use_id: The toolCallId from the tool-input-available SSE event.
            approved: Whether to approve (True) or deny (False) the tool call.
            reason: Optional reason for the decision.
            updated_input: Optional modified tool input (only used when approved).
            answers: Optional answers for interactive tool questions.

        Returns:
            ApprovalResponse confirming the decision.
        """
        payload: dict[str, Any] = {"toolUseId": tool_use_id, "approved": approved}
        if reason is not None:
            payload["reason"] = reason
        if updated_input is not None:
            payload["updatedInput"] = updated_input
        if answers is not None:
            payload["answers"] = answers

        response = await self._request("POST", f"/api/chat/{chat_id}/approval", json=payload)
        return ApprovalResponse.model_validate(response.json())

    # =========================================================================
    # History Endpoint
    # =========================================================================

    async def get_history(
        self,
        limit: int = 10,
        starting_after: Optional[str] = None,
        ending_before: Optional[str] = None,
    ) -> HistoryResponse:
        """
        Get the user's chat history.

        Args:
            limit: Maximum number of chats to return (default: 10).
            starting_after: Cursor for forward pagination (chat ID).
            ending_before: Cursor for backward pagination (chat ID).

        Returns:
            HistoryResponse with list of chats and pagination info.
        """
        params: dict[str, Any] = {"limit": limit}
        if starting_after:
            params["starting_after"] = starting_after
        if ending_before:
            params["ending_before"] = ending_before

        response = await self._request("GET", "/api/history", params=params)
        return HistoryResponse.model_validate(response.json())

    async def get_all_history(self, batch_size: int = 100) -> AsyncIterator[Chat]:
        """
        Iterate through all chat history.

        This is a convenience method that handles pagination automatically.

        Args:
            batch_size: Number of chats to fetch per request.

        Yields:
            Chat objects from the history.
        """
        starting_after: Optional[str] = None
        while True:
            history = await self.get_history(limit=batch_size, starting_after=starting_after)
            for chat in history.chats:
                yield chat

            if not history.has_more or not history.chats:
                break
            starting_after = history.chats[-1].id

    # =========================================================================
    # Vote Endpoints
    # =========================================================================

    async def get_votes(self, chat_id: str) -> list[Vote]:
        """
        Get all votes for a chat.

        Args:
            chat_id: The chat session ID.

        Returns:
            List of votes on messages in the chat.
        """
        response = await self._request("GET", "/api/vote", params={"chatId": chat_id})
        data = response.json()
        # Response might be a list or an object with a votes field
        items = data if isinstance(data, list) else data.get("votes", [])
        return [self._parse_vote(v) for v in items]

    @staticmethod
    def _parse_vote(data: dict) -> Vote:
        """Parse a vote from either API format.

        The API may return votes as:
        - {chatId, messageId, type: "up"|"down"} (legacy)
        - {chatId, messageId, isUpvoted: bool} (current production)
        """
        if "type" in data:
            return Vote.model_validate(data)
        # Convert isUpvoted format to type format
        vote_type = "up" if data.get("isUpvoted", False) else "down"
        return Vote(
            chat_id=data.get("chatId", ""),
            message_id=data.get("messageId", ""),
            type=vote_type,  # type: ignore
        )

    async def vote(
        self,
        chat_id: str,
        message_id: str,
        vote_type: str | VoteType,
    ) -> Vote:
        """
        Vote on a message.

        Args:
            chat_id: The chat session ID.
            message_id: The message ID to vote on.
            vote_type: The vote type ("up" or "down").

        Returns:
            The created/updated vote.
        """
        vote_str = vote_type.value if isinstance(vote_type, VoteType) else vote_type
        request = VoteRequest(
            chat_id=chat_id,
            message_id=message_id,
            type=vote_str,  # type: ignore
        )
        payload = request.model_dump(by_alias=True)

        await self._request("PATCH", "/api/vote", json=payload)
        # API returns plain text confirmation, not JSON.
        # Construct the Vote from the request data.
        return Vote(
            chat_id=chat_id,
            message_id=message_id,
            type=vote_str,  # type: ignore
        )

    async def upvote(self, chat_id: str, message_id: str) -> Vote:
        """
        Upvote a message.

        Args:
            chat_id: The chat session ID.
            message_id: The message ID to upvote.

        Returns:
            The created/updated vote.
        """
        return await self.vote(chat_id, message_id, VoteType.UP)

    async def downvote(self, chat_id: str, message_id: str) -> Vote:
        """
        Downvote a message.

        Args:
            chat_id: The chat session ID.
            message_id: The message ID to downvote.

        Returns:
            The created/updated vote.
        """
        return await self.vote(chat_id, message_id, VoteType.DOWN)

    # =========================================================================
    # Usage Endpoint
    # =========================================================================

    async def get_usage(self) -> UsageResponse:
        """
        Get rate limit usage information for the current user and project.

        Returns:
            UsageResponse with messages used, limit, and reset date.
        """
        response = await self._request("GET", "/api/usage")
        return UsageResponse.model_validate(response.json())

    # =========================================================================
    # Settings Endpoints
    # =========================================================================

    async def get_settings(self) -> AgentSettings:
        """
        Get project-level agent settings.

        Returns:
            AgentSettings with custom instructions for the project.
        """
        response = await self._request("GET", "/api/settings")
        return AgentSettings.model_validate(response.json())

    async def update_settings(
        self,
        *,
        custom_instructions: Union[str, None] = _UNSET,
    ) -> AgentSettings:
        """
        Update project-level agent settings.

        Only fields explicitly passed are included in the request — omitting a
        parameter leaves the corresponding server value unchanged. Pass
        ``custom_instructions=None`` to explicitly clear instructions.

        Args:
            custom_instructions: Custom system prompt instructions for the project.
                Pass ``None`` to clear. Omit to leave unchanged.

        Returns:
            Updated AgentSettings.
        """
        payload: dict[str, Any] = {}
        if custom_instructions is not _UNSET:
            payload["customInstructions"] = custom_instructions

        response = await self._request("PATCH", "/api/settings", json=payload)
        return AgentSettings.model_validate(response.json())

    async def get_user_settings(self) -> UserAgentSettings:
        """
        Get user-level agent settings.

        Returns:
            UserAgentSettings with custom instructions and tool permissions.
        """
        response = await self._request("GET", "/api/settings/user")
        return UserAgentSettings.model_validate(response.json())

    async def update_user_settings(
        self,
        *,
        custom_instructions: Union[str, None] = _UNSET,
        tool_permissions: Union[dict[str, str], None] = _UNSET,
    ) -> UserAgentSettings:
        """
        Update user-level agent settings.

        Only fields explicitly passed are included in the request — omitting a
        parameter leaves the corresponding server value unchanged.

        - Pass ``custom_instructions=None`` to clear instructions.
        - Pass ``tool_permissions=None`` to reset all permissions to defaults.
        - Pass a dict to ``tool_permissions`` to merge with existing values.

        Valid permission values: ``"always_allow"``, ``"always_ask"``, ``"blocked"``.

        Args:
            custom_instructions: Custom system prompt instructions for this user.
                Pass ``None`` to clear. Omit to leave unchanged.
            tool_permissions: Dict mapping tool name to permission value.
                Pass ``None`` to reset to defaults. Omit to leave unchanged.

        Raises:
            ValueError: If no fields are provided (nothing to update).

        Returns:
            Updated UserAgentSettings.
        """
        payload: dict[str, Any] = {}
        if custom_instructions is not _UNSET:
            payload["customInstructions"] = custom_instructions
        if tool_permissions is not _UNSET:
            payload["toolPermissions"] = tool_permissions

        if not payload:
            raise ValueError(
                "update_user_settings() requires at least one argument; "
                "call with explicit values or None to clear individual fields."
            )

        response = await self._request("PATCH", "/api/settings/user", json=payload)
        return UserAgentSettings.model_validate(response.json())

    async def get_tools(self) -> ToolsListResponse:
        """
        List all available MCP tools with their metadata.

        Returns:
            ToolsListResponse with tool names, descriptions, and read-only flags.
        """
        response = await self._request("GET", "/api/settings/tools")
        data = response.json()
        tools = [ToolInfo.model_validate(t) for t in data.get("tools", [])]
        return ToolsListResponse(tools=tools)

    # =========================================================================
    # Suggestions Endpoint
    # =========================================================================

    async def get_suggestions(
        self,
        context: str,
        data: dict[str, Any],
    ) -> SuggestionsResponse:
        """
        Generate contextual AI suggestions.

        Args:
            context: The context type — one of ``"dashboard"``,
                ``"job-detail"``, or ``"configuration-detail"``.
            data: Context-specific data payload.

        Returns:
            SuggestionsResponse with a list of suggestions and session ID.
        """
        payload: dict[str, Any] = {"context": context, "data": data}
        response = await self._request("POST", "/api/suggestions", json=payload)
        return SuggestionsResponse.model_validate(response.json())

    # =========================================================================
    # Convenience Methods
    # =========================================================================

    async def chat(
        self,
        text: str,
        *,
        chat_id: Optional[str] = None,
        visibility: str | VisibilityType = VisibilityType.PRIVATE,
        branch_id: Optional[int] = None,
    ) -> tuple[str, str]:
        """
        Send a message and collect the full text response.

        This is a convenience method that collects all text events into
        a single response string.

        Args:
            text: The message text to send.
            chat_id: Optional chat ID (generates new one if not provided).
            visibility: Chat visibility.
            branch_id: Optional Keboola branch ID.

        Returns:
            Tuple of (chat_id, response_text).

        Example:
            ```python
            chat_id, response = await client.chat("What is 2+2?")
            print(response)
            ```
        """
        if chat_id is None:
            chat_id = self.new_chat_id()

        response_parts: list[str] = []

        async for event in self.send_message(
            chat_id=chat_id,
            text=text,
            visibility=visibility,
            branch_id=branch_id,
        ):
            if event.type == "text":
                response_parts.append(event.text)  # type: ignore

        return chat_id, "".join(response_parts)


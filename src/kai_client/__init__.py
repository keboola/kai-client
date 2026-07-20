"""
Kai Client - Python client library for the Keboola AI Assistant Backend API.

This library provides an async client for interacting with the Keboola AI
Assistant (Kai) backend, supporting SSE streaming, chat management, and more.

Example:
    ```python
    from kai_client import KaiClient

    async with KaiClient(
        storage_api_token="your-token",
        storage_api_url="https://connection.keboola.com"
    ) as client:
        # Start a new chat
        chat_id = client.new_chat_id()

        # Send a message and stream the response
        async for event in client.send_message(chat_id, "Hello!"):
            if event.type == "text":
                print(event.text, end="", flush=True)
    ```
"""

from kai_client.client import KaiClient
from kai_client.exceptions import (
    KaiAuthenticationError,
    KaiBadRequestError,
    KaiConnectionError,
    KaiError,
    KaiForbiddenError,
    KaiNotFoundError,
    KaiRateLimitError,
    KaiStreamError,
    KaiTimeoutError,
)
from kai_client.models import (
    AgentSettings,
    ApprovalResponse,
    Chat,
    ChatDetail,
    ChatRequest,
    ErrorEvent,
    ErrorResponse,
    FinishEvent,
    HistoryResponse,
    InfoResponse,
    McpConnection,
    Message,
    MessageMetadata,
    MessageRequest,
    PingResponse,
    RequestContext,
    SSEEvent,
    StepStartEvent,
    Suggestion,
    SuggestionsResponse,
    TextEvent,
    TextPart,
    ToolApproval,
    ToolApprovalRequestEvent,
    ToolApprovalResponsePart,
    ToolCallEvent,
    ToolCallPart,
    ToolInfo,
    ToolOutputErrorEvent,
    ToolRestrictions,
    ToolResultPart,
    ToolsListResponse,
    UnknownEvent,
    UsageEvent,
    UsageInfo,
    UsageResponse,
    UserAgentSettings,
    Vote,
    VoteRequest,
)
from kai_client.sse import SSEStreamParser, parse_sse_event, parse_sse_stream
from kai_client.types import (
    FinishReason,
    MessageRole,
    SSEEventType,
    ToolCallState,
    VisibilityType,
    VoteType,
)

__version__ = "0.12.0"

__all__ = [
    # Main client
    "KaiClient",
    # Exceptions
    "KaiError",
    "KaiAuthenticationError",
    "KaiForbiddenError",
    "KaiNotFoundError",
    "KaiRateLimitError",
    "KaiBadRequestError",
    "KaiStreamError",
    "KaiConnectionError",
    "KaiTimeoutError",
    # Request models
    "ChatRequest",
    "MessageRequest",
    "VoteRequest",
    "TextPart",
    "ToolResultPart",
    "ToolApprovalResponsePart",
    "ToolCallPart",
    "ToolRestrictions",
    "MessageMetadata",
    "RequestContext",
    # Response models
    "PingResponse",
    "InfoResponse",
    "McpConnection",
    "Chat",
    "ChatDetail",
    "Message",
    "HistoryResponse",
    "Vote",
    "ErrorResponse",
    "ApprovalResponse",
    "UsageResponse",
    "AgentSettings",
    "UserAgentSettings",
    "ToolInfo",
    "ToolsListResponse",
    "Suggestion",
    "SuggestionsResponse",
    # SSE models
    "SSEEvent",
    "TextEvent",
    "StepStartEvent",
    "ToolApproval",
    "ToolApprovalRequestEvent",
    "ToolCallEvent",
    "ToolOutputErrorEvent",
    "UsageEvent",
    "UsageInfo",
    "FinishEvent",
    "ErrorEvent",
    "UnknownEvent",
    # SSE utilities
    "SSEStreamParser",
    "parse_sse_stream",
    "parse_sse_event",
    # Enums
    "VisibilityType",
    "VoteType",
    "MessageRole",
    "SSEEventType",
    "FinishReason",
    "ToolCallState",
    # Version
    "__version__",
]



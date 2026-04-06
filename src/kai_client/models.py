"""Pydantic models for the Kai client library."""

from datetime import datetime
from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

# =============================================================================
# Message Part Models (for discriminated union)
# =============================================================================


class TextPart(BaseModel):
    """A text content part in a message."""

    model_config = ConfigDict(extra="allow")

    type: Literal["text"] = "text"
    text: str
    state: Optional[str] = None


class StepStartPart(BaseModel):
    """Indicates the start of a processing step."""

    model_config = ConfigDict(extra="allow")

    type: Literal["step-start"] = "step-start"


class ToolResultPart(BaseModel):
    """Result from a tool execution."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: Literal["tool-result"] = "tool-result"
    tool_call_id: str = Field(alias="toolCallId")
    tool_name: str = Field(alias="toolName")
    result: Any


class ToolApprovalResponsePart(BaseModel):
    """Response to a tool approval request (Vercel AI SDK v6)."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: Literal["tool-approval-response"] = "tool-approval-response"
    approval_id: str = Field(alias="approvalId")
    approved: bool
    reason: Optional[str] = None


class ToolCallPart(BaseModel):
    """A tool call in progress or completed."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: str  # "tool-{name}" pattern
    tool_call_id: str = Field(alias="toolCallId")
    state: str
    input: Optional[dict[str, Any]] = None
    output: Optional[dict[str, Any]] = None
    tool_name: Optional[str] = Field(default=None, alias="toolName")


# Discriminated union for message parts
MessagePart = Annotated[
    Union[TextPart, StepStartPart, ToolResultPart, ToolApprovalResponsePart, ToolCallPart],
    Field(discriminator="type"),
]


# =============================================================================
# Request Metadata Models
# =============================================================================


class RequestContext(BaseModel):
    """Context about the request origin."""

    model_config = ConfigDict(extra="allow")

    path: Optional[str] = None


class MessageMetadata(BaseModel):
    """Metadata attached to a message."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    hidden: bool = False
    request_context: Optional[RequestContext] = Field(default=None, alias="requestContext")


# =============================================================================
# Request Models
# =============================================================================


class MessageRequest(BaseModel):
    """A user message to send to the chat."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    role: Literal["user"] = "user"
    parts: list[Union[TextPart, ToolResultPart, ToolApprovalResponsePart]]
    metadata: Optional[MessageMetadata] = None


class ChatRequest(BaseModel):
    """Request body for creating/continuing a chat."""

    model_config = ConfigDict(populate_by_name=True)

    id: str
    message: MessageRequest
    selected_chat_model: str = Field(alias="selectedChatModel")
    selected_visibility_type: str = Field(alias="selectedVisibilityType")
    branch_id: Optional[int] = Field(default=None, alias="branchId")


class VoteRequest(BaseModel):
    """Request body for voting on a message."""

    model_config = ConfigDict(populate_by_name=True)

    chat_id: str = Field(alias="chatId")
    message_id: str = Field(alias="messageId")
    type: Literal["up", "down"]


# =============================================================================
# Response Models
# =============================================================================


class PingResponse(BaseModel):
    """Response from the ping endpoint."""

    timestamp: datetime


class McpConnection(BaseModel):
    """Information about an MCP server connection."""

    model_config = ConfigDict(extra="allow")

    name: str
    status: str


class InfoResponse(BaseModel):
    """Response from the info endpoint."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    timestamp: datetime
    uptime: float
    app_name: str = Field(alias="appName")
    app_version: str = Field(alias="appVersion")
    server_version: str = Field(alias="serverVersion")
    connected_mcp: Any = Field(default_factory=list, alias="connectedMcp")  # Can be list or dict


class Message(BaseModel):
    """A message in a chat conversation."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    role: str
    parts: list[dict[str, Any]]  # Allow any part structure
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")
    metadata: Optional[dict[str, Any]] = None


class Chat(BaseModel):
    """A chat conversation summary."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: str
    title: Optional[str] = None
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")
    updated_at: Optional[datetime] = Field(default=None, alias="updatedAt")
    visibility: Optional[str] = None
    user_id: Optional[str] = Field(default=None, alias="userId")


class ChatDetail(Chat):
    """Detailed chat information including messages."""

    messages: list[Message] = Field(default_factory=list)


class HistoryResponse(BaseModel):
    """Response from the history endpoint."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    chats: list[Chat]
    has_more: bool = Field(alias="hasMore")


class Vote(BaseModel):
    """A vote on a message."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    id: Optional[str] = None
    chat_id: str = Field(alias="chatId")
    message_id: str = Field(alias="messageId")
    type: Literal["up", "down"]
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")


class ErrorResponse(BaseModel):
    """Error response from the API."""

    model_config = ConfigDict(extra="allow")

    code: str
    message: str
    cause: Optional[str] = None


# =============================================================================
# SSE Event Models
# =============================================================================


class BaseSSEEvent(BaseModel):
    """Base class for SSE events."""

    model_config = ConfigDict(extra="allow")

    type: str


class TextEvent(BaseSSEEvent):
    """Text content event from the stream."""

    type: Literal["text"] = "text"
    text: str
    state: Optional[str] = None


class StepStartEvent(BaseSSEEvent):
    """Step start event from the stream."""

    type: Literal["step-start"] = "step-start"


class ToolApproval(BaseModel):
    """Approval metadata attached to a tool call event."""

    model_config = ConfigDict(extra="allow")

    id: str
    approved: Optional[bool] = None
    reason: Optional[str] = None


class ToolCallEvent(BaseSSEEvent):
    """Tool call event from the stream."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: Literal["tool-call"] = "tool-call"
    tool_call_id: str = Field(alias="toolCallId")
    tool_name: Optional[str] = Field(default=None, alias="toolName")
    state: str
    input: Optional[dict[str, Any]] = None
    output: Optional[dict[str, Any]] = None
    approval: Optional[ToolApproval] = None


class ToolApprovalRequestEvent(BaseSSEEvent):
    """Tool approval request event from the stream (Vercel AI SDK v6).

    Emitted when a tool call requires explicit user approval before execution.
    Contains the approval_id needed to approve or reject the tool.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: Literal["tool-approval-request"] = "tool-approval-request"
    approval_id: str = Field(alias="approvalId")
    tool_call_id: str = Field(alias="toolCallId")


class UsageInfo(BaseModel):
    """Token usage information from a finish event."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    prompt_tokens: int = Field(default=0, alias="promptTokens")
    completion_tokens: int = Field(default=0, alias="completionTokens")
    total_tokens: int = Field(default=0, alias="totalTokens")
    cache_read_tokens: int = Field(default=0, alias="cacheReadTokens")
    cache_write_tokens: int = Field(default=0, alias="cacheWriteTokens")
    reasoning_tokens: int = Field(default=0, alias="reasoningTokens")


class UsageEvent(BaseSSEEvent):
    """Token usage event emitted by the backend via dataStream.write().

    The Vercel AI SDK prefixes custom data types with "data-", so the
    SSE event type is "data-usage" with the payload nested under "data".
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: Literal["data-usage"] = "data-usage"
    usage: UsageInfo


class FinishEvent(BaseSSEEvent):
    """Stream finish event."""

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: Literal["finish"] = "finish"
    finish_reason: str = Field(alias="finishReason")
    usage: Optional[UsageInfo] = None


class ErrorEvent(BaseSSEEvent):
    """Error event from the stream."""

    type: Literal["error"] = "error"
    message: str
    code: Optional[str] = None


class ToolOutputErrorEvent(BaseSSEEvent):
    """Tool output error event from the stream.

    Emitted when a tool execution fails after user confirmation.
    """

    model_config = ConfigDict(extra="allow", populate_by_name=True)

    type: Literal["tool-output-error"] = "tool-output-error"
    tool_call_id: str = Field(alias="toolCallId")
    error_text: str = Field(alias="errorText")


class UnknownEvent(BaseSSEEvent):
    """Unknown event type - stores raw data."""

    type: str
    data: dict[str, Any] = Field(default_factory=dict)


# Union type for all SSE events
SSEEvent = Union[
    TextEvent,
    StepStartEvent,
    ToolCallEvent,
    ToolApprovalRequestEvent,
    UsageEvent,
    FinishEvent,
    ErrorEvent,
    ToolOutputErrorEvent,
    UnknownEvent,
]


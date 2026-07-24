"""Type aliases and enums for the Kai client library."""

from enum import Enum


class VisibilityType(str, Enum):
    """Chat visibility types."""

    PRIVATE = "private"
    PUBLIC = "public"


class VoteType(str, Enum):
    """Vote types for messages."""

    UP = "up"
    DOWN = "down"


class KaiBackend(str, Enum):
    """Selectable Keboola AI backend services (Storage API service ids)."""

    AGENT = "kai-agent"          # modern agent backend (default)
    ASSISTANT = "kai-assistant"  # legacy backend (single-tenant; being retired)


class JobStatus(str, Enum):
    """Job processing status."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class MessageRole(str, Enum):
    """Message sender role."""

    USER = "user"
    ASSISTANT = "assistant"


class SSEEventType(str, Enum):
    """Server-Sent Event types."""

    TEXT = "text"
    STEP_START = "step-start"
    TOOL_CALL = "tool-call"
    TOOL_RESULT = "tool-result"
    TOOL_OUTPUT_ERROR = "tool-output-error"
    FINISH = "finish"
    ERROR = "error"


class FinishReason(str, Enum):
    """Reasons for stream completion."""

    STOP = "stop"
    LENGTH = "length"
    TOOL_CALLS = "tool_calls"
    ERROR = "error"


class ToolCallState(str, Enum):
    """State of a tool call."""

    STARTED = "started"
    INPUT_AVAILABLE = "input-available"
    INPUT_STREAMING = "input-streaming"
    OUTPUT_AVAILABLE = "output-available"
    OUTPUT_ERROR = "output-error"
    OUTPUT_DENIED = "output-denied"
    STREAMING = "streaming"
    DONE = "done"
    # Vercel AI SDK v6 approval states
    APPROVAL_REQUESTED = "approval-requested"
    APPROVAL_RESPONDED = "approval-responded"


# Type aliases for common patterns
ChatId = str
MessageId = str
ToolCallId = str


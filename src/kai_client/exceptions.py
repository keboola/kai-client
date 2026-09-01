"""Custom exception classes for the Kai client library."""

from typing import Any, Optional


class KaiError(Exception):
    """Base exception for all Kai client errors."""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        cause: Optional[str] = None,
        response_data: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.cause = cause
        self.response_data = response_data

    def __str__(self) -> str:
        parts = [self.message]
        if self.code:
            parts.insert(0, f"[{self.code}]")
        if self.cause:
            parts.append(f"(cause: {self.cause})")
        return " ".join(parts)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(message={self.message!r}, code={self.code!r})"


class KaiAuthenticationError(KaiError):
    """Raised when authentication fails (unauthorized:chat)."""


class KaiForbiddenError(KaiError):
    """Raised when access is forbidden (forbidden:chat)."""


class KaiNotFoundError(KaiError):
    """Raised when a resource is not found (not_found:chat)."""


class KaiRateLimitError(KaiError):
    """Raised when rate limit is exceeded (rate_limit:chat)."""


class KaiBadRequestError(KaiError):
    """Raised when the request is malformed (bad_request:api)."""


class KaiStreamError(KaiError):
    """Raised when there's an error during SSE streaming."""


class KaiConnectionError(KaiError):
    """Raised when connection to the server fails."""


class KaiTimeoutError(KaiError):
    """Raised when a request times out."""


# Mapping of API error codes to exception classes
ERROR_CODE_MAP: dict[str, type[KaiError]] = {
    "unauthorized:chat": KaiAuthenticationError,
    "forbidden:chat": KaiForbiddenError,
    "not_found:chat": KaiNotFoundError,
    "rate_limit:chat": KaiRateLimitError,
    "bad_request:api": KaiBadRequestError,
}

# kai-agent error *types* (the `error.type` field of its envelope) to exception
# classes. Types with no dedicated class (conflict, payload_too_large, offline,
# bad_response, internal) fall through to the base KaiError.
AGENT_ERROR_TYPE_MAP: dict[str, type[KaiError]] = {
    "bad_request": KaiBadRequestError,
    "unauthorized": KaiAuthenticationError,
    "forbidden": KaiForbiddenError,
    "not_found": KaiNotFoundError,
    "rate_limit": KaiRateLimitError,
}


def _parse_agent_error(response_data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Recognize the kai-agent error envelope and flatten it.

    kai-agent nests its error under an ``error`` key::

        {"error": {"type": "not_found", "surface": "api",
                   "message": "No pending approval found",
                   "exceptionId": "KAI-..."}}

    The legacy kai-assistant backend instead returns ``code``/``message`` at the
    top level. Without this branch every kai-agent failure would fall through to
    a bare ``KaiError("Unknown error")``, losing the message, the exception ID,
    and the ability to tell a 404 from a 500.

    ``type`` and ``surface`` are joined into the same ``type:surface`` code
    format the legacy codes already use, so ``KaiError.code`` stays uniform
    across backends.

    Returns None if this is not a kai-agent envelope.
    """
    error = response_data.get("error")
    if not isinstance(error, dict):
        return None

    error_type = error.get("type")
    message = error.get("message")
    if not isinstance(error_type, str) or not isinstance(message, str):
        return None

    surface = error.get("surface")
    code = f"{error_type}:{surface}" if isinstance(surface, str) else error_type

    return {
        "exception_class": AGENT_ERROR_TYPE_MAP.get(error_type, KaiError),
        "message": message,
        "code": code,
        "cause": error.get("exceptionId"),
    }


def raise_for_error_response(response_data: dict[str, Any]) -> None:
    """
    Raise the appropriate exception based on the error response.

    Args:
        response_data: The error response from the API.

    Raises:
        KaiError: The appropriate exception subclass based on the error code.
    """
    agent_error = _parse_agent_error(response_data)
    if agent_error is not None:
        raise agent_error["exception_class"](
            message=agent_error["message"],
            code=agent_error["code"],
            cause=agent_error["cause"],
            response_data=response_data,
        )

    code = response_data.get("code", "")
    message = response_data.get("message", "Unknown error")
    cause = response_data.get("cause")

    # Try exact match first
    exception_class = ERROR_CODE_MAP.get(code)

    # Try prefix match if no exact match
    if exception_class is None:
        for prefix, exc_class in ERROR_CODE_MAP.items():
            if code.startswith(prefix.split(":")[0]):
                exception_class = exc_class
                break

    # Default to base KaiError
    if exception_class is None:
        exception_class = KaiError

    raise exception_class(
        message=message,
        code=code,
        cause=cause,
        response_data=response_data,
    )



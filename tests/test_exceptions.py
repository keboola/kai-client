"""Tests for exception classes."""

import pytest

from kai_client.exceptions import (
    AGENT_ERROR_TYPE_MAP,
    ERROR_CODE_MAP,
    KaiAuthenticationError,
    KaiBadRequestError,
    KaiConnectionError,
    KaiError,
    KaiForbiddenError,
    KaiNotFoundError,
    KaiRateLimitError,
    KaiStreamError,
    KaiTimeoutError,
    raise_for_error_response,
)


class TestKaiError:
    """Tests for KaiError base class."""

    def test_basic_error(self):
        error = KaiError(message="Something went wrong")
        assert str(error) == "Something went wrong"
        assert error.message == "Something went wrong"
        assert error.code is None
        assert error.cause is None

    def test_error_with_code(self):
        error = KaiError(message="Error occurred", code="test:error")
        assert "[test:error]" in str(error)

    def test_error_with_cause(self):
        error = KaiError(message="Error", cause="Root cause")
        assert "(cause: Root cause)" in str(error)

    def test_error_with_all_fields(self):
        error = KaiError(
            message="Error message",
            code="error:code",
            cause="Some cause",
            response_data={"extra": "data"},
        )
        assert "[error:code]" in str(error)
        assert "Error message" in str(error)
        assert "(cause: Some cause)" in str(error)
        assert error.response_data == {"extra": "data"}

    def test_repr(self):
        error = KaiError(message="Test", code="test:code")
        repr_str = repr(error)
        assert "KaiError" in repr_str
        assert "Test" in repr_str
        assert "test:code" in repr_str


class TestSpecificExceptions:
    """Tests for specific exception subclasses."""

    def test_authentication_error(self):
        error = KaiAuthenticationError(
            message="Invalid token",
            code="unauthorized:chat",
        )
        assert isinstance(error, KaiError)
        assert error.code == "unauthorized:chat"

    def test_forbidden_error(self):
        error = KaiForbiddenError(
            message="Access denied",
            code="forbidden:chat",
        )
        assert isinstance(error, KaiError)

    def test_not_found_error(self):
        error = KaiNotFoundError(
            message="Chat not found",
            code="not_found:chat",
        )
        assert isinstance(error, KaiError)

    def test_rate_limit_error(self):
        error = KaiRateLimitError(
            message="Too many requests",
            code="rate_limit:chat",
        )
        assert isinstance(error, KaiError)

    def test_bad_request_error(self):
        error = KaiBadRequestError(
            message="Invalid request",
            code="bad_request:api",
        )
        assert isinstance(error, KaiError)

    def test_stream_error(self):
        error = KaiStreamError(
            message="Stream interrupted",
        )
        assert isinstance(error, KaiError)

    def test_connection_error(self):
        error = KaiConnectionError(
            message="Failed to connect",
            cause="Connection refused",
        )
        assert isinstance(error, KaiError)
        assert error.cause == "Connection refused"

    def test_timeout_error(self):
        error = KaiTimeoutError(
            message="Request timed out",
        )
        assert isinstance(error, KaiError)


class TestErrorCodeMap:
    """Tests for error code mapping."""

    def test_all_codes_mapped(self):
        expected_codes = [
            "unauthorized:chat",
            "forbidden:chat",
            "not_found:chat",
            "rate_limit:chat",
            "bad_request:api",
        ]
        for code in expected_codes:
            assert code in ERROR_CODE_MAP


class TestRaiseForErrorResponse:
    """Tests for raise_for_error_response function."""

    def test_unauthorized_error(self):
        with pytest.raises(KaiAuthenticationError) as exc_info:
            raise_for_error_response({
                "code": "unauthorized:chat",
                "message": "Invalid credentials",
            })
        assert exc_info.value.code == "unauthorized:chat"

    def test_forbidden_error(self):
        with pytest.raises(KaiForbiddenError):
            raise_for_error_response({
                "code": "forbidden:chat",
                "message": "Access denied",
            })

    def test_not_found_error(self):
        with pytest.raises(KaiNotFoundError):
            raise_for_error_response({
                "code": "not_found:chat",
                "message": "Resource not found",
            })

    def test_rate_limit_error(self):
        with pytest.raises(KaiRateLimitError):
            raise_for_error_response({
                "code": "rate_limit:chat",
                "message": "Rate limit exceeded",
            })

    def test_bad_request_error(self):
        with pytest.raises(KaiBadRequestError):
            raise_for_error_response({
                "code": "bad_request:api",
                "message": "Invalid request body",
            })

    def test_unknown_code_falls_back_to_base(self):
        with pytest.raises(KaiError) as exc_info:
            raise_for_error_response({
                "code": "unknown:error",
                "message": "Unknown error type",
            })
        # Should be base KaiError, not a subclass
        assert type(exc_info.value) is KaiError

    def test_prefix_matching(self):
        """Test that prefix matching works for variant codes."""
        with pytest.raises(KaiAuthenticationError):
            raise_for_error_response({
                "code": "unauthorized:something_else",
                "message": "Auth error variant",
            })

    def test_error_with_cause(self):
        with pytest.raises(KaiBadRequestError) as exc_info:
            raise_for_error_response({
                "code": "bad_request:api",
                "message": "Validation failed",
                "cause": "Missing field: name",
            })
        assert exc_info.value.cause == "Missing field: name"

    def test_missing_message_uses_default(self):
        with pytest.raises(KaiError) as exc_info:
            raise_for_error_response({
                "code": "some:error",
            })
        assert exc_info.value.message == "Unknown error"

    def test_response_data_preserved(self):
        response_data = {
            "code": "test:error",
            "message": "Test error",
            "extra_field": "extra_value",
        }
        with pytest.raises(KaiError) as exc_info:
            raise_for_error_response(response_data)
        assert exc_info.value.response_data == response_data


class TestAgentErrorEnvelope:
    """The kai-agent backend nests its error under an ``error`` key.

    Shape (from kai-agent's errorResponseSchema)::

        {"error": {"type", "surface", "message", "subtype"?, "exceptionId"?}}

    Before this was handled, every kai-agent failure produced a bare
    ``KaiError("Unknown error")`` — losing the message, the exception ID, and
    any way to distinguish a 404 from a 500.
    """

    @pytest.mark.parametrize(
        "error_type,expected",
        [
            ("not_found", KaiNotFoundError),
            ("unauthorized", KaiAuthenticationError),
            ("forbidden", KaiForbiddenError),
            ("bad_request", KaiBadRequestError),
            ("rate_limit", KaiRateLimitError),
            # Types with no dedicated class fall back to the base error.
            ("internal", KaiError),
            ("conflict", KaiError),
            ("offline", KaiError),
            ("bad_response", KaiError),
            ("payload_too_large", KaiError),
        ],
    )
    def test_error_type_maps_to_exception_class(self, error_type, expected):
        payload = {
            "error": {"type": error_type, "surface": "api", "message": "boom"}
        }
        with pytest.raises(KaiError) as exc_info:
            raise_for_error_response(payload)
        assert type(exc_info.value) is expected

    def test_message_and_exception_id_preserved(self):
        """The real message and exceptionId must survive — this is what makes
        a kai-agent failure debuggable."""
        payload = {
            "error": {
                "type": "not_found",
                "surface": "api",
                "message": "No pending approval found",
                "exceptionId": "KAI-abc123-deadbeef",
            }
        }
        with pytest.raises(KaiNotFoundError) as exc_info:
            raise_for_error_response(payload)

        err = exc_info.value
        assert err.message == "No pending approval found"
        assert err.code == "not_found:api"
        assert err.cause == "KAI-abc123-deadbeef"
        assert err.response_data == payload
        assert "Unknown error" not in str(err)

    def test_missing_surface_falls_back_to_bare_type(self):
        payload = {"error": {"type": "internal", "message": "boom"}}
        with pytest.raises(KaiError) as exc_info:
            raise_for_error_response(payload)
        assert exc_info.value.code == "internal"

    @pytest.mark.parametrize(
        "payload",
        [
            {"error": "a string, not an object"},
            {"error": {"surface": "api", "message": "no type"}},
            {"error": {"type": "not_found", "surface": "api"}},  # no message
            {"error": {"type": 500, "message": "type not a string"}},
        ],
        ids=["error_not_dict", "no_type", "no_message", "type_not_str"],
    )
    def test_non_conforming_envelope_falls_through_to_legacy(self, payload):
        """A malformed envelope must not crash — it falls back to legacy parsing."""
        with pytest.raises(KaiError) as exc_info:
            raise_for_error_response(payload)
        assert type(exc_info.value) is KaiError

    def test_legacy_top_level_format_still_works(self):
        """kai-assistant's flat code/message format must keep working."""
        with pytest.raises(KaiNotFoundError) as exc_info:
            raise_for_error_response({"code": "not_found:chat", "message": "gone"})
        assert exc_info.value.message == "gone"
        assert exc_info.value.code == "not_found:chat"

    def test_agent_map_covers_the_classed_types(self):
        assert AGENT_ERROR_TYPE_MAP == {
            "bad_request": KaiBadRequestError,
            "unauthorized": KaiAuthenticationError,
            "forbidden": KaiForbiddenError,
            "not_found": KaiNotFoundError,
            "rate_limit": KaiRateLimitError,
        }



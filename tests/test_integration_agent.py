"""End-to-end tests of the kai-agent approval flow against a stub backend.

Every other CLI test mocks the client, so the CLI and the client are never
exercised together: a mocked `send_message` yields hand-built event objects, and
nothing proves the real SSE bytes parse into those objects or that the approval
POST is issued while the stream is still open.

These tests close that gap. A stdlib HTTP server speaks kai-agent's real wire
protocol and — crucially — *blocks the chat stream* until the decision is POSTed
to the approval endpoint, exactly as kai-agent's approval handler does. The path
under test is real throughout: real httpx, real SSE parsing, real
``_send_and_display_agent`` loop, real approval POST.

The mid-stream contract is what makes this worth the machinery: if the CLI ever
regresses to deciding *after* draining the stream (the shape it originally had),
the stub never receives the POST, the stream times out, and these tests fail.
A mock cannot catch that.

``ThreadingHTTPServer`` serves the approval POST on a second thread while the
chat handler blocks on an ``Event``.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from kai_client import KaiBackend, KaiClient, KaiError, KaiNotFoundError
from kai_client.cli import _send_and_display_agent

TOOL_CALL_ID = "tool-call-abc123"
STREAM_BLOCK_TIMEOUT = 10  # generous; a passing run resolves in milliseconds


class _StubAgentState:
    """Shared state between the request handler threads."""

    def __init__(self, approval_mode: str) -> None:
        self.approval_mode = approval_mode
        self.lock = threading.Lock()
        self.pending: dict[str, dict] = {}
        self.log: list[str] = []

    def note(self, msg: str) -> None:
        with self.lock:
            self.log.append(msg)


def _make_handler(state: _StubAgentState):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, format, *args):  # noqa: A002 - silence access log
            pass

        def _json(self, status, obj):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _agent_error(self, status, type_, message):
            """kai-agent's nested error envelope."""
            self._json(
                status,
                {
                    "error": {
                        "type": type_,
                        "surface": "api",
                        "message": message,
                        "exceptionId": "KAI-test-00000000",
                    }
                },
            )

        def _send_event(self, obj):
            self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode())
            self.wfile.flush()

        def do_POST(self):
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/chat":
                self._chat(body)
            elif self.path.startswith("/api/chat/") and self.path.endswith("/approval"):
                self._approval(self.path.split("/")[3], body)
            else:  # pragma: no cover - defensive
                self._agent_error(404, "not_found", "no route")

        def _chat(self, body):
            chat_id = body["id"]
            state.note("chat:start")
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Connection", "close")
            self.end_headers()

            self._send_event({"type": "start", "messageId": "msg-1"})
            self._send_event(
                {
                    "type": "tool-input-available",
                    "toolCallId": TOOL_CALL_ID,
                    "toolName": "create_bucket",
                    "input": {"name": "test-bucket"},
                }
            )

            # Block until the approval POST lands on another thread.
            slot = {"event": threading.Event(), "approved": False}
            with state.lock:
                state.pending[chat_id] = slot
            state.note("chat:blocked")

            arrived = slot["event"].wait(timeout=STREAM_BLOCK_TIMEOUT)
            with state.lock:
                state.pending.pop(chat_id, None)

            if not arrived:
                state.note("chat:TIMEOUT")
                self._send_event({"type": "finish", "finishReason": "error"})
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                return

            state.note(f"chat:resumed:approved={slot['approved']}")
            if slot["approved"]:
                self._send_event(
                    {
                        "type": "tool-output-available",
                        "toolCallId": TOOL_CALL_ID,
                        "output": {"id": "in.c-test-bucket"},
                    }
                )
                text = "Bucket created!"
            else:
                text = "Okay, skipped it."
            self._send_event({"type": "text-start", "id": "0"})
            self._send_event({"type": "text-delta", "id": "0", "delta": text})
            self._send_event({"type": "text-end", "id": "0"})
            self._send_event({"type": "finish", "finishReason": "stop"})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            state.note("chat:done")

        def _approval(self, chat_id, body):
            approved = bool(body.get("approved"))
            state.note(f"approval:POST:{body.get('toolUseId')}:approved={approved}")

            def unblock(value):
                with state.lock:
                    slot = state.pending.get(chat_id)
                if slot and not slot["event"].is_set():
                    slot["approved"] = value
                    slot["event"].set()

            if state.approval_mode == "not_found":
                unblock(True)  # let the run finish so the test terminates
                self._agent_error(404, "not_found", "No pending approval found")
                return
            if state.approval_mode == "server_error":
                unblock(True)
                self._agent_error(500, "internal", "An unexpected error occurred")
                return

            unblock(approved)
            self._json(200, {"success": True, "toolUseId": TOOL_CALL_ID, "approved": approved})

    return Handler


@pytest.fixture
def stub_agent(request):
    """Run a stub kai-agent on a free port. Param selects the approval mode."""
    mode = getattr(request, "param", "ok")
    state = _StubAgentState(mode)
    server = ThreadingHTTPServer(("127.0.0.1", 0), _make_handler(state))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", state
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _client(base_url: str) -> KaiClient:
    return KaiClient(
        storage_api_token="test-token",
        storage_api_url="https://connection.example.com",
        base_url=base_url,
        backend=KaiBackend.AGENT,
        stream_timeout=20.0,
    )


@pytest.mark.asyncio
async def test_approval_is_submitted_while_the_stream_is_open(stub_agent, capsys):
    """The crux: the POST must arrive while the server still holds the stream.

    Deciding after the stream drains — the CLI's original shape — makes the stub
    time out instead of resuming.
    """
    base_url, state = stub_agent
    async with _client(base_url) as client:
        await _send_and_display_agent(
            client, "chat-1", "Create a bucket", auto_approve=True, json_output=False
        )

    assert "chat:TIMEOUT" not in state.log
    assert state.log == [
        "chat:start",
        "chat:blocked",
        f"approval:POST:{TOOL_CALL_ID}:approved=True",
        "chat:resumed:approved=True",
        "chat:done",
    ]
    # The post-approval remainder of the same stream was consumed and rendered.
    assert "Bucket created!" in capsys.readouterr().out


@pytest.mark.asyncio
async def test_denial_is_submitted_and_stream_continues(stub_agent, capsys, monkeypatch):
    """Declining the prompt POSTs approved=False and keeps consuming the stream."""
    base_url, state = stub_agent
    monkeypatch.setattr("kai_client.cli.click.confirm", lambda *a, **kw: False)

    async with _client(base_url) as client:
        await _send_and_display_agent(
            client, "chat-1", "Create a bucket", auto_approve=False, json_output=False
        )

    assert f"approval:POST:{TOOL_CALL_ID}:approved=False" in state.log
    assert "chat:resumed:approved=False" in state.log
    assert "chat:TIMEOUT" not in state.log
    assert "Okay, skipped it." in capsys.readouterr().out


@pytest.mark.parametrize("stub_agent", ["not_found"], indirect=True)
@pytest.mark.asyncio
async def test_approval_404_is_not_fatal(stub_agent, capsys):
    """kai-agent announces auto-executed tools too, so the POST can 404.

    Also pins that the nested error envelope is parsed into KaiNotFoundError —
    without that, the CLI's narrow `except` could not catch this.
    """
    base_url, state = stub_agent
    async with _client(base_url) as client:
        await _send_and_display_agent(
            client, "chat-1", "Read something", auto_approve=True, json_output=False
        )

    captured = capsys.readouterr()
    assert "No pending approval found" in captured.err
    assert "chat:done" in state.log
    assert "Bucket created!" in captured.out  # stream still consumed


@pytest.mark.parametrize("stub_agent", ["server_error"], indirect=True)
@pytest.mark.asyncio
async def test_approval_500_propagates(stub_agent):
    """A real failure must not be swallowed.

    Swallowing it would resume the loop with the tool still pending server-side,
    stalling until a timeout with one stderr line as the only clue.
    """
    base_url, _state = stub_agent
    async with _client(base_url) as client:
        with pytest.raises(KaiError) as exc_info:
            await _send_and_display_agent(
                client, "chat-1", "Create a bucket", auto_approve=True, json_output=False
            )

    err = exc_info.value
    assert not isinstance(err, KaiNotFoundError)
    # The real message and exception id survive, rather than "Unknown error".
    assert err.message == "An unexpected error occurred"
    assert err.code == "internal:api"
    assert err.cause == "KAI-test-00000000"


@pytest.mark.asyncio
async def test_json_output_stdout_is_parseable(stub_agent, capsys):
    """Under --json-output every stdout line must be machine-readable."""
    base_url, _state = stub_agent
    async with _client(base_url) as client:
        await _send_and_display_agent(
            client, "chat-1", "Create a bucket", auto_approve=True, json_output=True
        )

    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines() if ln.strip()]
    assert lines
    for line in lines:
        json.loads(line)  # raises if the CLI leaked prose onto stdout

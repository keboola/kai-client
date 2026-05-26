"""Command-line interface for the Kai client."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

import click
import httpx
from dotenv import load_dotenv

# Load .env.local file if it exists (before any commands run)
_env_local = Path.cwd() / ".env.local"
if _env_local.exists():
    load_dotenv(_env_local)

from kai_client import KaiClient, __version__  # noqa: E402
from kai_client.exceptions import KaiError  # noqa: E402
from kai_client.models import ToolApprovalRequestEvent  # noqa: E402
from kai_client.types import VoteType  # noqa: E402


def get_env_or_error(name: str) -> str:
    """Get environment variable or exit with error."""
    value = os.environ.get(name)
    if not value:
        click.echo(f"Error: {name} environment variable is required", err=True)
        click.echo(f"Set it with: export {name}=your-value", err=True)
        sys.exit(1)
    return value


def run_async(coro):
    """Run an async coroutine."""
    return asyncio.run(coro)


@click.group()
@click.version_option(version=__version__, prog_name="kai")
@click.option(
    "--token",
    envvar="STORAGE_API_TOKEN",
    help="Keboola Storage API token (or set STORAGE_API_TOKEN env var)",
)
@click.option(
    "--url",
    envvar="STORAGE_API_URL",
    help="Keboola Storage API URL (or set STORAGE_API_URL env var)",
)
@click.option(
    "--base-url",
    envvar="KAI_BASE_URL",
    help="Kai API base URL for local development (default: auto-discover)",
)
@click.pass_context
def main(ctx, token: Optional[str], url: Optional[str], base_url: Optional[str]):
    """
    Kai CLI - Command-line interface for the Keboola AI Assistant.

    Requires STORAGE_API_TOKEN and STORAGE_API_URL environment variables,
    or use --token and --url options.

    Examples:

        # Check server health
        kai ping

        # Diagnose token / service / quota when things misbehave
        kai verify

        # Start an interactive chat
        kai chat

        # Send a single message
        kai chat -m "What tables do I have?"

        # View chat history
        kai history

        # Get details of a specific chat
        kai get-chat <chat-id>
    """
    ctx.ensure_object(dict)
    ctx.obj["token"] = token
    ctx.obj["url"] = url
    ctx.obj["base_url"] = base_url


async def get_client(ctx) -> KaiClient:
    """Create and return a KaiClient from context."""
    token = ctx.obj.get("token") or get_env_or_error("STORAGE_API_TOKEN")
    url = ctx.obj.get("url") or get_env_or_error("STORAGE_API_URL")
    base_url = ctx.obj.get("base_url")

    if base_url:
        # Local development mode
        return KaiClient(
            storage_api_token=token,
            storage_api_url=url,
            base_url=base_url,
        )
    else:
        # Production mode - auto-discover URL
        return await KaiClient.from_storage_api(
            storage_api_token=token,
            storage_api_url=url,
        )


@main.command()
@click.pass_context
def ping(ctx):
    """Check if the Kai server is alive."""

    async def _ping():
        client = await get_client(ctx)
        async with client:
            response = await client.ping()
            click.echo(f"Server is alive: {response.timestamp.isoformat()}")

    run_async(_ping())


@main.command()
@click.pass_context
def info(ctx):
    """Get server information."""

    async def _info():
        client = await get_client(ctx)
        async with client:
            response = await client.info()
            click.echo(f"App: {response.app_name} v{response.app_version}")
            click.echo(f"Server: v{response.server_version}")
            click.echo(f"Uptime: {response.uptime:.1f}s")
            # Handle connected_mcp being either a list or a single dict
            mcp_list = response.connected_mcp
            if isinstance(mcp_list, dict):
                mcp_list = [mcp_list]  # Wrap single dict in a list
            click.echo(f"Connected MCP servers: {len(mcp_list)}")
            for mcp in mcp_list:
                if isinstance(mcp, dict):
                    name = mcp.get("name") or mcp.get("url", "unknown")
                    status = mcp.get("status", "unknown")
                    click.echo(f"  - {name}: {status}")

    run_async(_info())


class _VerifyRecorder:
    """Collects per-check results for `kai verify` and prints them inline."""

    def __init__(self, json_output: bool) -> None:
        self.json_output = json_output
        self.report: dict[str, Any] = {"ok": True, "checks": {}}

    def record(self, name: str, ok: bool, summary: str, **extra: Any) -> None:
        self.report["checks"][name] = {"ok": ok, "summary": summary, **extra}
        if not ok:
            self.report["ok"] = False
        if not self.json_output:
            mark = click.style("✓", fg="green") if ok else click.style("✗", fg="red")
            click.echo(f"{mark} {name}: {summary}")


def _format_kai_error(e: KaiError) -> str:
    """Render a KaiError as `code: message`, falling back to message-only."""
    if e.code and e.message:
        return f"{e.code}: {e.message}"
    return e.message or str(e)


def _safe_json_body(resp: httpx.Response) -> dict[str, Any]:
    """Parse `resp` as a JSON object, falling back to `{'error': <text>}`."""
    if "application/json" in resp.headers.get("content-type", ""):
        try:
            parsed = resp.json()
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    return {"error": resp.text}


async def _check_token(url: str, token: str, recorder: _VerifyRecorder) -> Optional[dict[str, Any]]:
    """Verify the token via Storage API; return the parsed token info on success."""
    async with httpx.AsyncClient() as http_client:
        try:
            resp = await http_client.get(
                f"{url.rstrip('/')}/v2/storage/tokens/verify",
                headers={"x-storageapi-token": token},
                timeout=30.0,
            )
        except httpx.RequestError as e:
            recorder.record("token", False, f"connection error: {e}")
            return None

    if resp.status_code >= 400:
        body = _safe_json_body(resp)
        code = body.get("code") or f"http:{resp.status_code}"
        msg = body.get("error") or body.get("message") or resp.reason_phrase
        recorder.record("token", False, f"HTTP {resp.status_code} {code}: {msg}")
        return None

    parsed = resp.json()
    if not isinstance(parsed, dict):
        recorder.record("token", False, f"unexpected response shape: {type(parsed).__name__}")
        return None

    owner = parsed.get("owner") or {}
    project_id = owner.get("id")
    project_name = owner.get("name", "?")
    description = parsed.get("description", "?")
    is_master = parsed.get("isMasterToken", False)
    token_type = "master" if is_master else "scoped"
    summary = f"project {project_id} ({project_name}), token '{description}' [{token_type}]"
    recorder.record(
        "token",
        True,
        summary,
        project_id=project_id,
        project_name=project_name,
        token_description=description,
        is_master_token=is_master,
    )
    return parsed


async def _check_service_discovery(
    token: str, url: str, base_url: Optional[str], recorder: _VerifyRecorder
) -> Optional[KaiClient]:
    """Build a KaiClient (auto-discover or honour --base-url for local dev)."""
    try:
        if base_url:
            client = KaiClient(storage_api_token=token, storage_api_url=url, base_url=base_url)
            recorder.record("service-discovery", True, f"using --base-url {base_url}")
        else:
            client = await KaiClient.from_storage_api(storage_api_token=token, storage_api_url=url)
            recorder.record(
                "service-discovery",
                True,
                f"kai-assistant at {client.base_url}",
            )
    except KaiError as e:
        recorder.record(
            "service-discovery",
            False,
            _format_kai_error(e),
            code=e.code,
            message=e.message,
        )
        return None
    return client


async def _check_reachability(client: KaiClient, recorder: _VerifyRecorder) -> None:
    """Ping + info (no auth). Records each independently."""
    try:
        ping_resp = await client.ping()
        recorder.record("ping", True, f"server alive at {ping_resp.timestamp.isoformat()}")
    except KaiError as e:
        recorder.record("ping", False, _format_kai_error(e), code=e.code, message=e.message)

    try:
        info_resp = await client.info()
        recorder.record(
            "info",
            True,
            f"{info_resp.app_name} v{info_resp.app_version} "
            f"(server v{info_resp.server_version}, uptime {info_resp.uptime:.0f}s)",
            server_version=info_resp.server_version,
        )
    except KaiError as e:
        recorder.record("info", False, _format_kai_error(e), code=e.code, message=e.message)


async def _check_usage(client: KaiClient, recorder: _VerifyRecorder) -> None:
    """Authenticated probe + monthly message quota.

    The KaiError handler renders any upstream `{code, message}` cleanly. The
    headline symptom this command was built for is 429 ``rate_limit:chat``,
    but 401/403/timeout etc. all surface through the same path.
    """
    try:
        usage = await client.get_usage()
        remaining = usage.messages_limit - usage.messages_used
        recorder.record(
            "usage",
            True,
            f"{usage.messages_used}/{usage.messages_limit} messages used "
            f"(resets {usage.reset_date.date().isoformat()}, {remaining} left)",
            messages_used=usage.messages_used,
            messages_limit=usage.messages_limit,
            reset_date=usage.reset_date.isoformat(),
        )
    except KaiError as e:
        recorder.record("usage", False, _format_kai_error(e), code=e.code, message=e.message)


def _emit_verify_footer(recorder: _VerifyRecorder) -> None:
    """Print the final summary line (JSON dump or human-readable footer)."""
    if recorder.json_output:
        click.echo(json.dumps(recorder.report, indent=2, default=str))
    elif recorder.report["ok"]:
        click.echo()
        click.echo(click.style("All checks passed.", fg="green"))
    else:
        click.echo()
        click.echo(click.style("Some checks failed — see above.", fg="red"), err=True)


@main.command()
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def verify(ctx, json_output: bool):
    """
    Diagnose Kai setup: token identity, service reachability, message quota.

    Use this when "it works in the Keboola platform UI but my app errors out".
    Verify confirms which project/user the token resolves to, that the
    kai-assistant service is reachable, and your current monthly message usage.

    Examples:

        kai verify
        kai verify --json-output
    """

    async def _verify():
        token = ctx.obj.get("token") or get_env_or_error("STORAGE_API_TOKEN")
        url = ctx.obj.get("url") or get_env_or_error("STORAGE_API_URL")
        base_url = ctx.obj.get("base_url")

        recorder = _VerifyRecorder(json_output)
        if not json_output:
            click.echo(f"Storage API URL: {url}")

        if await _check_token(url, token, recorder) is None:
            _emit_verify_footer(recorder)
            sys.exit(1)

        client = await _check_service_discovery(token, url, base_url, recorder)
        if client is None:
            _emit_verify_footer(recorder)
            sys.exit(1)

        async with client:
            await _check_reachability(client, recorder)
            await _check_usage(client, recorder)

        _emit_verify_footer(recorder)
        sys.exit(0 if recorder.report["ok"] else 1)

    run_async(_verify())


@main.command()
@click.option("-m", "--message", help="Send a single message instead of interactive mode")
@click.option(
    "--chat-id",
    help="Continue an existing chat (default: new chat)",
)
@click.option(
    "--auto-approve",
    is_flag=True,
    help="Automatically approve tool calls that require confirmation",
)
@click.option(
    "--json-output",
    is_flag=True,
    help="Output raw JSON events instead of formatted text",
)
@click.pass_context
def chat(
    ctx,
    message: Optional[str],
    chat_id: Optional[str],
    auto_approve: bool,
    json_output: bool,
):
    """
    Start a chat with the Keboola AI Assistant.

    In interactive mode, type your messages and press Enter to send.
    Type 'exit' or 'quit' to end the chat, or press Ctrl+C.

    Examples:

        # Interactive chat
        kai chat

        # Single message
        kai chat -m "Show me my tables"

        # Continue existing chat
        kai chat --chat-id abc-123 -m "Tell me more"

        # Auto-approve tool calls
        kai chat --auto-approve -m "Create a bucket called test"
    """

    async def _chat():
        client = await get_client(ctx)
        async with client:
            nonlocal chat_id
            if not chat_id:
                chat_id = client.new_chat_id()
                if not json_output:
                    click.echo(f"Chat ID: {chat_id}")

            if message:
                # Single message mode
                await send_and_display(client, chat_id, message, auto_approve, json_output)
            else:
                # Interactive mode
                if not json_output:
                    click.echo("Interactive chat mode. Type 'exit' to quit.")
                    click.echo("-" * 50)

                while True:
                    try:
                        user_input = click.prompt("You", default="", show_default=False)
                        if user_input.lower() in ("exit", "quit", "q"):
                            break
                        if not user_input.strip():
                            continue

                        await send_and_display(
                            client, chat_id, user_input, auto_approve, json_output
                        )
                        if not json_output:
                            click.echo()  # Blank line after response

                    except click.exceptions.Abort:
                        break

                if not json_output:
                    click.echo("\nChat ended.")

    run_async(_chat())


async def display_tool_result_events(
    events_generator,
    json_output: bool,
    approved_tool_name: str,
):
    """Display events from a tool result response."""
    async for event in events_generator:
        if json_output:
            click.echo(json.dumps(event.model_dump(), default=str))
        else:
            if event.type == "text":
                click.echo(event.text, nl=False)
            elif event.type == "tool-call" and event.state == "output-available":
                tool_name = event.tool_name or approved_tool_name
                click.echo(f"\n[{tool_name} completed]", nl=False)
            elif event.type == "tool-output-error":
                click.echo(f"\n[Tool Error: {event.error_text}]", err=True)
            elif event.type == "finish":
                click.echo()
                break


async def send_and_display(
    client: KaiClient,
    chat_id: str,
    message: str,
    auto_approve: bool,
    json_output: bool,
):
    """Send a message and display the response."""
    pending_approval = None
    # Track v6 approval request (separate event with approvalId)
    pending_approval_id: str | None = None
    # Track current tool call to handle null tool_name in output-available events
    current_tool_name: dict[str, str] = {}  # tool_call_id -> tool_name

    async for event in client.send_message(chat_id, message):
        if json_output:
            click.echo(json.dumps(event.model_dump(), default=str))
        else:
            if event.type == "text":
                click.echo(event.text, nl=False)
            elif event.type == "step-start":
                click.echo("\n[Processing...]", nl=False)
            elif event.type == "tool-call":
                # Track tool names by tool_call_id
                if event.tool_call_id and event.tool_name:
                    current_tool_name[event.tool_call_id] = event.tool_name
                # Get the tool name, falling back to tracked name if null
                tool_name = event.tool_name or current_tool_name.get(
                    event.tool_call_id or "", "unknown"
                )

                if event.state == "started":
                    click.echo(f"\n[Calling {tool_name}...]", nl=False)
                elif event.state == "input-available":
                    click.echo(f"\n[Tool {tool_name} requires approval]")
                    pending_approval = event
                elif event.state == "output-available":
                    click.echo(f"\n[{tool_name} completed]", nl=False)
                    # Tool completed, clear pending approval if this was the pending tool
                    if pending_approval and pending_approval.tool_call_id == event.tool_call_id:
                        pending_approval = None
                        pending_approval_id = None
            elif event.type == "tool-approval-request":
                # v6 approval flow: capture the approval ID
                if isinstance(event, ToolApprovalRequestEvent):
                    pending_approval_id = event.approval_id
            elif event.type == "tool-output-error":
                click.echo(f"\n[Tool Error: {event.error_text}]", err=True)
            elif event.type == "finish":
                if not json_output:
                    click.echo()  # Final newline
            elif event.type == "error":
                click.echo(f"\n[Error: {event.message}]", err=True)

    # Handle tool approval if needed (pending_approval is set when a tool needs approval
    # and cleared when that tool completes)
    if pending_approval:
        # Get the tool name from tracking dict or pending_approval
        approved_tool_name = pending_approval.tool_name or current_tool_name.get(
            pending_approval.tool_call_id or "", "unknown"
        )

        # Determine which approval flow to use
        use_v6 = bool(pending_approval_id)

        if auto_approve:
            click.echo("[Auto-approving...]")
            if use_v6:
                stream = client.approve_tool(
                    chat_id=chat_id,
                    approval_id=pending_approval_id,
                )
            else:
                stream = client.confirm_tool(
                    chat_id=chat_id,
                    tool_call_id=pending_approval.tool_call_id,
                    tool_name=approved_tool_name,
                )
            await display_tool_result_events(stream, json_output, approved_tool_name)
        elif click.confirm("Approve this tool call?"):
            if use_v6:
                stream = client.approve_tool(
                    chat_id=chat_id,
                    approval_id=pending_approval_id,
                )
            else:
                stream = client.confirm_tool(
                    chat_id=chat_id,
                    tool_call_id=pending_approval.tool_call_id,
                    tool_name=approved_tool_name,
                )
            await display_tool_result_events(stream, json_output, approved_tool_name)
        else:
            if use_v6:
                stream = client.reject_tool(
                    chat_id=chat_id,
                    approval_id=pending_approval_id,
                )
            else:
                stream = client.deny_tool(
                    chat_id=chat_id,
                    tool_call_id=pending_approval.tool_call_id,
                    tool_name=approved_tool_name,
                )
            await display_tool_result_events(stream, json_output, approved_tool_name)


@main.command()
@click.option("-n", "--limit", default=10, help="Number of chats to show (default: 10)")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def history(ctx, limit: int, json_output: bool):
    """View chat history."""

    async def _history():
        client = await get_client(ctx)
        async with client:
            response = await client.get_history(limit=limit)

            if json_output:
                chats = [chat.model_dump() for chat in response.chats]
                click.echo(json.dumps({"chats": chats, "hasMore": response.has_more}, default=str))
            else:
                if not response.chats:
                    click.echo("No chat history found.")
                    return

                for chat in response.chats:
                    created = chat.created_at.strftime("%Y-%m-%d %H:%M") if chat.created_at else "?"
                    title = chat.title or "(no title)"
                    click.echo(f"{chat.id}  {created}  {title[:50]}")

                if response.has_more:
                    click.echo("\n... and more (use --limit to see more)")

    run_async(_history())


@main.command("get-chat")
@click.argument("chat_id")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def get_chat(ctx, chat_id: str, json_output: bool):
    """Get details of a specific chat including messages."""

    async def _get_chat():
        client = await get_client(ctx)
        async with client:
            chat = await client.get_chat(chat_id)

            if json_output:
                click.echo(json.dumps(chat.model_dump(), default=str))
            else:
                click.echo(f"Chat ID: {chat.id}")
                click.echo(f"Title: {chat.title or '(no title)'}")
                click.echo(f"Messages: {len(chat.messages)}")
                click.echo("-" * 50)

                for msg in chat.messages:
                    role = msg.role.upper()
                    click.echo(f"\n[{role}]")
                    for part in msg.parts:
                        if hasattr(part, "text"):
                            click.echo(part.text)
                        elif hasattr(part, "type"):
                            click.echo(f"[{part.type}]")

    run_async(_get_chat())


@main.command("delete-chat")
@click.argument("chat_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
@click.pass_context
def delete_chat(ctx, chat_id: str, yes: bool):
    """Delete a chat."""

    if not yes:
        if not click.confirm(f"Delete chat {chat_id}?"):
            click.echo("Cancelled.")
            return

    async def _delete():
        client = await get_client(ctx)
        async with client:
            await client.delete_chat(chat_id)
            click.echo(f"Deleted chat {chat_id}")

    run_async(_delete())


@main.command()
@click.argument("chat_id")
@click.argument("message_id")
@click.argument("vote_type", type=click.Choice(["up", "down"]))
@click.pass_context
def vote(ctx, chat_id: str, message_id: str, vote_type: str):
    """Vote on a message (up or down)."""

    async def _vote():
        client = await get_client(ctx)
        async with client:
            vtype = VoteType.UP if vote_type == "up" else VoteType.DOWN
            result = await client.vote(chat_id, message_id, vtype)
            click.echo(f"Voted {result.type} on message {message_id}")

    run_async(_vote())


@main.command("get-votes")
@click.argument("chat_id")
@click.option("--json-output", is_flag=True, help="Output as JSON")
@click.pass_context
def get_votes(ctx, chat_id: str, json_output: bool):
    """Get votes for a chat."""

    async def _get_votes():
        client = await get_client(ctx)
        async with client:
            votes = await client.get_votes(chat_id)

            if json_output:
                click.echo(json.dumps([v.model_dump() for v in votes], default=str))
            else:
                if not votes:
                    click.echo("No votes found.")
                    return

                for v in votes:
                    click.echo(f"{v.message_id}: {v.type}")

    run_async(_get_votes())


if __name__ == "__main__":
    main()

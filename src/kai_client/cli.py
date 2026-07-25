"""Command-line interface for the Kai client."""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional

import click
from dotenv import load_dotenv

# Load .env.local file if it exists (before any commands run)
_env_local = Path.cwd() / ".env.local"
if _env_local.exists():
    load_dotenv(_env_local)

from kai_client import KaiBackend, KaiClient, KaiError, __version__  # noqa: E402
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
@click.option(
    "--service",
    type=click.Choice(["agent", "assistant", "kai-agent", "kai-assistant"]),
    default="agent",
    envvar="KAI_SERVICE",
    help=(
        "Which Kai backend to auto-discover: agent (default) or assistant; "
        "the full service ids kai-agent/kai-assistant are also accepted. "
        "Ignored with --base-url."
    ),
)
@click.pass_context
def main(ctx, token: Optional[str], url: Optional[str], base_url: Optional[str], service: str):
    """
    Kai CLI - Command-line interface for the Keboola AI Assistant.

    Requires STORAGE_API_TOKEN and STORAGE_API_URL environment variables,
    or use --token and --url options.

    Examples:

        # Check server health
        kai ping

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
    ctx.obj["service"] = service


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

    # Production mode - auto-discover URL
    service_map = {
        "agent": KaiBackend.AGENT,
        "kai-agent": KaiBackend.AGENT,
        "assistant": KaiBackend.ASSISTANT,
        "kai-assistant": KaiBackend.ASSISTANT,
    }
    service = service_map[ctx.obj.get("service") or "agent"]
    return await KaiClient.from_storage_api(
        storage_api_token=token,
        storage_api_url=url,
        service=service,
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
                await send_and_display(
                    client, chat_id, message, auto_approve, json_output
                )
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


def _display_event(
    event,
    json_output: bool,
    current_tool_name: dict[str, str],
) -> None:
    """Render a single SSE event (shared by both approval flows).

    ``current_tool_name`` maps tool_call_id -> tool_name and is updated in place,
    so that output-available events with a null tool_name still display a name.
    """
    if json_output:
        click.echo(json.dumps(event.model_dump(), default=str))
        return

    if event.type == "text":
        click.echo(event.text, nl=False)
    elif event.type == "step-start":
        click.echo("\n[Processing...]", nl=False)
    elif event.type == "tool-call":
        # Track tool names by tool_call_id
        if event.tool_call_id and event.tool_name:
            current_tool_name[event.tool_call_id] = event.tool_name
        # Get the tool name, falling back to tracked name if null
        tool_name = event.tool_name or current_tool_name.get(event.tool_call_id or "", "unknown")

        if event.state == "started":
            click.echo(f"\n[Calling {tool_name}...]", nl=False)
        elif event.state == "input-available":
            click.echo(f"\n[Tool {tool_name} requires approval]")
        elif event.state == "output-available":
            click.echo(f"\n[{tool_name} completed]", nl=False)
    elif event.type == "tool-output-error":
        click.echo(f"\n[Tool Error: {event.error_text}]", err=True)
    elif event.type == "finish":
        click.echo()  # Final newline
    elif event.type == "error":
        click.echo(f"\n[Error: {event.message}]", err=True)


def _decide_approval(auto_approve: bool, json_output: bool) -> bool:
    """Ask the user (or auto-approve) whether to run a pending tool call."""
    if auto_approve:
        if not json_output:
            click.echo("[Auto-approving...]")
        return True
    return click.confirm("Approve this tool call?")


async def send_and_display(
    client: KaiClient,
    chat_id: str,
    message: str,
    auto_approve: bool,
    json_output: bool,
):
    """Send a message and display the response, handling tool approvals.

    The two backends use incompatible approval protocols, so the flow is chosen
    from ``client.backend``:

    - ``KaiBackend.ASSISTANT`` -> the legacy/v6 flow (``approve_tool`` /
      ``confirm_tool``), which replies *after* the first stream ends.
    - ``KaiBackend.AGENT`` -> ``submit_approval``, which must be called while the
      original stream is still open.

    ``client.backend`` is ``None`` when the client was built directly instead of
    through discovery — for the CLI that is the ``--base-url`` local-dev path,
    where the backend behind the URL is unknown. We assume the agent protocol
    there: kai-agent is the library default, it is the modern protocol, and it is
    what a locally-run backend is expected to speak.
    """
    if client.backend is KaiBackend.ASSISTANT:
        await _send_and_display_v6(client, chat_id, message, auto_approve, json_output)
    else:
        await _send_and_display_agent(client, chat_id, message, auto_approve, json_output)


async def _send_and_display_agent(
    client: KaiClient,
    chat_id: str,
    message: str,
    auto_approve: bool,
    json_output: bool,
):
    """Stream a message, resolving approvals inline via ``submit_approval``.

    On kai-agent a tool that needs approval is announced by a tool-call event in
    the ``input-available`` state and the stream then blocks until the decision is
    POSTed to the approval endpoint. The decision therefore has to be made from
    inside the streaming loop; the same stream afterwards carries the
    post-approval events (tool output, further text, finish).
    """
    current_tool_name: dict[str, str] = {}
    decided: set[str] = set()

    async for event in client.send_message(chat_id, message):
        _display_event(event, json_output, current_tool_name)

        if (
            event.type != "tool-call"
            or event.state != "input-available"
            or not event.tool_call_id
            or event.tool_call_id in decided
        ):
            continue

        decided.add(event.tool_call_id)
        approved = _decide_approval(auto_approve, json_output)
        try:
            await client.submit_approval(
                chat_id=chat_id,
                tool_use_id=event.tool_call_id,
                approved=approved,
            )
        except KaiError as e:
            # Not fatal: a tool the backend auto-executes (e.g. a read-only one)
            # has no pending approval to answer. Report it and keep streaming.
            click.echo(f"\n[Approval not submitted: {e.message}]", err=True)


async def _send_and_display_v6(
    client: KaiClient,
    chat_id: str,
    message: str,
    auto_approve: bool,
    json_output: bool,
):
    """Stream a message using the legacy/v6 approval flow (kai-assistant)."""
    pending_approval = None
    # Track v6 approval request (separate event with approvalId)
    pending_approval_id: str | None = None
    # Track current tool call to handle null tool_name in output-available events
    current_tool_name: dict[str, str] = {}  # tool_call_id -> tool_name

    async for event in client.send_message(chat_id, message):
        _display_event(event, json_output, current_tool_name)
        if json_output:
            continue

        if event.type == "tool-call":
            if event.state == "input-available":
                pending_approval = event
            elif event.state == "output-available":
                # Tool completed, clear pending approval if this was the pending tool
                if pending_approval and pending_approval.tool_call_id == event.tool_call_id:
                    pending_approval = None
                    pending_approval_id = None
        elif event.type == "tool-approval-request":
            # v6 approval flow: capture the approval ID
            if isinstance(event, ToolApprovalRequestEvent):
                pending_approval_id = event.approval_id

    # Handle tool approval if needed (pending_approval is set when a tool needs approval
    # and cleared when that tool completes)
    if pending_approval:
        # Get the tool name from tracking dict or pending_approval
        approved_tool_name = (
            pending_approval.tool_name
            or current_tool_name.get(pending_approval.tool_call_id or "", "unknown")
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

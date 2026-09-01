#!/usr/bin/env python3
"""
Example demonstrating tool approval flow for write operations.

When the AI assistant calls tools that modify data (create_config, run_job, etc.),
those tools require explicit approval before execution. This example shows how to:

1. Detect when a tool requires approval (state="input-available" without immediate output)
2. Approve or deny the tool execution
3. Continue streaming the response after approval
"""

import argparse
import asyncio
import os
from pathlib import Path

# Load .env.local manually
env_file = Path(__file__).parent.parent / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()

from kai_client import KaiBackend, KaiClient, ToolCallEvent  # noqa: E402


async def run_with_auto_approve(client: KaiClient, message: str):
    """
    Run a chat that automatically approves all tool calls.

    This is useful for automated scripts that trust all AI tool calls.
    """
    chat_id = client.new_chat_id()
    print(f"Chat ID: {chat_id}")
    print(f"Sending: {message}")
    print("-" * 50)

    # Track pending tool calls that need approval
    pending_approval: ToolCallEvent | None = None

    async for event in client.send_message(chat_id, message):
        if event.type == "text":
            print(event.text, end="", flush=True)
        elif event.type == "step-start":
            print("\n[New step]", flush=True)
        elif event.type == "tool-call":
            if event.state == "started":
                print(f"\n[Tool starting: {event.tool_name}]", flush=True)
            elif event.state == "input-available":
                print(f"\n[Tool {event.tool_name} waiting for approval]", flush=True)
                print(f"  Input: {event.input}", flush=True)
                pending_approval = event
            elif event.state == "output-available":
                print(f"\n[Tool {event.tool_name} completed]", flush=True)
                pending_approval = None
        elif event.type == "finish":
            print(f"\n\n[Finished: {event.finish_reason}]")

    # If there's a pending approval after the stream ends, handle it
    if pending_approval:
        print(f"\n[AUTO-APPROVING: {pending_approval.tool_name}]")
        async for event in client.confirm_tool(
            chat_id=chat_id,
            tool_call_id=pending_approval.tool_call_id,
            tool_name=pending_approval.tool_name or "unknown",
        ):
            if event.type == "text":
                print(event.text, end="", flush=True)
            elif event.type == "tool-call":
                if event.state == "output-available":
                    print(f"\n[Tool {event.tool_name} completed]", flush=True)
            elif event.type == "finish":
                print(f"\n\n[Finished: {event.finish_reason}]")


async def run_with_interactive_approve(client: KaiClient, message: str):
    """
    Run a chat that prompts the user for approval on each tool call.

    This gives the user control over which operations are executed.
    """
    chat_id = client.new_chat_id()
    print(f"Chat ID: {chat_id}")
    print(f"Sending: {message}")
    print("-" * 50)

    async def process_stream(stream):
        """Process a stream, returning any pending approval."""
        pending = None
        async for event in stream:
            if event.type == "text":
                print(event.text, end="", flush=True)
            elif event.type == "step-start":
                print("\n[New step]", flush=True)
            elif event.type == "tool-call":
                if event.state == "started":
                    print(f"\n[Tool starting: {event.tool_name}]", flush=True)
                elif event.state == "input-available":
                    print(f"\n[Tool {event.tool_name} requires approval]", flush=True)
                    print(f"  Input: {event.input}", flush=True)
                    pending = event
                elif event.state == "output-available":
                    print(f"\n[Tool {event.tool_name} completed]", flush=True)
                    pending = None
            elif event.type == "finish":
                print(f"\n\n[Finished: {event.finish_reason}]")
        return pending

    # Process initial message
    pending = await process_stream(client.send_message(chat_id, message))

    # Handle any pending approvals interactively
    while pending:
        print()
        response = input(f"Approve {pending.tool_name}? [y/n]: ").strip().lower()

        if response in ("y", "yes"):
            print(f"[APPROVED: {pending.tool_name}]")
            stream = client.confirm_tool(
                chat_id=chat_id,
                tool_call_id=pending.tool_call_id,
                tool_name=pending.tool_name or "unknown",
            )
        else:
            print(f"[DENIED: {pending.tool_name}]")
            stream = client.deny_tool(
                chat_id=chat_id,
                tool_call_id=pending.tool_call_id,
                tool_name=pending.tool_name or "unknown",
            )

        pending = await process_stream(stream)


async def main():
    parser = argparse.ArgumentParser(
        description="Test Kai tool approval flow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Interactive mode (default) - prompts for each approval
  python tool_approval.py -m "Create a bucket called test-bucket"

  # Auto-approve mode - approves all tool calls automatically
  python tool_approval.py --auto-approve -m "Run the job in configuration 12345"

  # Test with a read-only operation (no approval needed)
  python tool_approval.py -m "List my tables"
""",
    )
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local dev server (http://localhost:3000) instead of production",
    )
    parser.add_argument(
        "--message",
        "-m",
        default="Create a new bucket called 'test-from-kai-client'",
        help="Message to send (should trigger a write operation for approval demo)",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically approve all tool calls instead of prompting",
    )
    args = parser.parse_args()

    token = os.environ.get("STORAGE_API_TOKEN")
    url = os.environ.get("STORAGE_API_URL")

    if not token or not url:
        print("Error: STORAGE_API_TOKEN and STORAGE_API_URL must be set in .env.local")
        return

    print(f"Storage API URL: {url}")
    print(f"Mode: {'AUTO-APPROVE' if args.auto_approve else 'INTERACTIVE'}")

    if args.local:
        print("Server: LOCAL (http://localhost:3000)")
        client = KaiClient(
            storage_api_token=token,
            storage_api_url=url,
            base_url="http://localhost:3000",
        )
    else:
        print("Server: PRODUCTION (auto-discovering...)")
        try:
            # This example demonstrates the legacy v6 / tool-result approval
            # flow (confirm_tool / deny_tool), which only the kai-assistant
            # backend supports — so it pins discovery to that backend instead
            # of the kai-agent default. On kai-agent, use submit_approval from
            # inside the send_message stream (see the README).
            client = await KaiClient.from_storage_api(
                storage_api_token=token,
                storage_api_url=url,
                service=KaiBackend.ASSISTANT,
            )
            print(f"Discovered Kai URL: {client.base_url}")
        except Exception as e:
            print(f"Failed to discover production URL: {e}")
            return

    print("-" * 50)

    async with client:
        if args.auto_approve:
            await run_with_auto_approve(client, args.message)
        else:
            await run_with_interactive_approve(client, args.message)

    print("-" * 50)
    print("Done!")


if __name__ == "__main__":
    asyncio.run(main())

#!/usr/bin/env python3
"""Test script for making a real chat request."""

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

from kai_client import KaiClient  # noqa: E402


async def main():
    parser = argparse.ArgumentParser(description="Test Kai chat client")
    parser.add_argument(
        "--local",
        action="store_true",
        help="Use local dev server (http://localhost:3000) instead of production",
    )
    parser.add_argument(
        "--message",
        "-m",
        default="Hello! What can you help me with?",
        help="Message to send to the chat",
    )
    args = parser.parse_args()

    token = os.environ.get("STORAGE_API_TOKEN")
    url = os.environ.get("STORAGE_API_URL")

    if not token or not url:
        print("Error: STORAGE_API_TOKEN and STORAGE_API_URL must be set in .env.local")
        return

    print(f"Storage API URL: {url}")

    if args.local:
        print("Mode: LOCAL (http://localhost:3000)")
        client = KaiClient(
            storage_api_token=token,
            storage_api_url=url,
            base_url="http://localhost:3000",
        )
    else:
        print("Mode: PRODUCTION (auto-discovering kai-agent URL...)")
        try:
            client = await KaiClient.from_storage_api(
                storage_api_token=token,
                storage_api_url=url,
            )
            print(f"Discovered Kai URL: {client.base_url}")
        except Exception as e:
            print(f"✗ Failed to discover production URL: {e}")
            return

    print("-" * 50)

    async with client:
        # First, test ping
        try:
            ping = await client.ping()
            print(f"✓ Server ping successful: {ping.timestamp}")
        except Exception as e:
            print(f"✗ Ping failed: {e}")
            return

        # Test info
        try:
            info = await client.info()
            print(f"✓ Server info: {info.app_name} v{info.app_version}")
            print(f"  Connected MCP servers: {len(info.connected_mcp)}")
        except Exception as e:
            print(f"✗ Info failed: {e}")

        print("-" * 50)
        print(f"Sending chat message: '{args.message}'")
        print("-" * 50)

        # Start a new chat
        chat_id = client.new_chat_id()
        print(f"Chat ID: {chat_id}")
        print()

        # Send a message and stream the response
        try:
            async for event in client.send_message(
                chat_id,
                args.message,
            ):
                if event.type == "text":
                    print(event.text, end="", flush=True)
                elif event.type == "step-start":
                    print("\n[Step started]", flush=True)
                elif event.type == "tool-call":
                    if event.state == "input-available":
                        print(f"\n[Calling tool: {event.tool_name}]", flush=True)
                    elif event.state == "output-available":
                        print(f"\n[Tool {event.tool_name} completed]", flush=True)
                elif event.type == "finish":
                    print(f"\n\n[Finished: {event.finish_reason}]")
                elif event.type == "error":
                    print(f"\n[Error: {event.message}]")

        except Exception as e:
            print(f"\n✗ Chat failed: {e}")
            if "401" in str(e):
                print("\n" + "=" * 50)
                print("DEBUGGING INFO:")
                print("=" * 50)
                print("The token was validated successfully against Keboola Storage API.")
                print("The 401 error is coming from your local Kai server.")
                print("\nPossible causes:")
                print("1. The local server is not configured to validate tokens")
                print("2. The server needs specific environment variables set")
                print("3. Check the server's console for authentication errors")
                print("=" * 50)
            else:
                raise

        print("-" * 50)
        print("✓ Chat completed successfully!")


if __name__ == "__main__":
    asyncio.run(main())


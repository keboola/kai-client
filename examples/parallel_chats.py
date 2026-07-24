#!/usr/bin/env python3
"""Example: Run multiple Kai chats in parallel."""

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


async def chat_task(client: KaiClient, name: str, message: str) -> str:
    """Run a single chat and return the response."""
    print(f"[{name}] Starting: {message}")
    chat_id, response = await client.chat(message)
    # Truncate response for display
    short_response = response[:200] + "..." if len(response) > 200 else response
    print(f"[{name}] Done ({len(response)} chars)")
    return f"{name}: {short_response}"


async def main():
    token = os.environ.get("STORAGE_API_TOKEN")
    url = os.environ.get("STORAGE_API_URL")

    if not token or not url:
        print("Error: STORAGE_API_TOKEN and STORAGE_API_URL must be set in .env.local")
        return

    print("Discovering kai-agent URL...")
    client = await KaiClient.from_storage_api(
        storage_api_token=token,
        storage_api_url=url,
    )
    print(f"Using: {client.base_url}")
    print("-" * 50)

    async with client:
        # Define multiple questions to ask in parallel
        questions = [
            ("Q1", "How many buckets do I have?"),
            ("Q2", "What is the name of my project?"),
            ("Q3", "How many jobs ran in the last 24 hours?"),
        ]

        print(f"Running {len(questions)} chats in PARALLEL...\n")

        # Run all chats concurrently
        tasks = [
            chat_task(client, name, question) for name, question in questions
        ]
        results = await asyncio.gather(*tasks)

        print("\n" + "=" * 50)
        print("RESULTS:")
        print("=" * 50)
        for result in results:
            print(result)
            print()


if __name__ == "__main__":
    asyncio.run(main())

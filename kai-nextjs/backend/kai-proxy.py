"""
KAI Proxy — FastAPI endpoints for Keboola AI Assistant integration.

Copy this code into your FastAPI main.py. Do NOT modify unless marked // CUSTOMIZE:.

ARCHITECTURE:
  KAI (Keboola AI Assistant) proxy with polling pattern for SSE streaming.
  Backend buffers KAI's SSE stream in memory; frontend polls for buffered events.

CRITICAL IMPLEMENTATION DETAILS:
  1. KAI endpoint URL is {kai_url}/api/chat — append /api/chat to discovered URL
  2. Base URL extraction: KBC_URL may contain /v2/storage — always strip it
  3. SSE parsing: aiter_bytes() + split on b"\\n\\n" — append FULL event string
  4. Use asyncio.create_task() — NOT BackgroundTasks.add_task()
  5. Each stream gets its own httpx.AsyncClient (600s timeout)
  6. Tool approval constructs tool-approval-response message → new KAI stream
"""
import asyncio
import logging
import os
from typing import Optional
from uuid import uuid4

import httpx
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# ─── KAI proxy state ─────────────────────────────────────────────────────────

_kai_url: Optional[str] = None  # Discovered KAI service URL (cached globally)
_streams: dict[str, dict] = {}  # stream_id → {events: list, done: bool, error: str|None}


def _kbc_base_url() -> str:
    """Extract base connection URL from KBC_URL, stripping /v2/storage if present."""
    kbc_url = os.getenv("KBC_URL", "").strip().rstrip("/")
    return kbc_url.split("/v2/")[0] if "/v2/" in kbc_url else kbc_url


async def _discover_kai_url() -> str:
    """Discover KAI URL: GET {base}/v2/storage → find kai-assistant service. Cached globally."""
    global _kai_url
    if _kai_url:
        return _kai_url

    base = _kbc_base_url()
    kbc_token = os.getenv("KBC_TOKEN", "").strip()
    if not base or not kbc_token:
        raise HTTPException(status_code=503, detail="KBC_URL or KBC_TOKEN not configured")

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{base}/v2/storage",
            headers={"x-storageapi-token": kbc_token},
        )
        if resp.status_code != 200:
            raise HTTPException(status_code=502, detail=f"Storage API error: {resp.status_code}")
        services = resp.json().get("services", [])
        for svc in services:
            if svc.get("id") == "kai-assistant":
                discovered = svc["url"].rstrip("/")
                _kai_url = discovered
                logger.info("Discovered KAI URL: %s", discovered)
                return discovered

    raise HTTPException(status_code=503, detail="KAI assistant service not found in this project")


def _kai_auth_headers() -> dict[str, str]:
    """Build auth headers for KAI requests. KAI_TOKEN falls back to KBC_TOKEN."""
    base = _kbc_base_url()
    kai_token = os.getenv("KAI_TOKEN", "").strip() or os.getenv("KBC_TOKEN", "").strip()
    return {
        "x-storageapi-token": kai_token,
        "x-storageapi-url": base,
        "Content-Type": "application/json",
    }


async def _kai_stream_consumer(stream_id: str, resp: httpx.Response, client: httpx.AsyncClient) -> None:
    """Consume raw SSE bytes from KAI, split on \\n\\n, buffer full event strings.

    Uses aiter_bytes() — NOT aiter_lines() — because SSE events are delimited
    by double newlines. Each buffered entry is the full event text including
    data: prefix lines, which the frontend parses.
    """
    buffer = _streams[stream_id]
    try:
        raw = b""
        async for chunk in resp.aiter_bytes():
            raw += chunk
            # SSE events are separated by \n\n
            while b"\n\n" in raw:
                event_bytes, raw = raw.split(b"\n\n", 1)
                event_str = event_bytes.decode("utf-8", errors="replace").strip()
                if event_str:
                    buffer["events"].append(event_str)
        # Handle any trailing data
        if raw.strip():
            buffer["events"].append(raw.decode("utf-8", errors="replace").strip())
        buffer["done"] = True
    except Exception as exc:
        logger.exception("KAI stream error for %s", stream_id)
        buffer["error"] = str(exc)
        buffer["done"] = True
    finally:
        await resp.aclose()
        await client.aclose()


async def _start_kai_stream(kai_url: str, headers: dict, body: dict) -> str:
    """Open streaming POST to {kai_url}/api/chat, spawn consumer task, return stream_id."""
    stream_id = str(uuid4())
    _streams[stream_id] = {"events": [], "done": False, "error": None}

    # Each stream gets a dedicated client (600s timeout for long KAI responses)
    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=30.0))
    try:
        resp = await client.send(
            client.build_request("POST", f"{kai_url}/api/chat", headers=headers, json=body),
            stream=True,
        )
        if resp.status_code != 200:
            error_body = await resp.aread()
            await resp.aclose()
            await client.aclose()
            _streams[stream_id]["error"] = f"KAI returned {resp.status_code}: {error_body.decode()[:200]}"
            _streams[stream_id]["done"] = True
            return stream_id

        # Spawn consumer as asyncio task — NOT BackgroundTasks.add_task()
        asyncio.create_task(_kai_stream_consumer(stream_id, resp, client))
    except Exception as exc:
        await client.aclose()
        _streams[stream_id]["error"] = str(exc)
        _streams[stream_id]["done"] = True
        logger.exception("Failed to start KAI stream")

    return stream_id


# ─── KAI proxy endpoints (register on your FastAPI app) ─────────────────────
# Add these to your main.py:
#
#   from kai_proxy import (
#       _discover_kai_url, _kai_auth_headers, _start_kai_stream,
#       _streams, chat_start, chat_poll, chat_approval,
#   )
#
# Or copy the endpoint functions directly into main.py.


async def chat_start(request: Request):
    """POST /api/chat — Initiate a KAI chat stream. Returns a stream_id for polling."""
    payload = await request.json()
    kai_url = await _discover_kai_url()
    headers = _kai_auth_headers()
    stream_id = await _start_kai_stream(kai_url, headers, payload)
    return {"stream_id": stream_id}


async def chat_poll(stream_id: str, cursor: int = 0):
    """GET /api/chat/{stream_id}/poll — Poll for buffered SSE events starting at cursor."""
    buffer = _streams.get(stream_id)
    if buffer is None:
        raise HTTPException(status_code=404, detail=f"Stream {stream_id!r} not found")

    events = buffer["events"][cursor:]
    new_cursor = cursor + len(events)
    done = buffer["done"]
    error = buffer["error"]

    # Clean up completed streams after all events are consumed
    if done and new_cursor >= len(buffer["events"]):
        _streams.pop(stream_id, None)

    return {
        "events": events,
        "cursor": new_cursor,
        "done": done,
        "error": error,
    }


async def chat_approval(chat_id: str, action: str, approval_id: str, request: Request):
    """POST /api/chat/{chat_id}/{action}/{approval_id} — Tool approval/rejection."""
    payload = await request.json()
    approved = payload.get("approved", True)

    # Build the tool-approval-response message per KAI protocol
    approval_message = {
        "id": chat_id,
        "message": {
            "id": str(uuid4()),
            "role": "user",
            "parts": [
                {
                    "type": "tool-approval-response",
                    "approvalId": approval_id,
                    "approved": approved,
                    **({"reason": payload["reason"]} if not approved and "reason" in payload else {}),
                }
            ],
        },
        "selectedChatModel": "chat-model",
        "selectedVisibilityType": "private",
    }

    kai_url = await _discover_kai_url()
    headers = _kai_auth_headers()
    stream_id = await _start_kai_stream(kai_url, headers, approval_message)
    return {"stream_id": stream_id}

#!/usr/bin/env python3
"""Test tool confirmation/approval flows against the live Kai API."""

import asyncio
import os
import sys
import time
import traceback
from pathlib import Path

# Load .env.local manually
env_file = Path(__file__).parent.parent / ".env.local"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ[key.strip()] = value.strip()

from kai_client import KaiBackend, KaiClient  # noqa: E402
from kai_client.models import ToolCallEvent  # noqa: E402


class TestResult:
    def __init__(self, name: str, passed: bool, duration: float, details: str = ""):
        self.name = name
        self.passed = passed
        self.duration = duration
        self.details = details


results: list[TestResult] = []


def record(name: str, passed: bool, duration: float, details: str = ""):
    results.append(TestResult(name, passed, duration, details))
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name} ({duration:.1f}s)")
    if details:
        for line in details.splitlines()[:5]:
            print(f"         {line}")


async def stream_and_collect(client, chat_id, message):
    """
    Stream a message and collect all events. Track which tools reached
    input-available without a subsequent output-available (i.e., need approval).
    """
    text_parts = []
    all_events = []
    tool_states = {}  # tool_call_id -> last ToolCallEvent

    async for event in client.send_message(chat_id, message):
        all_events.append(event)
        if event.type == "text":
            text_parts.append(event.text)
        elif event.type == "tool-call" and isinstance(event, ToolCallEvent):
            tool_states[event.tool_call_id] = event

    # Find tools that need approval:
    # - Reached "input-available" but NOT "output-available"
    pending_tools = []
    for tool_call_id, last_event in tool_states.items():
        if last_event.state == "input-available":
            pending_tools.append(last_event)

    return text_parts, all_events, tool_states, pending_tools


async def main():
    token = os.environ.get("STORAGE_API_TOKEN")
    url = os.environ.get("STORAGE_API_URL")

    if not token or not url:
        print("Error: STORAGE_API_TOKEN and STORAGE_API_URL must be set")
        sys.exit(1)

    print("=" * 70)
    print("KaiClient Tool Confirmation/Approval Test")
    print("=" * 70)
    print(f"Storage API URL: {url}")
    print()

    # This script exercises the v6 (approve_tool / reject_tool) and legacy
    # (confirm_tool / deny_tool) approval flows, which are only supported by the
    # kai-assistant backend — hence the explicit service pin instead of the
    # kai-agent default. kai-agent approvals go through submit_approval.
    client = await KaiClient.from_storage_api(
        storage_api_token=token,
        storage_api_url=url,
        service=KaiBackend.ASSISTANT,
    )
    print(f"Kai URL: {client.base_url}")
    print()

    async with client:

        # =================================================================
        # TEST 1: Trigger write tool and detect it needs approval
        # =================================================================
        print("[1/5] Trigger write operation and detect pending approval")
        print("      Asking Kai to update a bucket description (write tool)")
        t0 = time.time()
        chat_id_1 = client.new_chat_id()
        try:
            text_parts, all_events, tool_states, pending_tools = (
                await stream_and_collect(
                    client,
                    chat_id_1,
                    "Update the description of the first bucket you find. "
                    "Add '[KaiClient approval test]' to the description. "
                    "Just call the tools, don't ask me.",
                )
            )
            dur = time.time() - t0

            event_types = {e.type for e in all_events}
            all_tool_info = [
                (e.tool_name, e.state)
                for e in all_events
                if isinstance(e, ToolCallEvent)
            ]

            has_pending = len(pending_tools) > 0
            details = (
                f"Event types: {event_types}\n"
                f"All tool transitions: {all_tool_info}\n"
                f"Pending tools (need approval): "
                f"{[(t.tool_name, t.tool_call_id[:12]) for t in pending_tools]}\n"
                f"Text: {''.join(text_parts)[:100]}"
            )
            record("Detect Pending Approval", has_pending, dur, details)

        except Exception:
            dur = time.time() - t0
            record("Detect Pending Approval", False, dur, traceback.format_exc())
            pending_tools = []

        # =================================================================
        # TEST 2: Deny/reject the pending tool
        # =================================================================
        print("\n[2/5] Deny the pending tool call")
        t0 = time.time()
        if pending_tools:
            pending = pending_tools[-1]  # Last pending tool
            try:
                # Determine which flow to use
                has_v6_approval = (
                    pending.approval is not None
                    and hasattr(pending.approval, "id")
                    and pending.approval.id
                )

                deny_text = []
                deny_events = []

                if has_v6_approval:
                    print(
                        f"      Using v6 flow: reject_tool("
                        f"approval_id={pending.approval.id[:12]}...)"
                    )
                    async for event in client.reject_tool(
                        chat_id=chat_id_1,
                        approval_id=pending.approval.id,
                        reason="Testing rejection - do not modify",
                    ):
                        deny_events.append(event)
                        if event.type == "text":
                            deny_text.append(event.text)
                else:
                    print(
                        f"      Using legacy flow: deny_tool("
                        f"tool_call_id={pending.tool_call_id[:12]}...)"
                    )
                    async for event in client.deny_tool(
                        chat_id=chat_id_1,
                        tool_call_id=pending.tool_call_id,
                        tool_name=pending.tool_name or "unknown",
                    ):
                        deny_events.append(event)
                        if event.type == "text":
                            deny_text.append(event.text)

                dur = time.time() - t0
                deny_response = "".join(deny_text)
                deny_event_types = {e.type for e in deny_events}
                flow_type = "v6" if has_v6_approval else "legacy"
                passed = len(deny_events) > 0
                record(
                    f"Deny Tool ({flow_type} flow)",
                    passed,
                    dur,
                    f"Flow: {flow_type}\n"
                    f"Events after denial: {deny_event_types}\n"
                    f"Response: {deny_response[:150]}",
                )
            except Exception:
                dur = time.time() - t0
                record("Deny Tool", False, dur, traceback.format_exc())
        else:
            dur = time.time() - t0
            record(
                "Deny Tool",
                False,
                dur,
                "Skipped: No pending tool from previous test",
            )

        # =================================================================
        # TEST 3: Trigger and APPROVE a write tool (confirm_tool)
        # =================================================================
        print("\n[3/5] Trigger and approve a write tool")
        print("      Asking Kai to update a bucket description (will approve)")
        t0 = time.time()
        chat_id_2 = client.new_chat_id()
        try:
            text_parts_2, all_events_2, tool_states_2, pending_tools_2 = (
                await stream_and_collect(
                    client,
                    chat_id_2,
                    "Update the description of the first bucket you find. "
                    "Add '[KaiClient test - safe to remove]' at the end. "
                    "Call the tools now.",
                )
            )

            if not pending_tools_2:
                dur = time.time() - t0
                all_tool_info_2 = [
                    (e.tool_name, e.state)
                    for e in all_events_2
                    if isinstance(e, ToolCallEvent)
                ]
                record(
                    "Approve Tool",
                    False,
                    dur,
                    f"No pending tools found.\n"
                    f"Tool transitions: {all_tool_info_2}\n"
                    f"Text: {''.join(text_parts_2)[:150]}",
                )
            else:
                pending = pending_tools_2[-1]
                has_v6_approval = (
                    pending.approval is not None
                    and hasattr(pending.approval, "id")
                    and pending.approval.id
                )

                approve_text = []
                approve_events = []

                if has_v6_approval:
                    print(
                        f"      Using v6 flow: approve_tool("
                        f"approval_id={pending.approval.id[:12]}...)"
                    )
                    async for event in client.approve_tool(
                        chat_id=chat_id_2,
                        approval_id=pending.approval.id,
                        reason="Approved for testing",
                    ):
                        approve_events.append(event)
                        if event.type == "text":
                            approve_text.append(event.text)
                else:
                    print(
                        f"      Using legacy flow: confirm_tool("
                        f"tool_call_id={pending.tool_call_id[:12]}...)"
                    )
                    async for event in client.confirm_tool(
                        chat_id=chat_id_2,
                        tool_call_id=pending.tool_call_id,
                        tool_name=pending.tool_name or "unknown",
                    ):
                        approve_events.append(event)
                        if event.type == "text":
                            approve_text.append(event.text)

                dur = time.time() - t0
                approve_response = "".join(approve_text)
                approve_event_types = {e.type for e in approve_events}
                approve_tool_states = [
                    (e.tool_name, e.state)
                    for e in approve_events
                    if isinstance(e, ToolCallEvent)
                ]
                flow_type = "v6" if has_v6_approval else "legacy"
                # After approval, we expect tool output and/or text continuation
                passed = len(approve_events) > 0
                record(
                    f"Approve Tool ({flow_type} flow)",
                    passed,
                    dur,
                    f"Flow: {flow_type}\n"
                    f"Events after approval: {approve_event_types}\n"
                    f"Tool states after: {approve_tool_states}\n"
                    f"Response: {approve_response[:150]}",
                )

        except Exception:
            dur = time.time() - t0
            record("Approve Tool", False, dur, traceback.format_exc())

        # =================================================================
        # TEST 4: Verify approved tool completed via get_chat
        # =================================================================
        print("\n[4/5] Verify approved tool execution via get_chat")
        t0 = time.time()
        try:
            chat_detail = await client.get_chat(chat_id_2)
            dur = time.time() - t0
            msg_count = len(chat_detail.messages) if chat_detail.messages else 0

            # Look for tool results in messages
            tool_parts_found = []
            for msg in chat_detail.messages:
                for part in msg.parts:
                    part_type = part.get("type", "") if isinstance(part, dict) else ""
                    if "tool" in part_type:
                        tool_parts_found.append(part_type)

            passed = msg_count >= 2 and len(tool_parts_found) > 0
            record(
                "Verify Tool Execution (get_chat)",
                passed,
                dur,
                f"Messages: {msg_count}, Tool parts found: {tool_parts_found}",
            )
        except Exception:
            dur = time.time() - t0
            record("Verify Tool Execution (get_chat)", False, dur, traceback.format_exc())

        # =================================================================
        # TEST 5: Multi-step tool flow (read then write)
        # =================================================================
        print("\n[5/5] Multi-step tool flow with approval in the middle")
        print("      Asking Kai to list buckets then update one (read + write)")
        t0 = time.time()
        chat_id_3 = client.new_chat_id()
        try:
            text_parts_3, all_events_3, tool_states_3, pending_tools_3 = (
                await stream_and_collect(
                    client,
                    chat_id_3,
                    "First list all my buckets, then update the description "
                    "of the last bucket to include '[multi-step test]'. "
                    "Do both steps now.",
                )
            )

            all_tool_info_3 = [
                (e.tool_name, e.state)
                for e in all_events_3
                if isinstance(e, ToolCallEvent)
            ]

            # We expect: get_buckets (auto-approved) -> update_descriptions (needs approval)
            tool_names_seen = set()
            for e in all_events_3:
                if isinstance(e, ToolCallEvent) and e.tool_name:
                    tool_names_seen.add(e.tool_name)

            has_read_tool = any(
                name for name in tool_names_seen
                if name in ("get_buckets", "get_tables", "list_buckets")
            )
            has_pending_write = len(pending_tools_3) > 0

            # If there's a pending write tool, deny it (cleanup)
            denied_ok = False
            if pending_tools_3:
                pending = pending_tools_3[-1]
                has_v6 = (
                    pending.approval is not None
                    and hasattr(pending.approval, "id")
                    and pending.approval.id
                )
                try:
                    if has_v6:
                        async for _ in client.reject_tool(
                            chat_id=chat_id_3,
                            approval_id=pending.approval.id,
                        ):
                            pass
                    else:
                        async for _ in client.deny_tool(
                            chat_id=chat_id_3,
                            tool_call_id=pending.tool_call_id,
                            tool_name=pending.tool_name or "unknown",
                        ):
                            pass
                    denied_ok = True
                except Exception:
                    pass

            dur = time.time() - t0
            passed = has_read_tool and (has_pending_write or len(tool_names_seen) >= 2)
            record(
                "Multi-Step Tool Flow",
                passed,
                dur,
                f"Tools seen: {tool_names_seen}\n"
                f"All transitions: {all_tool_info_3}\n"
                f"Read tool present: {has_read_tool}\n"
                f"Write tool pending: {has_pending_write}, denied: {denied_ok}",
            )

        except Exception as e:
            dur = time.time() - t0
            record("Multi-Step Tool Flow", False, dur, traceback.format_exc())

        # Clean up test chats
        print("\n[Cleanup] Deleting test chats...")
        for cid in [chat_id_1, chat_id_2, chat_id_3]:
            try:
                await client.delete_chat(cid)
                print(f"         Deleted {cid[:8]}...")
            except Exception:
                pass

    # =========================================================================
    # Summary
    # =========================================================================
    print("\n" + "=" * 70)
    print("TOOL CONFIRMATION TEST SUMMARY")
    print("=" * 70)
    passed_count = sum(1 for r in results if r.passed)
    total_count = len(results)
    total_time = sum(r.duration for r in results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name} ({r.duration:.1f}s)")

    print(f"\n  {passed_count}/{total_count} tests passed in {total_time:.1f}s total")

    if passed_count < total_count:
        print("\n  Failed tests:")
        for r in results:
            if not r.passed:
                print(f"    - {r.name}: {r.details[:200]}")

    print("=" * 70)
    return 0 if passed_count == total_count else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)

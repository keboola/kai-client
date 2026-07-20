# Design: kai-agent backend support in kai-client

**Date:** 2026-07-20
**Status:** Approved
**Version target:** 0.12.0 → 0.13.0 (breaking default change)

## Problem

Keboola exposes two backend services in the Storage API `/v2/storage` `services`
array:

- `kai-agent` — the modern "agent" backend.
- `kai-assistant` — the legacy backend (single-tenant customers only; slated for
  deprecation and removal).

`KaiClient.from_storage_api()` hardcodes discovery of the service whose
`id == "kai-assistant"` (the `next(...)` at `client.py:141`). So it always
connects to the legacy backend. Newer agent-only features (e.g. tool
restrictions) are then silently dropped: the kai-assistant route's schema strips
unknown keys and returns 200, so the feature never reaches the agent/MCP layer.

The library is already agent-first internally: `submit_approval` is the live
approval method, and the Vercel-AI-SDK-v6 flow methods carry `.. deprecated::`
docstrings stating they are "not supported by the kai-agent backend."

## Goal

Make the kai-agent backend fully supported and the default discovery target,
while keeping the legacy backend selectable but de-emphasized.

## Decisions (approved)

1. **Default backend:** `from_storage_api()` discovers `kai-agent` by default.
   This is a breaking change, accepted because the library is already
   agent-first and the project is pre-1.0. Ship with a version bump to 0.13.0
   and a changelog note.
2. **API shape:** a `service=` parameter backed by a new `KaiBackend` enum. One
   factory, one code path, generalized service-id lookup.
3. **Audit (item 3):** documentation-only. The v6/legacy methods are already
   docstring-deprecated; no runtime guard (avoids tripping CI warning filters
   and breaking existing tests exercising those methods).
4. **kai-assistant is legacy:** keep it selectable but de-emphasized in docs and
   examples; do not add new examples that lead with it.

## Design

### 1. `KaiBackend` enum (`src/kai_client/types.py`)

A string enum whose values are the exact Storage API service ids, so the enum
value doubles as the discovery lookup key:

```python
class KaiBackend(str, Enum):
    """Selectable Keboola AI backend services (Storage API service ids)."""

    AGENT = "kai-agent"          # modern agent backend (default)
    ASSISTANT = "kai-assistant"  # legacy backend (single-tenant; being retired)
```

Exported from `kai_client/__init__.py` (`from kai_client.types import ...` block
and `__all__` "Enums" section).

### 2. `from_storage_api(...)` (`src/kai_client/client.py`)

Signature gains a `service` parameter:

```python
@classmethod
async def from_storage_api(
    cls,
    storage_api_token: str,
    storage_api_url: str,
    *,
    service: KaiBackend | str = KaiBackend.AGENT,
    timeout: float = 300.0,
    stream_timeout: float = 600.0,
) -> "KaiClient":
```

- `service` accepts either a `KaiBackend` or a raw service-id string (forward-
  compat with future services). Resolve to the lookup id via
  `service.value if isinstance(service, KaiBackend) else service`.
- Replace the hardcoded lookup:

  ```python
  service_id = service.value if isinstance(service, KaiBackend) else service
  kai_service = next(
      (s for s in services if s.get("id") == service_id),
      None,
  )
  if not kai_service:
      available = [s.get("id") for s in services]
      raise KaiError(
          message=f"{service_id} service not found. Available services: {available}",
          code="discovery:service_not_found",
      )
  ```

- The "no URL" error message uses `service_id` too. Error codes are unchanged
  (`discovery:http_error`, `discovery:service_not_found`, `discovery:no_url`).
- Pass the resolved backend to the constructor so the instance records what it
  connected to.

> **Note on `*`:** `service` is keyword-only. `timeout`/`stream_timeout` were
> previously positional-or-keyword. Making them keyword-only alongside `service`
> is acceptable in the same breaking 0.13.0 release; existing callers in this
> repo and the README pass them by keyword. This keeps the signature clean and
> avoids an awkward positional `service` slot.

### 3. `__init__` records the backend

Add an optional `backend` parameter to `__init__` (default `None`) stored as
`self.backend: KaiBackend | None`. `from_storage_api` normalizes the resolved
`service_id` to a `KaiBackend` when it maps to a known member (via
`KaiBackend(service_id)` inside a `try/except ValueError`), otherwise `None`.
So both `service=KaiBackend.AGENT` and `service="kai-agent"` record
`KaiBackend.AGENT`, while an unrecognized future id records `None`. Direct
construction (local dev) leaves it `None` because the backend behind an
arbitrary `base_url` is unknown.

This is introspection-only; no method behavior branches on it (per the
documentation-only audit decision).

### 4. CLI (`src/kai_client/cli.py`)

Add a group-level option:

```python
@click.option(
    "--service",
    type=click.Choice(["agent", "assistant"]),
    default="agent",
    envvar="KAI_SERVICE",
    help="Which Kai backend to auto-discover (default: agent). Ignored with --base-url.",
)
```

- Store `ctx.obj["service"]` and thread it into `get_client`, mapping
  `"agent" → KaiBackend.AGENT`, `"assistant" → KaiBackend.ASSISTANT`.
- `--base-url` still wins and bypasses discovery entirely (backend stays
  unknown / `None`).

### 5. Endpoint support matrix (docs)

Document, in `README.md` and `plugins/kai-cli/skills/kai-cli/references/api-details.md`,
which methods are valid against kai-agent:

**Agent-valid:** `ping`, `info`, `send_message`, `chat`, `submit_approval`,
`get_chat`, `delete_chat`, `get_history` / `get_all_history`, `get_votes` /
`vote` / `upvote` / `downvote`, `get_usage`, `get_settings` / `update_settings` /
`get_user_settings` / `update_user_settings`, `get_tools`, `get_suggestions`.

**Not supported on kai-agent (already `.. deprecated::`):**
`send_tool_approval_response`, `approve_tool`, `reject_tool`, `send_tool_result`,
`confirm_tool`, `deny_tool`, `resume_stream`.

### 6. Docs + version

- `README.md`: update the auto-discovery examples (~line 44, ~184–195,
  ~402–410) to show agent-as-default and the `service=` param; add the support
  matrix; de-emphasize kai-assistant (mention it only as the legacy opt-in).
- `api-details.md`: same, in the Client Configuration section.
- Bump `__version__` in `src/kai_client/__init__.py` and `version` in
  `pyproject.toml` to `0.13.0`; add a changelog note describing the breaking
  default change and how to restore old behavior (`service=KaiBackend.ASSISTANT`).

## Testing

Mirror `TestFromStorageApi` (`tests/test_client.py:757`):

- Agent discovery success by default (services list contains both; asserts the
  agent URL is chosen and `client.backend == KaiBackend.AGENT`).
- Explicit `service=KaiBackend.ASSISTANT` selects the assistant URL and records
  `client.backend == KaiBackend.ASSISTANT`.
- Raw-string service id (`service="kai-agent"`) resolves correctly.
- Service-not-found error names the *requested* service and lists available ids;
  code `discovery:service_not_found`.
- Existing not-found/no-url/http-error/custom-timeout tests updated to the new
  default (they currently assume kai-assistant).
- Direct `__init__` leaves `backend is None`.

CLI (`tests/test_cli.py`, mirroring the `from_storage_api` patch at line ~804):

- `--service assistant` (and `KAI_SERVICE=assistant`) passes
  `service=KaiBackend.ASSISTANT` to `from_storage_api`.
- Default invocation passes `service=KaiBackend.AGENT`.

Keep `uv run pytest -v` and `uv run ruff check .` green on Python 3.10/3.11/3.12.

## Manual verification

Using the real us-east4 token in `~/Keboola/KaiClient/.env.local` (never
printed): confirm `from_storage_api(service=KaiBackend.AGENT)` resolves the
`kai-agent.us-east4.gcp.keboola.com` URL and a `send_message` round-trips.

## Out of scope

- `tool_restrictions` / `ToolRestrictions` (PR #46, separate branch) — this work
  must not depend on it.
- Removing kai-assistant support or its deprecated v6 methods.
- Any runtime guard/warning on deprecated methods.

# kai-agent Backend Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `KaiClient.from_storage_api()` discover and default to the modern `kai-agent` backend, with the legacy `kai-assistant` backend still selectable.

**Architecture:** Introduce a `KaiBackend` string enum whose values are the Storage API service ids. `from_storage_api()` gains a keyword-only `service` parameter (default `KaiBackend.AGENT`) that generalizes the previously hardcoded `kai-assistant` lookup. The client records the resolved backend on `self.backend`. The CLI exposes a `--service` choice. Deprecated v6/legacy methods stay as-is and are documented as agent-unsupported.

**Tech Stack:** Python 3.10+, httpx, pydantic v2, click, pytest (`asyncio_mode = auto`), pytest-httpx, ruff, uv.

## Global Constraints

- Python floor: 3.10 (`ruff target-version = py310`); CI runs on 3.10/3.11/3.12.
- CI gates: `uv run pytest -v` and `uv run ruff check .` must stay green. mypy/pyright are NOT in CI (pre-existing snake_case-kwarg noise is out of scope).
- `service` accepts `KaiBackend | str`; resolve the lookup id as `service.value if isinstance(service, KaiBackend) else service`.
- `KaiBackend` values are exact service ids: `AGENT = "kai-agent"`, `ASSISTANT = "kai-assistant"`.
- Discovery error codes are unchanged: `discovery:http_error`, `discovery:service_not_found`, `discovery:no_url`.
- kai-assistant is legacy (single-tenant, being retired) — keep it selectable but de-emphasized in docs; no new examples leading with it.
- Do NOT depend on `tool_restrictions`/`ToolRestrictions` (separate branch/PR #46).
- Version bumps to `0.13.0` in both `pyproject.toml` and `src/kai_client/__init__.py`.
- Commit after each task.

---

### Task 1: `KaiBackend` enum

**Files:**
- Modify: `src/kai_client/types.py` (append new enum after `VoteType`, ~line 17)
- Modify: `src/kai_client/__init__.py` (import block ~line 78-85; `__all__` "Enums" section ~line 147-153)
- Test: `tests/test_types.py` (create if absent; otherwise append)

**Interfaces:**
- Consumes: nothing.
- Produces: `KaiBackend(str, Enum)` with members `AGENT` (value `"kai-agent"`) and `ASSISTANT` (value `"kai-assistant"`); importable as `from kai_client import KaiBackend`.

- [ ] **Step 1: Write the failing test**

Create/append `tests/test_types.py`:

```python
from kai_client import KaiBackend
from kai_client.types import KaiBackend as KaiBackendFromTypes


def test_kai_backend_values_match_service_ids():
    assert KaiBackend.AGENT.value == "kai-agent"
    assert KaiBackend.ASSISTANT.value == "kai-assistant"


def test_kai_backend_is_str_enum():
    # str-enum so the member can be used directly as a lookup id
    assert KaiBackend.AGENT == "kai-agent"
    assert KaiBackend("kai-agent") is KaiBackend.AGENT


def test_kai_backend_exported_from_package_root():
    assert KaiBackendFromTypes is KaiBackend
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_types.py -v`
Expected: FAIL with `ImportError: cannot import name 'KaiBackend'`.

- [ ] **Step 3: Add the enum in `types.py`**

Insert after the `VoteType` class (after line 17):

```python
class KaiBackend(str, Enum):
    """Selectable Keboola AI backend services (Storage API service ids)."""

    AGENT = "kai-agent"          # modern agent backend (default)
    ASSISTANT = "kai-assistant"  # legacy backend (single-tenant; being retired)
```

- [ ] **Step 4: Export from `__init__.py`**

In the `from kai_client.types import (` block, add `KaiBackend,` (keep alphabetical: before `MessageRole`):

```python
from kai_client.types import (
    FinishReason,
    KaiBackend,
    MessageRole,
    SSEEventType,
    ToolCallState,
    VisibilityType,
    VoteType,
)
```

In `__all__`, under the `# Enums` comment, add `"KaiBackend",` (place it first in that group):

```python
    # Enums
    "KaiBackend",
    "VisibilityType",
    "VoteType",
    "MessageRole",
    "SSEEventType",
    "FinishReason",
    "ToolCallState",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_types.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/kai_client/types.py src/kai_client/__init__.py tests/test_types.py
git commit -m "feat: add KaiBackend enum for backend selection"
```

---

### Task 2: `from_storage_api` service parameter + generalized lookup + `self.backend`

**Files:**
- Modify: `src/kai_client/client.py` (`from_storage_api` ~lines 86-166; `__init__` ~lines 168-191; class docstring ~line 76)
- Test: `tests/test_client.py` (`TestFromStorageApi` class, ~lines 757-863)

**Interfaces:**
- Consumes: `KaiBackend` from Task 1.
- Produces:
  - `KaiClient.from_storage_api(storage_api_token, storage_api_url, *, service: KaiBackend | str = KaiBackend.AGENT, timeout=300.0, stream_timeout=600.0) -> KaiClient`
  - `KaiClient.__init__(..., base_url="http://localhost:3000", timeout=300.0, stream_timeout=600.0, backend: KaiBackend | None = None)`
  - Instance attribute `self.backend: KaiBackend | None`.

- [ ] **Step 1: Rewrite the discovery tests (failing)**

Replace the body of `TestFromStorageApi` in `tests/test_client.py` (lines ~757-863) with tests reflecting the agent default. Ensure `KaiBackend` is imported at the top of the file (add `from kai_client import KaiBackend` near the existing imports if not present):

```python
class TestFromStorageApi:
    """Tests for from_storage_api factory method."""

    @pytest.mark.asyncio
    async def test_defaults_to_agent(self, httpx_mock: HTTPXMock):
        """Default discovery targets the kai-agent service."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            json={
                "services": [
                    {"id": "kai-assistant", "url": "https://assistant.keboola.com"},
                    {"id": "kai-agent", "url": "https://agent.keboola.com"},
                ]
            },
        )

        client = await KaiClient.from_storage_api(
            storage_api_token="test-token",
            storage_api_url="https://connection.keboola.com",
        )

        assert client.base_url == "https://agent.keboola.com"
        assert client.backend == KaiBackend.AGENT
        await client.close()

    @pytest.mark.asyncio
    async def test_explicit_assistant(self, httpx_mock: HTTPXMock):
        """service=KaiBackend.ASSISTANT selects the legacy service."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            json={
                "services": [
                    {"id": "kai-assistant", "url": "https://assistant.keboola.com"},
                    {"id": "kai-agent", "url": "https://agent.keboola.com"},
                ]
            },
        )

        client = await KaiClient.from_storage_api(
            storage_api_token="test-token",
            storage_api_url="https://connection.keboola.com",
            service=KaiBackend.ASSISTANT,
        )

        assert client.base_url == "https://assistant.keboola.com"
        assert client.backend == KaiBackend.ASSISTANT
        await client.close()

    @pytest.mark.asyncio
    async def test_raw_string_service(self, httpx_mock: HTTPXMock):
        """A raw service-id string resolves and normalizes to the enum."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            json={"services": [{"id": "kai-agent", "url": "https://agent.keboola.com"}]},
        )

        client = await KaiClient.from_storage_api(
            storage_api_token="test-token",
            storage_api_url="https://connection.keboola.com",
            service="kai-agent",
        )

        assert client.base_url == "https://agent.keboola.com"
        assert client.backend == KaiBackend.AGENT
        await client.close()

    @pytest.mark.asyncio
    async def test_unknown_service_id_leaves_backend_none(self, httpx_mock: HTTPXMock):
        """A service id with no matching KaiBackend member records backend=None."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            json={"services": [{"id": "kai-future", "url": "https://future.keboola.com"}]},
        )

        client = await KaiClient.from_storage_api(
            storage_api_token="test-token",
            storage_api_url="https://connection.keboola.com",
            service="kai-future",
        )

        assert client.base_url == "https://future.keboola.com"
        assert client.backend is None
        await client.close()

    @pytest.mark.asyncio
    async def test_service_not_found(self, httpx_mock: HTTPXMock):
        """Error names the requested service and lists available ids."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            json={"services": [{"id": "kai-assistant", "url": "https://assistant.keboola.com"}]},
        )

        with pytest.raises(KaiError) as exc_info:
            await KaiClient.from_storage_api(
                storage_api_token="test-token",
                storage_api_url="https://connection.keboola.com",
            )

        assert "kai-agent service not found" in str(exc_info.value)
        assert "kai-assistant" in str(exc_info.value)
        assert exc_info.value.code == "discovery:service_not_found"

    @pytest.mark.asyncio
    async def test_no_url(self, httpx_mock: HTTPXMock):
        """Error when the discovered service has no URL."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            json={"services": [{"id": "kai-agent"}]},  # no URL
        )

        with pytest.raises(KaiError) as exc_info:
            await KaiClient.from_storage_api(
                storage_api_token="test-token",
                storage_api_url="https://connection.keboola.com",
            )

        assert "no URL" in str(exc_info.value)
        assert exc_info.value.code == "discovery:no_url"

    @pytest.mark.asyncio
    async def test_http_error(self, httpx_mock: HTTPXMock):
        """Error when Storage API returns HTTP error."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            status_code=401,
            json={"message": "Unauthorized"},
        )

        with pytest.raises(KaiError) as exc_info:
            await KaiClient.from_storage_api(
                storage_api_token="bad-token",
                storage_api_url="https://connection.keboola.com",
            )

        assert "HTTP 401" in str(exc_info.value)
        assert exc_info.value.code == "discovery:http_error"

    @pytest.mark.asyncio
    async def test_custom_timeouts(self, httpx_mock: HTTPXMock):
        """Custom timeouts are passed to the client."""
        httpx_mock.add_response(
            url="https://connection.keboola.com/v2/storage",
            json={"services": [{"id": "kai-agent", "url": "https://agent.keboola.com"}]},
        )

        client = await KaiClient.from_storage_api(
            storage_api_token="test-token",
            storage_api_url="https://connection.keboola.com",
            timeout=60.0,
            stream_timeout=120.0,
        )

        assert client.timeout == 60.0
        assert client.stream_timeout == 120.0
        await client.close()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_client.py::TestFromStorageApi -v`
Expected: FAIL — default now expects `kai-agent` (current code finds `kai-assistant`), and `client.backend` / `service=` don't exist yet.

- [ ] **Step 3: Add `KaiBackend` import in `client.py`**

In the `from kai_client.types import (...)` block near the top of `client.py` (currently `from kai_client.types import VisibilityType, VoteType`), add `KaiBackend`:

```python
from kai_client.types import KaiBackend, VisibilityType, VoteType
```

- [ ] **Step 4: Rewrite `from_storage_api` signature and lookup**

Change the signature (add keyword-only `service`):

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

Replace the hardcoded lookup block (current lines ~140-158) with:

```python
        services = data.get("services", [])
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

        kai_url = kai_service.get("url")
        if not kai_url:
            raise KaiError(
                message=f"{service_id} service has no URL",
                code="discovery:no_url",
            )

        try:
            backend: KaiBackend | None = KaiBackend(service_id)
        except ValueError:
            backend = None

        return cls(
            storage_api_token=storage_api_token,
            storage_api_url=storage_api_url,
            base_url=kai_url,
            timeout=timeout,
            stream_timeout=stream_timeout,
            backend=backend,
        )
```

Also update the `from_storage_api` docstring: change the summary from
"Auto-discover the kai-assistant URL" to "Auto-discover the Kai backend URL
(defaults to kai-agent)", and document the `service` arg:

```
            service: Which backend to discover. Defaults to KaiBackend.AGENT
                (the modern agent backend). Pass KaiBackend.ASSISTANT for the
                legacy backend, or a raw service-id string.
```

- [ ] **Step 5: Add `backend` to `__init__`**

Change the `__init__` signature to accept `backend` and store it:

```python
    def __init__(
        self,
        storage_api_token: str,
        storage_api_url: str,
        base_url: str = "http://localhost:3000",
        timeout: float = 300.0,
        stream_timeout: float = 600.0,
        backend: KaiBackend | None = None,
    ) -> None:
```

In the body, after `self.stream_timeout = stream_timeout` add:

```python
        self.backend = backend
```

Add to the `__init__` docstring Args:

```
            backend: The resolved KaiBackend this client targets, or None when
                constructed directly (backend behind base_url is unknown).
```

- [ ] **Step 6: Update the class docstring example**

In the `KaiClient` class docstring, change the comment `# Production (auto-discovers kai-assistant URL)` to `# Production (auto-discovers kai-agent URL)`.

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_client.py::TestFromStorageApi -v`
Expected: PASS (8 tests).

- [ ] **Step 8: Run the full client suite + ruff**

Run: `uv run pytest tests/test_client.py -q && uv run ruff check src/kai_client/client.py tests/test_client.py`
Expected: PASS, no ruff errors.

- [ ] **Step 9: Commit**

```bash
git add src/kai_client/client.py tests/test_client.py
git commit -m "feat: default from_storage_api to kai-agent via service param"
```

---

### Task 3: CLI `--service` option

**Files:**
- Modify: `src/kai_client/cli.py` (`main` group ~lines 38-83; `get_client` ~lines 86-104)
- Test: `tests/test_cli.py` (update `test_get_client_auto_discover` ~line 794; add new tests)

**Interfaces:**
- Consumes: `KaiClient.from_storage_api(..., service=...)` from Task 2; `KaiBackend` from Task 1.
- Produces: `main` accepts `--service [agent|assistant]` (envvar `KAI_SERVICE`, default `agent`); `get_client` maps it to `KaiBackend` and passes `service=` to `from_storage_api`.

- [ ] **Step 1: Update/extend CLI tests (failing)**

In `tests/test_cli.py`, add `from kai_client import KaiBackend` to the imports. Update the existing `test_get_client_auto_discover` assertion to expect the service kwarg, and add two new tests in the same class:

```python
    @pytest.mark.asyncio
    async def test_get_client_auto_discover(self, mock_env):
        """Auto-discovery defaults to the agent backend."""
        ctx = MagicMock()
        ctx.obj = {
            "token": "test-token",
            "url": "https://connection.keboola.com",
            "base_url": None,
            "service": "agent",
        }

        with patch("kai_client.cli.KaiClient.from_storage_api") as mock_factory:
            mock_client = MagicMock()
            mock_factory.return_value = mock_client

            client = await get_client(ctx)

            mock_factory.assert_called_once_with(
                storage_api_token="test-token",
                storage_api_url="https://connection.keboola.com",
                service=KaiBackend.AGENT,
            )
            assert client == mock_client

    @pytest.mark.asyncio
    async def test_get_client_service_assistant(self, mock_env):
        """service=assistant maps to KaiBackend.ASSISTANT."""
        ctx = MagicMock()
        ctx.obj = {
            "token": "test-token",
            "url": "https://connection.keboola.com",
            "base_url": None,
            "service": "assistant",
        }

        with patch("kai_client.cli.KaiClient.from_storage_api") as mock_factory:
            mock_factory.return_value = MagicMock()

            await get_client(ctx)

            mock_factory.assert_called_once_with(
                storage_api_token="test-token",
                storage_api_url="https://connection.keboola.com",
                service=KaiBackend.ASSISTANT,
            )

    @pytest.mark.asyncio
    async def test_get_client_base_url_ignores_service(self, mock_env):
        """--base-url bypasses discovery regardless of service."""
        ctx = MagicMock()
        ctx.obj = {
            "token": "test-token",
            "url": "https://connection.keboola.com",
            "base_url": "http://localhost:3000",
            "service": "assistant",
        }

        with patch("kai_client.cli.KaiClient.from_storage_api") as mock_factory:
            client = await get_client(ctx)
            mock_factory.assert_not_called()
            assert client.base_url == "http://localhost:3000"
```

> Note: other tests build `ctx.obj` without a `"service"` key; `get_client` reads it via `.get("service")` so those keep working.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_cli.py -k get_client -v`
Expected: FAIL — `assert_called_once_with` now expects `service=`, and `KaiBackend` import resolves but `get_client` doesn't pass `service` yet.

- [ ] **Step 3: Add the `--service` option to the `main` group**

In `cli.py`, add the import at the top with the other `kai_client` imports:

```python
from kai_client import KaiClient, KaiBackend, __version__  # noqa: E402
```

Add the option decorator to `main` (after the `--base-url` option, before `@click.pass_context`):

```python
@click.option(
    "--service",
    type=click.Choice(["agent", "assistant"]),
    default="agent",
    envvar="KAI_SERVICE",
    help="Which Kai backend to auto-discover (default: agent). Ignored with --base-url.",
)
```

Update the `main` function signature and body to accept/store it:

```python
def main(ctx, token: Optional[str], url: Optional[str], base_url: Optional[str], service: str):
    ...
    ctx.ensure_object(dict)
    ctx.obj["token"] = token
    ctx.obj["url"] = url
    ctx.obj["base_url"] = base_url
    ctx.obj["service"] = service
```

- [ ] **Step 4: Map the service in `get_client`**

Replace the production branch of `get_client`:

```python
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
    service_map = {"agent": KaiBackend.AGENT, "assistant": KaiBackend.ASSISTANT}
    service = service_map[ctx.obj.get("service") or "agent"]
    return await KaiClient.from_storage_api(
        storage_api_token=token,
        storage_api_url=url,
        service=service,
    )
```

- [ ] **Step 5: Run CLI tests to verify they pass**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (all, including the 3 get_client tests).

- [ ] **Step 6: ruff check**

Run: `uv run ruff check src/kai_client/cli.py tests/test_cli.py`
Expected: no errors. (If ruff flags import order on the `KaiClient, KaiBackend` line, run `uv run ruff check --fix` and re-verify.)

- [ ] **Step 7: Commit**

```bash
git add src/kai_client/cli.py tests/test_cli.py
git commit -m "feat: add --service backend selector to CLI"
```

---

### Task 4: Docs, support matrix, and version bump

**Files:**
- Modify: `README.md` (quick-start ~line 44; comparison/config ~lines 184-196; factory-method reference ~lines 400-412; add a support-matrix subsection)
- Modify: `plugins/kai-cli/skills/kai-cli/references/api-details.md` (Client Configuration section, lines ~9-46)
- Modify: `pyproject.toml:3`, `src/kai_client/__init__.py:87`
- Test: `tests/test_cli.py:69` (version test already asserts `__version__` dynamically — no change needed; just keep green)

**Interfaces:**
- Consumes: everything from Tasks 1-3.
- Produces: docs describing agent-as-default + `service=`; version `0.13.0`.

- [ ] **Step 1: Bump the version (two places)**

`pyproject.toml` line 3: `version = "0.12.0"` → `version = "0.13.0"`.
`src/kai_client/__init__.py` line 87: `__version__ = "0.12.0"` → `__version__ = "0.13.0"`.

- [ ] **Step 2: Update README quick-start comment**

Line ~44: change `# Production: Auto-discover the kai-assistant URL from your Keboola stack` to `# Production: Auto-discover the kai-agent URL from your Keboola stack`.

- [ ] **Step 3: Update README config section**

Line ~194: change `# Production (auto-discovers kai-assistant URL)` to `# Production (auto-discovers kai-agent URL)`.

- [ ] **Step 4: Update README factory-method reference**

Replace the factory-method code block (~lines 400-406) and the following sentence with:

````markdown
```python
client = await KaiClient.from_storage_api(
    storage_api_token: str,        # Keboola Storage API token
    storage_api_url: str,          # Keboola connection URL (e.g., https://connection.keboola.com)
    service: KaiBackend = KaiBackend.AGENT,  # Backend to discover (keyword-only)
    timeout: float = 300.0,        # Request timeout in seconds
    stream_timeout: float = 600.0  # Streaming timeout in seconds
)
```

This method auto-discovers the **kai-agent** service URL from your Keboola stack
(the modern agent backend). To target the legacy `kai-assistant` backend
(single-tenant deployments only), pass `service=KaiBackend.ASSISTANT`.
````

- [ ] **Step 5: Add a backend support-matrix subsection to README**

Immediately after the factory-method reference subsection (before the `#### Constructor (For Local Development)` heading), insert:

````markdown
#### Backend Support

`kai-client` targets the **kai-agent** backend by default. The following methods
are supported against kai-agent:

`ping`, `info`, `send_message`, `chat`, `submit_approval`, `get_chat`,
`delete_chat`, `get_history` / `get_all_history`, `get_votes` / `vote` /
`upvote` / `downvote`, `get_usage`, `get_settings` / `update_settings` /
`get_user_settings` / `update_user_settings`, `get_tools`, `get_suggestions`.

These methods use the older Vercel-AI-SDK-v6 / tool-result protocols and are
**not supported by kai-agent** (kept only for the legacy backend):
`send_tool_approval_response`, `approve_tool`, `reject_tool`, `send_tool_result`,
`confirm_tool`, `deny_tool`, `resume_stream`. Use `submit_approval` for tool
approvals on kai-agent.
````

- [ ] **Step 6: Update api-details.md**

In the "Production Mode (Auto-Discovery)" block (~line 13), change the intro line to note the default, and update the code sample to mention `service`:

```markdown
The Kai client automatically discovers the Kai API URL from the Keboola stack
(defaults to the **kai-agent** backend):

```python
from kai_client import KaiClient, KaiBackend

# Defaults to kai-agent
async with await KaiClient.from_storage_api(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com",
) as client:
    response = await client.ping()

# Legacy backend (single-tenant deployments only)
client = await KaiClient.from_storage_api(
    storage_api_token="your-token",
    storage_api_url="https://connection.keboola.com",
    service=KaiBackend.ASSISTANT,
)
```
```

Add a CLI note in the same file near the CLI flag example (~line 42-45):

```markdown
Select the backend for auto-discovery (default `agent`):
```bash
kai --service assistant chat -m "Hello"   # legacy backend
```
```

- [ ] **Step 7: Verify version + full suite + ruff**

Run: `uv run python -c "import kai_client; print(kai_client.__version__)"`
Expected: `0.13.0`.

Run: `uv run pytest -q && uv run ruff check .`
Expected: all tests PASS, no ruff errors.

- [ ] **Step 8: Commit**

```bash
git add README.md plugins/kai-cli/skills/kai-cli/references/api-details.md pyproject.toml src/kai_client/__init__.py
git commit -m "docs: document kai-agent default and backend support matrix; bump 0.13.0"
```

---

### Task 5: Manual end-to-end verification against kai-agent

**Files:**
- Create (temporary, in scratchpad — not committed): a verification script.

**Interfaces:**
- Consumes: the full implementation; the real us-east4 token in `~/Keboola/KaiClient/.env.local` (vars `STORAGE_API_TOKEN` / `STORAGE_API_URL`). NEVER print the token.

- [ ] **Step 1: Confirm agent discovery resolves the agent URL**

Write a scratchpad script that loads `.env.local`, calls `from_storage_api()` (default), and prints only `client.base_url` and `client.backend` (never the token). Run it.
Expected: base_url contains `kai-agent` (e.g. `https://kai-agent.us-east4.gcp.keboola.com`), `backend == KaiBackend.AGENT`.

- [ ] **Step 2: Confirm a message round-trips against kai-agent**

Extend the script to run `chat_id, text = await client.chat("Reply with the single word: pong")` and print the response text.
Expected: a non-empty text response from the agent backend (proves the agent chat endpoint works end-to-end via discovery).

- [ ] **Step 3: Record the result**

Note the resolved agent URL (host only, no token) and that `chat()` returned text, in the final report. Delete the scratchpad script.

---

## Self-Review

**Spec coverage:**
- Spec §1 (KaiBackend enum) → Task 1. ✔
- Spec §2 (generalized `from_storage_api`, error message, `*` keyword-only) → Task 2. ✔
- Spec §3 (`self.backend` incl. raw-string normalization via `KaiBackend(service_id)`/`ValueError`) → Task 2 Steps 4-5 + tests `test_raw_string_service`, `test_unknown_service_id_leaves_backend_none`. ✔
- Spec §4 (CLI `--service`, base-url bypass) → Task 3. ✔
- Spec §5 (support matrix) → Task 4 Steps 5-6. ✔
- Spec §6 (README/api-details/version/changelog) → Task 4. Note: no CHANGELOG file exists; the "changelog note" is delivered via the version-bump commit message + README. ✔
- Spec "Manual verification" → Task 5. ✔
- Spec "Out of scope" (no ToolRestrictions, no runtime guard, no removal) → respected; no task touches them. ✔

**Placeholder scan:** No TBD/TODO; all code steps show full code. ✔

**Type consistency:** `KaiBackend` (`AGENT`/`ASSISTANT`, values `kai-agent`/`kai-assistant`), `service` param name, `self.backend`, `backend=` kwarg, and error codes are used identically across Tasks 1-5 and the tests. ✔

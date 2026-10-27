"""Resolution of the Storage API token from the environment."""

import os
from collections.abc import Mapping
from typing import Optional

from kai_client.exceptions import KaiConfigurationError

KAI_STORAGE_API_TOKEN_ENV = "KAI_STORAGE_API_TOKEN"
KAI_ENABLED_ENV = "KAI_ENABLED"
STORAGE_API_TOKEN_ENV = "STORAGE_API_TOKEN"

_FALSY_VALUES = frozenset({"", "0", "false", "no", "off"})


def _is_kai_enabled(environ: Mapping[str, str]) -> bool:
    return environ.get(KAI_ENABLED_ENV, "").strip().lower() not in _FALSY_VALUES


def resolve_storage_api_token(
    token: Optional[str] = None,
    environ: Optional[Mapping[str, str]] = None,
) -> Optional[str]:
    """
    Resolve the Storage API token Kai should authenticate with.

    Order:
        1. `token`, when passed explicitly.
        2. `KAI_STORAGE_API_TOKEN` — the dedicated Kai token Keboola injects into Data Apps
           deployed with Kai enabled; kai-agent scopes it to the app's own workspace.
        3. `STORAGE_API_TOKEN` — unless `KAI_ENABLED` is set, in which case the Kai token is
           required and falling back to the user's token is refused.

    Args:
        token: Explicitly provided token; always wins when non-empty.
        environ: Environment to read from (default: `os.environ`).

    Returns:
        The resolved token, or None when no token is available.

    Raises:
        KaiConfigurationError: If `KAI_ENABLED` is set but `KAI_STORAGE_API_TOKEN` is missing.
    """
    if token:
        return token

    env = os.environ if environ is None else environ

    kai_token = env.get(KAI_STORAGE_API_TOKEN_ENV)
    if kai_token:
        return kai_token

    if _is_kai_enabled(env):
        raise KaiConfigurationError(
            message=(
                f"{KAI_ENABLED_ENV} is set but {KAI_STORAGE_API_TOKEN_ENV} is missing. "
                "Redeploy the Data App as a user who is allowed to create Storage API "
                "tokens so Keboola can issue the Kai token."
            ),
            code="config:kai_token_missing",
        )

    return env.get(STORAGE_API_TOKEN_ENV) or None

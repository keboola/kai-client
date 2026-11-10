"""Tests for Storage API token resolution."""

import pytest

from kai_client import KaiConfigurationError, KaiError, resolve_storage_api_token

EXPLICIT = "explicit-token"
KAI = "kai-token"
USER = "user-token"


class TestResolveStorageApiToken:
    """Tests for resolve_storage_api_token()."""

    @pytest.mark.parametrize(
        ("explicit", "environ", "expected"),
        [
            # explicit token always wins
            (EXPLICIT, {}, EXPLICIT),
            (EXPLICIT, {"KAI_STORAGE_API_TOKEN": KAI, "STORAGE_API_TOKEN": USER}, EXPLICIT),
            (EXPLICIT, {"KAI_ENABLED": "1"}, EXPLICIT),
            (EXPLICIT, {"KAI_ENABLED": "1", "STORAGE_API_TOKEN": USER}, EXPLICIT),
            # Kai token wins over the user token, with or without KAI_ENABLED
            (None, {"KAI_STORAGE_API_TOKEN": KAI}, KAI),
            (None, {"KAI_STORAGE_API_TOKEN": KAI, "STORAGE_API_TOKEN": USER}, KAI),
            (None, {"KAI_ENABLED": "1", "KAI_STORAGE_API_TOKEN": KAI}, KAI),
            (
                None,
                {"KAI_ENABLED": "1", "KAI_STORAGE_API_TOKEN": KAI, "STORAGE_API_TOKEN": USER},
                KAI,
            ),
            # without KAI_ENABLED the pre-existing STORAGE_API_TOKEN behaviour is kept
            (None, {"STORAGE_API_TOKEN": USER}, USER),
            (None, {"KAI_STORAGE_API_TOKEN": "", "STORAGE_API_TOKEN": USER}, USER),
            (None, {}, None),
            (None, {"STORAGE_API_TOKEN": ""}, None),
            # an empty explicit token is treated as not passed
            ("", {"STORAGE_API_TOKEN": USER}, USER),
            # KAI_ENABLED with a falsy value does not count as enabled
            (None, {"KAI_ENABLED": "", "STORAGE_API_TOKEN": USER}, USER),
            (None, {"KAI_ENABLED": "0", "STORAGE_API_TOKEN": USER}, USER),
            (None, {"KAI_ENABLED": "false", "STORAGE_API_TOKEN": USER}, USER),
            (None, {"KAI_ENABLED": " Off ", "STORAGE_API_TOKEN": USER}, USER),
        ],
    )
    def test_resolution_order(self, explicit, environ, expected):
        assert resolve_storage_api_token(explicit, environ=environ) == expected

    @pytest.mark.parametrize(
        "environ",
        [
            {"KAI_ENABLED": "1"},
            {"KAI_ENABLED": "1", "STORAGE_API_TOKEN": USER},
            {"KAI_ENABLED": "true", "STORAGE_API_TOKEN": USER},
            {"KAI_ENABLED": "1", "KAI_STORAGE_API_TOKEN": "", "STORAGE_API_TOKEN": USER},
        ],
    )
    def test_kai_enabled_without_kai_token_raises(self, environ):
        with pytest.raises(KaiConfigurationError) as exc_info:
            resolve_storage_api_token(environ=environ)

        error = exc_info.value
        assert isinstance(error, KaiError)
        assert error.code == "config:kai_token_missing"
        assert "KAI_STORAGE_API_TOKEN" in error.message
        assert "Redeploy" in error.message

    def test_reads_os_environ_by_default(self, monkeypatch):
        monkeypatch.delenv("KAI_ENABLED", raising=False)
        monkeypatch.setenv("KAI_STORAGE_API_TOKEN", KAI)
        monkeypatch.setenv("STORAGE_API_TOKEN", USER)

        assert resolve_storage_api_token() == KAI

    def test_os_environ_kai_enabled_without_kai_token_raises(self, monkeypatch):
        monkeypatch.setenv("KAI_ENABLED", "1")
        monkeypatch.delenv("KAI_STORAGE_API_TOKEN", raising=False)
        monkeypatch.setenv("STORAGE_API_TOKEN", USER)

        with pytest.raises(KaiConfigurationError):
            resolve_storage_api_token()

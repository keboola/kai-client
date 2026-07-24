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

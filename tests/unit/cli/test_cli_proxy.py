"""Tests for proxy CLI configuration helpers."""

from unittest.mock import MagicMock

from detent.cli.proxy import _build_http_adapter, _resolve_proxy_upstream
from detent.config import DetentConfig, ProxyConfig


def test_resolve_proxy_upstream_uses_explicit_config() -> None:
    config = DetentConfig(agent="cursor", proxy=ProxyConfig(upstream_url="https://api.anthropic.com"))

    assert _resolve_proxy_upstream(config) == "https://api.anthropic.com"


def test_resolve_proxy_upstream_falls_back_by_agent() -> None:
    config = DetentConfig(agent="codex")

    assert _resolve_proxy_upstream(config) == "https://api.openai.com"


def test_build_http_adapter_uses_openai_provider_for_openai_upstream() -> None:
    config = DetentConfig(agent="cursor")

    adapter = _build_http_adapter(config, MagicMock(), "https://api.openai.com")

    assert adapter is not None
    assert adapter.agent_name == "cursor"
    assert adapter.upstream_host == "api.openai.com"


def test_build_http_adapter_uses_anthropic_provider_for_anthropic_upstream() -> None:
    config = DetentConfig(agent="cursor")

    adapter = _build_http_adapter(config, MagicMock(), "https://api.anthropic.com")

    assert adapter is not None
    assert adapter.agent_name == "cursor"
    assert adapter.upstream_host == "api.anthropic.com"

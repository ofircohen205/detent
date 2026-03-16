"""Unit tests for OpenTelemetry setup helpers."""

import pytest

from detent.config import TelemetryConfig
from detent.observability import setup_telemetry


def test_setup_telemetry_noop_when_disabled(monkeypatch):
    monkeypatch.setattr("detent.observability._initialized", False)

    def _should_not_be_called(*args, **kwargs):
        raise AssertionError("build_exporter was called unexpectedly")

    monkeypatch.setattr("detent.observability.build_exporter", _should_not_be_called)

    setup_telemetry(TelemetryConfig(enabled=False))


def test_setup_telemetry_missing_sdk(monkeypatch):
    monkeypatch.setattr("detent.observability._initialized", False)

    def _raise_import(*args, **kwargs):
        raise ImportError("missing dependency")

    monkeypatch.setattr("detent.observability.build_exporter", _raise_import)

    with pytest.raises(ImportError, match="OpenTelemetry SDK not installed"):
        setup_telemetry(TelemetryConfig(enabled=True))

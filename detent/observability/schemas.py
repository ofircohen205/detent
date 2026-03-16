from typing import Any

from pydantic import BaseModel


class ExporterBundle(BaseModel):
    """Bundle containing both span and metric exporters."""

    span_exporter: Any
    metric_exporter: Any

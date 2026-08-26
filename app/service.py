from __future__ import annotations

from .service_base import (
    COMMON_ENCODINGS,
    TYPE_EXTENSION,
    TYPE_NAME_EXTENSION,
    BaseServiceMixin,
    CommandResult,
    CommandRunner,
)
from .service_components import ComponentServiceMixin
from .service_extract import ExtractServiceMixin
from .service_graph import GraphServiceMixin
from .service_quantize import QuantizeServiceMixin
from .service_rebuild import RebuildServiceMixin


class PylabviewService(
    GraphServiceMixin,
    ComponentServiceMixin,
    ExtractServiceMixin,
    RebuildServiceMixin,
    QuantizeServiceMixin,
    BaseServiceMixin,
):
    """pylabview conversion, graph analysis, and component-editing service."""


__all__ = [
    "COMMON_ENCODINGS",
    "TYPE_EXTENSION",
    "TYPE_NAME_EXTENSION",
    "CommandResult",
    "CommandRunner",
    "PylabviewService",
]

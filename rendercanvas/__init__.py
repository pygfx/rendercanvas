"""
RenderCanvas: one canvas API, multiple backends.
"""

# ruff: noqa: F401

from ._version import __version__, version_info
from . import _coreutils
from ._enums import CursorShape, EventType, UpdateMode
from .base import BaseRenderCanvas, BaseLoop
from ._loop import get_running_loop
from . import contexts
from . import utils


__all__ = [
    "BaseLoop",
    "BaseRenderCanvas",
    "CursorShape",
    "EventType",
    "UpdateMode",
    "get_running_loop",
]

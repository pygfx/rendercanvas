"""
RenderCanvas: one canvas API, multiple backends.
"""

# ruff: noqa: F401

from ._version import __version__, version_info
from . import _coreutils
from ._enums import CursorShape, EventType, UpdateMode
from .base import BaseRenderCanvas, BaseLoop

__all__ = ["BaseLoop", "BaseRenderCanvas", "CursorShape", "EventType", "UpdateMode"]

"""
RenderCanvas: one canvas API, multiple backends.
"""

# ruff: noqa: F401

from ._version import __version__, version_info
from . import core
from . import utils
from . import contexts
from .base import BaseRenderCanvas, BaseLoop
from .core.enums import CursorShape, EventType, UpdateMode


__all__ = ["BaseLoop", "BaseRenderCanvas", "CursorShape", "EventType", "UpdateMode"]

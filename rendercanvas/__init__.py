"""
rendercanvas: one canvas API, multiple backends
"""

# ruff: noqa: F401

from ._version import __version__, version_info
from . import _gui_utils
from .base import WgpuCanvasInterface, WgpuCanvasBase, WgpuAutoGui

__all__ = [
    "WgpuCanvasInterface",
    "WgpuCanvasBase",
    "WgpuAutoGui",
]

"""
This module implements all async functionality that one can use in any ``rendercanvas`` backend.
Currently supported are ``sleep()`` and ``Event``.
"""

import sys

from .asyncadapter import Event as _Event
from .asyncadapter import sleep as _sleep


def detect_current_async_lib() -> str:
    """Get the lib name of the currently active async lib, or None."""

    ob = sys.get_asyncgen_hooks()[0]

    libname = "none"
    if ob is not None:
        try:
            libname = ob.__module__.partition(".")[0]
        except AttributeError:
            libname = "unknown"
        if libname == "rendercanvas":
            libname = "rendercanvas.utils.asyncadapter"
        elif libname == "pyodide":
            libname = "asyncio"
        elif libname == "uvloop":
            libname = "asyncio"

    return libname


async def sleep(delay):
    """Sleep using rendercanvas' own async mirco-framework."""
    libname = detect_current_async_lib()
    if not libname.startswith("rendercanvas"):
        raise RuntimeError(
            f"Trying to use ``rendercanvas.utils.asyncs.sleep()``, but the current async framework is {libname}!"
        )

    await _sleep(delay)


class Event:
    """Event class for rendercanvas' own async micro-framework."""

    def __new__(cls):
        libname = detect_current_async_lib()
        if not libname.startswith("rendercanvas"):
            raise RuntimeError(
                f"Trying to use ``rendercanvas.utils.asyncs.Event()``, but the current async framework is {libname}!"
            )
        return _Event()

    async def wait(self):
        return

    def set(self):
        pass

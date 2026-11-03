"""
This module implements all async functionality that one can use in any ``rendercanvas`` backend.
Currently supported are ``sleep()`` and ``Event``.
"""

import sys

from ..core.coreutils import IS_PYODIDE
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


# Rendercanvas does not use detect_current_call_soon_threadsafe(), but we still include it here because
# downstream code may depend on it, plus it demonstrates the recommended way to get the call_soon_threadsafe() effectively.
# wgpu-py uses its own copy of this funtion.
def detect_current_call_soon_threadsafe():
    """Get the current applicable call_soon_threadsafe function, or None"""

    # Pyodide always runs asyncio (which wraps the JS native event loop)
    if IS_PYODIDE:
        return sys.modules["asyncio"].get_running_loop().call_soon_threadsafe

    # Get asyncgen hook func, return fast when no async loop active
    ob = sys.get_asyncgen_hooks()[0]
    if ob is None:
        return None

    # Super-fast path that works for loop objects that have call_soon_threadsafe()
    # and use sys.set_asyncgen_hooks() on a method of the same loop object.
    # Works with asyncio, rendercanvas' asyncadapter, and also custom (direct) loops.
    try:
        return ob.__self__.call_soon_threadsafe
    except AttributeError:
        pass

    # Otherwise, checkout the module name
    try:
        libname = ob.__module__.partition(".")[0]
    except AttributeError:
        return None

    if libname == "trio":
        # Still pretty fast for trio
        trio = sys.modules[libname]
        token = trio.lowlevel.current_trio_token()
        return token.run_sync_soon
    else:
        # Ok, it looks like there is an async loop, try to get the func.
        # This is also a fallback for asyncio (in case the ob.__self__ stops working)
        # Note: we have a unit test for the asyncio fast-path, so we will know when we need to update,
        # but the code below makes sure that it keeps working regardless (just a tiiiny bit slower).
        if libname == "pyodide":
            libname = "asyncio"
        mod = sys.modules.get(libname, None)
        if mod is None:
            return None
        try:
            return mod.call_soon_threadsafe
        except AttributeError:
            pass
        try:
            return mod.get_running_loop().call_soon_threadsafe
        except Exception:  # (RuntimeError, AttributeError) but accept any error
            pass


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

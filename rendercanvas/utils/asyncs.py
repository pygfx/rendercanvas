"""
This module implements all async functionality that one can use in any ``rendercanvas`` backend.

To give an idea how to implement a generic async sleep function:

.. code-block:: py

    libname = detect_current_async_lib()
    sleep = sys.modules[libname].sleep

"""

import sys

from .._coreutils import IS_WIN, call_later_from_thread


USE_THREADED_TIMER = IS_WIN


# Below detection methods use ``sys.get_asyncgen_hooks()`` for fast and robust detection.
# Compared to sniffio, this is faster and also  works when not inside a task.


def detect_current_async_lib():
    """Get the lib name of the currently active async lib, or None."""
    ob = sys.get_asyncgen_hooks()[0]
    if ob is not None:
        try:
            libname = ob.__module__.partition(".")[0]
        except AttributeError:
            return None
        if libname == "rendercanvas":
            libname = "rendercanvas.utils.asyncadapter"
        elif libname == "pyodide":
            libname = "asyncio"
        return libname


def detect_current_call_soon_threadsafe():
    """Get the current applicable call_soon_threadsafe function, or None"""

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
    """Generic async sleep. Works with trio, asyncio and rendercanvas-native.

    On Windows, with asyncio or trio, this uses a special sleep routine that is more accurate than the ``sleep()`` of asyncio/trio.
    """

    if delay > 0 and USE_THREADED_TIMER:
        call_soon_threadsafe = detect_current_call_soon_threadsafe()
        if call_soon_threadsafe:
            event = Event()
            call_later_from_thread(delay, call_soon_threadsafe, event.set)
            await event.wait()
    else:
        libname = detect_current_async_lib()
        if libname is not None:
            sleep = sys.modules[libname].sleep
            await sleep(delay)


class Event:
    """Generic async event object. Works with trio, asyncio and rendercanvas-native."""

    def __new__(cls):
        libname = detect_current_async_lib()
        if libname is None:
            return object.__new__(cls)
        else:
            Event = sys.modules[libname].Event  # noqa
            return Event()

    async def wait(self):
        return

    def set(self):
        pass

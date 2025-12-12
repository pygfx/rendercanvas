"""
This module implements all async functionality that one can use in any ``rendercanvas`` backend.

To give an idea how to implement a generic async sleep function:

.. code-block:: py

    libname = detect_current_async_lib()
    sleep = sys.modules[libname].sleep

"""

import sys

from .._coreutils import IS_WIN, call_later_from_thread, thread_local


USE_THREADED_TIMER = IS_WIN


def detect_current_async_lib():
    """Get the lib name of the currently active async lib, or None.

    This uses ``sys.get_asyncgen_hooks()`` for fast and robust detection.
    Compared to sniffio, this is faster and also  works when not inside a task.
    Compared to ``rendercanvas.get_running_loop()`` this also works when asyncio
    is running while the rendercanvas loop is not.
    """
    ob = sys.get_asyncgen_hooks()[0]
    if ob is not None:
        try:
            libname = ob.__module__.partition(".")[0]
        except AttributeError:
            return None
        if libname == "rendercanvas":
            libname = "rendercanvas.utils.asyncadapter"
        return libname


async def sleep(delay):
    """Generic async sleep. Works with trio, asyncio and rendercanvas-native.

    On Windows, with asyncio or trio, this uses a special sleep routine that is more accurate than the ``sleep()`` of asyncio/trio.
    """

    rc_loop = getattr(thread_local, "loop", None)  # == get_running_loop

    if delay > 0 and USE_THREADED_TIMER and rc_loop is not None:
        event = Event()
        call_later_from_thread(delay, rc_loop.call_soon_threadsafe, event.set)
        await event.wait()
    else:
        libname = detect_current_async_lib()
        sleep = sys.modules[libname].sleep
        await sleep(delay)


class Event:
    """Generic async event object. Works with trio, asyncio and rendercanvas-native."""

    def __new__(cls):
        libname = detect_current_async_lib()
        Event = sys.modules[libname].Event  # noqa
        return Event()

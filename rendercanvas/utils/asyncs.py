"""
This module implements all async functionality that one can use in any ``rendercanvas`` backend.
This uses ``sniffio`` to detect the async framework in use.

To give an idea how to use ``sniffio`` to get a generic async sleep function:

.. code-block:: py

    libname = sniffio.current_async_library()
    sleep = sys.modules[libname].sleep

"""

import sys

import sniffio

from .._coreutils import IS_WIN, call_later_from_thread


USE_THREADED_TIMER = True


async def sleep(delay):
    """Generic async sleep. Works with trio, asyncio and rendercanvas-native.

    On Windows, with asyncio or trio, this uses a special sleep routine that is more accurate than the standard ``sleep()``.
    """
    libname = sniffio.current_async_library()
    if libname == "asyncio" and delay > 0 and USE_THREADED_TIMER:
        asyncio = sys.modules[libname]
        loop = asyncio.get_running_loop()
        event = asyncio.Event()
        call_later_from_thread(delay, loop.call_soon_threadsafe, event.set)
        await event.wait()
    elif libname == "trio" and delay > 0 and USE_THREADED_TIMER:
        trio = sys.modules[libname]
        event = trio.Event()
        token = trio.lowlevel.current_trio_token()
        call_later_from_thread(delay, token.run_sync_soon, event.set)
        await event.wait()
    else:
        sleep = sys.modules[libname].sleep
        await sleep(delay)


class Event:
    """Generic async event object. Works with trio, asyncio and rendercanvas-native."""

    def __new__(cls):
        libname = sniffio.current_async_library()
        Event = sys.modules[libname].Event  # noqa
        return Event()

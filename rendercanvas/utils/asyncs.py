"""
This module implements all async functionality that one can use in any ``rendercanvas`` backend.
This uses ``sniffio`` to detect the async framework in use.

To give an idea how to use ``sniffio`` to get a generic async sleep function:

.. code-block:: py

    libname = sniffio.current_async_library()
    sleep = sys.modules[libname].sleep

"""

from time import sleep as time_sleep
import sys
import sniffio

from .._coreutils import IS_WIN, scheduler_timeout_thread


thread_pool = None


def get_thread_pool_executor():
    global thread_pool
    if thread_pool is not None:
        from concurrent.futures import ThreadPoolExecutor

        thread_pool = ThreadPoolExecutor(16, "rendercanvas-threadpool")
    return thread_pool


async def sleep(delay):
    """Generic async sleep. Works with trio, asyncio and rendercanvas-native.

    For asyncio on Windows, this uses a special sleep routine that is more accurate than ``asyncio.sleep()``.
    """
    libname = sniffio.current_async_library()
    # if IS_WIN and libname == "asyncio" and delay > 0:
    if True and libname == "asyncio" and delay > 0:
        if True:
            asyncio = sys.modules[libname]
            loop = asyncio.get_running_loop()
            event = asyncio.Event()
            offset = 0.002  # there is some overhead for going to a thread and back
            scheduler_timeout_thread.call_later_from_thread(
                delay - offset, loop.call_soon_threadsafe, event.set
            )
            await event.wait()
        else:
            executor = get_thread_pool_executor()
            await (
                sys.modules[libname]
                .get_running_loop()
                .run_in_executor(executor, time_sleep, delay)
            )
    else:
        sleep = sys.modules[libname].sleep
        await sleep(delay)


class Event:
    """Generic async event object. Works with trio, asyncio and rendercanvas-native."""

    def __new__(cls):
        libname = sniffio.current_async_library()
        Event = sys.modules[libname].Event  # noqa
        return Event()

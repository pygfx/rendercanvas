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


async def sleep(delay):
    """Generic async sleep. Works with trio, asyncio and rendercanvas-native."""
    libname = sniffio.current_async_library()
    sleep = sys.modules[libname].sleep
    await sleep(delay)


class Event:
    """Generic async event object. Works with trio, asyncio and rendercanvas-native."""

    def __new__(cls):
        libname = sniffio.current_async_library()
        Event = sys.modules[libname].Event  # noqa
        return Event()

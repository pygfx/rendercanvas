import sys
import sniffio


async def sleep(delay):
    libname = sniffio.current_async_library()
    sleep = sys.modules[libname].sleep
    await sleep(delay)


class Event:
    def __new__(cls):
        libname = sniffio.current_async_library()
        Event = sys.modules[libname].Event  # noqa
        return Event()

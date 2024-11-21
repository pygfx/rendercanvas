"""
Implements an asyncio event loop, used in some backends.
"""

# This is used for backends that don't have an event loop by themselves, like glfw.
# Would be nice to also allow a loop based on e.g. Trio. But we can likely fit that in
# when the time comes.

__all__ = ["AsyncioLoop", "AsyncioTimer"]

import asyncio

from .base import BaseLoop, BaseTimer


class AsyncioTimer(BaseTimer):
    """Timer based on asyncio."""

    _handle = None

    def _rc_init(self):
        pass

    def _rc_start(self):
        def tick():
            self._handle = None
            self._tick()

        if self._handle is not None:
            self._handle.cancel()
        asyncio_loop = self._loop._loop
        self._handle = asyncio_loop.call_later(self._interval, tick)

    def _rc_stop(self):
        if self._handle:
            self._handle.cancel()
            self._handle = None


class AsyncioLoop(BaseLoop):
    _TimerClass = AsyncioTimer
    _the_loop = None

    @property
    def _loop(self):
        if self._the_loop is None:
            self._the_loop = self._get_loop()
        return self._the_loop

    def _get_loop(self):
        try:
            return asyncio.get_running_loop()
        except Exception:
            pass
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

    def _rc_run(self):
        if not self._loop.is_running():
            self._loop.run_forever()

    def _rc_stop(self):
        # Note: is only called when we're inside _rc_run
        self._loop.stop()

    def _rc_call_soon(self, callback, *args):
        self._loop.call_soon(callback, *args)

    def _rc_gui_poll(self):
        pass

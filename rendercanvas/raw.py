"""
Implements a pure Python raw event-loop for backends that don't have an event-loop by themselves, like glfw.

There is not really an advantage over say the asyncio loop, except perhaps that it does not use
asyncio, so you can start an asyncio loop from a callback. Other than that, this is more
for educational purposes: look how simple a loop can be!
"""

__all__ = ["RawLoop", "loop"]

import queue

from .base import BaseLoop
from .core.coreutils import call_later_from_thread, logger


class RawLoop(BaseLoop):
    def __init__(self):
        super().__init__()
        self._queue = queue.SimpleQueue()
        self._should_stop = False

    def _rc_init(self):
        # This gets called when the first canvas is created (possibly after having run and stopped before).
        self._should_stop = False

    def _rc_run(self):
        self._rc_init()

        # If no canvases, we flush the current queue and then stop
        if not self.get_canvases():
            self._queue.put(self.stop)

        while not self._should_stop:
            callback = self._queue.get(True, None)
            try:
                callback()
            except Exception as err:
                logger.error(f"Error in RawLoop callback: {err}")

        # Clear queue
        # NOTE: there could be call laters underway!
        while not self._queue.empty():
            self._queue.get_nowait()

    async def _rc_run_async(self):
        raise NotImplementedError()

    def _rc_stop(self):
        # Note: is only called when we're inside _rc_run
        self._should_stop = True
        self._queue.put(lambda: None)  # trigger an iter

    def _rc_call_soon(self, callback):
        self._queue.put(callback)

    def _rc_call_soon_threadsafe(self, callback):
        self._queue.put(callback)


loop = RawLoop()

"""
Implements a pure Python raw event-loop for backends that don't have an event-loop by themselves, like glfw.

There is not really an advantage over say the asyncio loop, except perhaps that it does not use
asyncio, so you can start an asyncio loop from a callback. Other than that, this is more
for educational purposes: look how simple a loop can be!
"""

__all__ = ["RawLoop", "loop"]

import queue

from .base import BaseLoop
from ._coreutils import logger, call_later_from_thread


class RawLoop(BaseLoop):
    def __init__(self):
        super().__init__()
        self._queue = queue.SimpleQueue()
        self._should_stop = False

    def _rc_init(self):
        # This gets called when the first canvas is created (possibly after having run and stopped before).
        self._should_stop = False

    def _rc_run(self):
        while not self._should_stop:
            callback = self._queue.get(True, None)
            try:
                callback()
            except Exception as err:
                logger.error(f"Error in RawLoop callback: {err}")
        # Note that the queue may still contain pending callbacks, but these will
        # mostly be task.step() for finished tasks (coro already deleted), so its ok.

    async def _rc_run_async(self):
        raise NotImplementedError()

    def _rc_stop(self):
        # Note: is only called when we're inside _rc_run
        self._should_stop = True
        self._queue.put(lambda: None)  # trigger an iter

    def _rc_add_task(self, async_func, name):
        # we use the async adapter with call_later
        return super()._rc_add_task(async_func, name)

    def _rc_call_later(self, delay, callback):
        if delay <= 0:
            self._queue.put(callback)
        else:
            # Using call_later_from_thread keeps the loop super-simple.
            # Note that its high-precision-on-Windows feature is not why we use it; precision is handled in asyns.py.
            call_later_from_thread(delay, self._rc_call_soon_threadsafe, callback)

    def _rc_call_soon_threadsafe(self, callback):
        self._queue.put(callback)


loop = RawLoop()

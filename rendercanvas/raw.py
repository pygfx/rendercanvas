"""
Implements a pure Python raw event-loop for backends that don't have an event-loop by themselves, like glfw.

There is not really an advantage over say the asyncio loop, except perhaps that it does not use
asyncio, so you can start an asyncio loop from a callback. Other than that, this is more
for educational purposes: look how simple a loop can be!
"""

__all__ = ["RawLoop", "loop"]

import time
import heapq
import logging
import threading
from itertools import count

from .base import BaseLoop


logger = logging.getLogger("rendercanvas")
counter = count()


class CallAtWrapper:
    def __init__(self, time, callback):
        self.index = next(counter)
        self.time = time
        self.callback = callback

    def __lt__(self, other):
        return (self.time, self.index) < (other.time, other.index)

    def cancel(self):
        self.callback = None


class RawLoop(BaseLoop):
    def __init__(self):
        super().__init__()
        self._queue = []  # prioriry queue
        self._should_stop = False
        self._event = threading.Event()

    def _rc_init(self):
        # This gets called when the first canvas is created (possibly after having run and stopped before).
        pass

    def _rc_run(self):
        while not self._should_stop:
            self._event.clear()

            # Get wrapper for callback that is first to be called
            try:
                wrapper = heapq.heappop(self._queue)
            except IndexError:
                wrapper = None

            if wrapper is None:
                # Empty queue, exit
                break
            else:
                # Wait until its time for it to be called
                wait_time = wrapper.time - time.perf_counter()
                self._event.wait(max(wait_time, 0))

                # Put it back or call it?
                if time.perf_counter() < wrapper.time:
                    heapq.heappush(self._queue, wrapper)
                elif wrapper.callback is not None:
                    try:
                        wrapper.callback()
                    except Exception as err:
                        logger.error(f"Error in callback: {err}")

    async def _rc_run_async(self):
        raise NotImplementedError()

    def _rc_stop(self):
        # Note: is only called when we're inside _rc_run
        self._should_stop = True
        self._event.set()

    def _rc_add_task(self, async_func, name):
        # we use the async adapter with call_later
        return super()._rc_add_task(async_func, name)

    def _rc_call_later(self, delay, callback):
        now = time.perf_counter()
        time_at = now + max(0, delay)
        wrapper = CallAtWrapper(time_at, callback)
        heapq.heappush(self._queue, wrapper)
        self._event.set()


loop = RawLoop()

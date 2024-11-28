"""
Implements an asyncio event loop for backends that don't have an event loop by themselves, like glfw.
"""

__all__ = ["AsyncioLoop", "loop"]


from .base import BaseLoop


class AsyncioLoop(BaseLoop):
    _the_loop = None

    def __init__(self):
        super().__init__()
        self._tasks = []

    @property
    def _loop(self):
        if self._the_loop is None:
            import asyncio

            try:
                self._the_loop = asyncio.get_running_loop()
            except Exception:
                pass
            if self._the_loop is None:
                self._the_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._the_loop)
        return self._the_loop

    def _rc_add_task(self, func, name):
        task = self._loop.create_task(func(), name=name)
        self._tasks.append(task)
        task.add_done_callback(self._tasks.remove)
        return task

    def _rc_run(self):
        if not self._loop.is_running():
            self._loop.run_forever()

    def _rc_stop(self):
        # Note: is only called when we're inside _rc_run
        self._loop.stop()
        while self._tasks:
            t = self._tasks.pop(-1)
            t.cancel()  # is a no-op if the task is no longer running


loop = AsyncioLoop()

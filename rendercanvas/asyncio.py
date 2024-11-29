"""
Implements an asyncio event loop for backends that don't have an event loop by themselves, like glfw.
"""

__all__ = ["AsyncioLoop", "loop"]


from .base import BaseLoop


class AsyncioLoop(BaseLoop):
    _the_loop = None

    def __init__(self):
        super().__init__()
        self.__tasks = set()

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

    async def run_async(self):
        pass  # todo: xx

    def _rc_run(self):
        if not self._loop.is_running():
            self._loop.run_forever()

    def _rc_stop(self):
        # Note: is only called when we're inside _rc_run.
        # I.e. if the loop was already running
        while self.__tasks:
            task = self.__tasks.pop()
            task.cancel()  # is a no-op if the task is no longer running
        self._loop.stop()
        self._the_loop = None

    def _rc_add_task(self, func, name):
        task = self._loop.create_task(func(), name=name)
        self.__tasks.add(task)
        task.add_done_callback(self.__tasks.discard)
        return task

    def _rc_call_later(self, *args):
        raise NotImplementedError()  # we implement _rc_add_task instead


loop = AsyncioLoop()

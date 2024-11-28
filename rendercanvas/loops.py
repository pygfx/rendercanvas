"""
Implements an asyncio event loop, used in some backends.
"""

# This is used for backends that don't have an event loop by themselves, like glfw.
# Would be nice to also allow a loop based on e.g. Trio. But we can likely fit that in
# when the time comes.

__all__ = ["AsyncioLoop", "TrioLoop"]


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

    # def _rc_call_soon(self, callback, *args):
    #     self._loop.call_soon(callback, *args)

    def _rc_gui_poll(self):
        pass


class TrioLoop(BaseLoop):
    def __init__(self):
        super().__init__()
        import trio

        self._pending_tasks = []
        self._cancel_scope = None
        self._send_channel, self._receive_channel = trio.open_memory_channel(99)

    def _rc_add_task(self, async_func, name):
        self._send_channel.send_nowait((async_func, name))
        return None

    async def _rc_run_async(self):
        import trio

        with trio.CancelScope() as self._cancel_scope:
            async with trio.open_nursery() as nursery:
                while True:
                    async_func, name = await self._receive_channel.receive()
                    nursery.start_soon(async_func, name=name)
        self._cancel_scope = None

    def _rc_run(self):
        import trio

        trio.run(self.run_async, restrict_keyboard_interrupt_to_checkpoints=False)

    def _rc_stop(self):
        # Cancel the main task and all its child tasks.
        if self._cancel_scope is not None:
            self._cancel_scope.cancel()

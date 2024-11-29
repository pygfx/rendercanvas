"""
Implements a trio event loop for backends that don't have an event loop by themselves, like glfw.
"""

__all__ = ["TrioLoop", "loop"]


from .base import BaseLoop


class TrioLoop(BaseLoop):
    def __init__(self):
        super().__init__()
        import trio

        self._pending_tasks = []
        self._cancel_scope = None
        self._send_channel, self._receive_channel = trio.open_memory_channel(99)

    async def run_async(self):
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

    def _rc_add_task(self, async_func, name):
        self._send_channel.send_nowait((async_func, name))
        return None

    def _rc_call_later(self, delay, callback):
        raise NotImplementedError()  # we implement _rc_add_task() instead


loop = TrioLoop()

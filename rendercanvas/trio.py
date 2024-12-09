"""
Implements a trio event-loop for backends that don't have an event-loop by themselves, like glfw.
Also supports a trio-friendly way to run or wait for the loop using ``run_async()``.
"""

__all__ = ["TrioLoop", "loop"]

from .base import BaseLoop

import trio
import sniffio


class TrioLoop(BaseLoop):
    def _rc_init(self):
        import trio

        self._cancel_scope = None
        self._send_channel, self._receive_channel = trio.open_memory_channel(99)

    def _rc_run(self):
        trio.run(self._rc_run_async, restrict_keyboard_interrupt_to_checkpoints=False)

    async def _rc_run_async(self):
        # Protect against usage of wrong loop object
        libname = sniffio.current_async_library()
        if libname != "trio":
            raise TypeError(f"Attempt to run TrioLoop with {libname}.")

        with trio.CancelScope() as self._cancel_scope:
            async with trio.open_nursery() as nursery:
                while True:
                    async_func, name = await self._receive_channel.receive()
                    nursery.start_soon(async_func, name=name)
        self._cancel_scope = None

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

"""
Implements an asyncio event-loop for backends that don't have an event-loop by themselves, like glfw.
Also supports a asyncio-friendly way to run or wait for the loop using ``run_async()``.
"""

__all__ = ["AsyncioLoop", "loop"]

from .base import BaseLoop

import sniffio


class AsyncioLoop(BaseLoop):
    def __init__(self):
        super().__init__()
        # Initialize, but don't even import asyncio yet
        self.__tasks = set()
        self.__pending_tasks = []
        self._interactive_loop = None
        self._run_loop = None
        self._stop_event = None

    def _rc_init(self):
        # This gets called when the first canvas is created (possibly after having run and stopped before).
        import asyncio

        try:
            self._interactive_loop = asyncio.get_running_loop()
            self._stop_event = asyncio.Event()
            self._mark_as_interactive()  # prevents _rc_run from being called
        except Exception:
            self._interactive_loop = None

    def _rc_run(self):
        import asyncio

        if self._interactive_loop is not None:
            return

        asyncio.run(self._rc_run_async())

    async def _rc_run_async(self):
        import asyncio

        # Protect agsinst usage of wrong loop object
        libname = sniffio.current_async_library()
        if libname != "asyncio":
            raise TypeError(f"Attempt to run AsyncioLoop with {libname}.")

        # Assume we have a running loop
        self._run_loop = asyncio.get_running_loop()

        # If we had a running loop when we initialized, it must be the same,
        # because we submitted our tasks to it :)
        if self._interactive_loop and self._interactive_loop is not self._run_loop:
            # I cannot see a valid use-case for this situation. If you do have a use-case, please create an issue
            # at https://github.com/pygfx/rendercanvas/issues, and we can maybe fix it.
            raise RuntimeError(
                "Attempt to run AsyncioLoop with a different asyncio-loop than the initialized loop."
            )

        # Create tasks if necessay
        while self.__pending_tasks:
            self._rc_add_task(*self.__pending_tasks.pop(-1))

        # Wait for loop to finish
        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        await self._stop_event.wait()

    def _rc_stop(self):
        # Clean up our tasks
        while self.__tasks:
            task = self.__tasks.pop()
            task.cancel()  # is a no-op if the task is no longer running
        # Signal that we stopped
        self._stop_event.set()
        self._stop_event = None
        self._run_loop = None
        # Note how we don't explicitly stop a loop, not the interactive loop, nor the running loop

    def _rc_add_task(self, func, name):
        loop = self._interactive_loop or self._run_loop
        if loop is None:
            self.__pending_tasks.append((func, name))
        else:
            task = loop.create_task(func(), name=name)
            self.__tasks.add(task)
            task.add_done_callback(self.__tasks.discard)

    def _rc_call_later(self, *args):
        raise NotImplementedError()  # we implement _rc_add_task instead


loop = AsyncioLoop()

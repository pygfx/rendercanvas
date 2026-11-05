"""
Implements an asyncio event-loop for backends that don't have an event-loop by themselves, like glfw.
Also supports a asyncio-friendly way to run or wait for the loop using ``run_async()``.
"""

__all__ = ["AsyncioLoop", "loop"]

from .base import BaseLoop
from .core.coreutils import IS_PYODIDE
from .utils.asyncs import detect_current_async_lib


class AsyncioLoop(BaseLoop):
    _use_call_later_via_thread = not bool(IS_PYODIDE)

    def __init__(self):
        super().__init__()
        # Initialize, but don't even import asyncio yet
        self.__pending_call_soons = []
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

        # Protect against usage of wrong loop object
        libname = detect_current_async_lib()
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

        # Call soon if necessary
        while self.__pending_call_soons:
            self._rc_call_soon_threadsafe(self.__pending_call_soons.pop(0))

        # Only do one cycle of processing tasks if there are no canvases.
        if not self.get_canvases():
            self._run_loop.call_soon(self.stop)

        # Wait for loop to finish
        if self._stop_event is None:
            self._stop_event = asyncio.Event()
        await self._stop_event.wait()

    def _rc_stop(self):
        # Signal that we stopped
        if self._stop_event is not None:
            self._stop_event.set()
        self._stop_event = None
        self._run_loop = None
        # Note how we don't explicitly stop a loop, not the interactive loop, nor the running loop

    def _rc_call_soon(self, callback):
        loop = self._interactive_loop or self._run_loop
        if loop is None:
            self.__pending_call_soons.append(callback)
        else:
            loop.call_soon(callback)

    def _rc_call_soon_threadsafe(self, callback):
        loop = self._interactive_loop or self._run_loop
        if loop is None:
            self.__pending_call_soons.append(callback)
        else:
            loop.call_soon_threadsafe(callback)

    def _rc_call_later(self, delay, callback):
        if self._use_call_later_via_thread:
            # The default version has more accurate timing on Windows.
            super()._rc_call_later(delay, callback)
        else:
            # For Pyodide we cannot use the default implementation, because it uses threading.
            loop = self._interactive_loop or self._run_loop
            if loop is None:
                self.__pending_call_soons.append(callback)
            else:
                loop.call_later(delay, callback)


loop = AsyncioLoop()

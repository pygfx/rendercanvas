"""
The base loop implementation.
"""

from __future__ import annotations

import signal
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING

from ._coreutils import logger, log_exception
from .utils.asyncs import sleep
from .utils import asyncadapter

if TYPE_CHECKING:
    from typing import Any, Callable, Coroutine, List
    from base import BaseRenderCanvas

    CallbackFunction = Callable[[], Any]


HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)


class BaseLoop:
    """The base class for an event-loop object.

    Canvas backends can implement their own loop subclass (like qt and wx do), but a
    canvas backend can also rely on one of muliple loop implementations (like glfw
    running on asyncio or trio).

    The lifecycle states of a loop are:

    * off (0): the initial state, the subclass should probably not even import dependencies yet.
    * ready (1): the first canvas is created, ``_rc_init()`` is called to get the loop ready for running.
    * active (2): the loop is active, but not running via our entrypoints.
    * active (3): the loop is inter-active in e.g. an IDE.
    * running (4): the loop is running via ``_rc_run()`` or ``_rc_run_async()``.

    Notes:

    * The loop goes back to the "off" state after all canvases are closed.
    * Stopping the loop (via ``.stop()``) closes the canvases, which will then stop the loop.
    * From there it can go back to the ready state (which would call ``_rc_init()`` again).
    * In backends like Qt, the native loop can be started without us knowing: state "active".
    * In interactive settings like an IDE that runs an syncio or Qt loop, the
      loop can become "active" as soon as the first canvas is created.

    """

    def __init__(self):
        self.__tasks = set()
        self.__canvas_groups = set()
        self.__should_stop = 0
        self.__state = (
            0  # 0: off, 1: ready, 2: detected-active, 3: inter-active, 4: running
        )

    def __repr__(self):
        full_class_name = f"{self.__class__.__module__}.{self.__class__.__name__}"
        state = self.__state
        state_str = ["off", "ready", "active", "active", "running"][state]
        return f"<{full_class_name} '{state_str}' ({state}) at {hex(id(self))}>"

    def _mark_as_interactive(self):
        """For subclasses to set active from ``_rc_init()``"""
        if self.__state in (1, 2):
            self.__state = 3

    def _register_canvas_group(self, canvas_group):
        # A CanvasGroup will call this every time that a new canvas is created for this loop.
        # So now is also a good time to initialize.
        if self.__state == 0:
            self.__state = 1
            self._rc_init()
            self.add_task(self._loop_task, name="loop-task")
        self.__canvas_groups.add(canvas_group)

    def _unregister_canvas_group(self, canvas_group):
        # A CanvasGroup will call this when it selects a different loop.
        self.__canvas_groups.discard(canvas_group)

    def get_canvases(self) -> List[BaseRenderCanvas]:
        """Get a list of currently active (not-closed) canvases."""
        canvases = []
        for canvas_group in self.__canvas_groups:
            canvases += canvas_group.get_canvases()
        return canvases

    async def _loop_task(self):
        # This task has multiple purposes:
        #
        # * Detect closed windows. Relying on the backend alone is tricky, since the
        #   loop usually stops when the last window is closed, so the close event may
        #   not be fired.
        # * Keep the GUI going even when the canvas loop is on pause e.g. because its
        #   minimized (applies to backends that implement _rc_gui_poll).

        # Detect active loop
        self.__state = max(self.__state, 2)

        # Keep track of event emitter objects
        event_emitters = {id(c): c._events for c in self.get_canvases()}

        try:
            while True:
                await sleep(0.1)

                # Get list of canvases, beware to delete the list when we're done with it!
                canvases = self.get_canvases()

                # Send close event for closed canvases
                new_event_emitters = {id(c): c._events for c in canvases}
                closed_canvas_ids = set(event_emitters) - set(new_event_emitters)
                for canvas_id in closed_canvas_ids:
                    events = event_emitters[canvas_id]
                    events.close()

                # Keep canvases alive
                for canvas in canvases:
                    canvas._rc_gui_poll()
                    del canvas

                canvas_count = len(canvases)
                del canvases

                # Should we stop?

                if canvas_count == 0:
                    # Stop when there are no more canvases
                    break
                elif self.__should_stop >= 2:
                    # Force a stop without waiting for the canvases to close.
                    # We could call event.close() for the remaining canvases, but technically they have not closed.
                    # Since this case is considered a failure, better be honest than consistent, I think.
                    break
                elif self.__should_stop:
                    # Close all remaining canvases. Loop will stop in a next iteration.
                    # We store a flag on the canvas, that we only use here.
                    for canvas in self.get_canvases():
                        try:
                            closed_by_loop = canvas._rc_closed_by_loop  # type: ignore
                        except AttributeError:
                            closed_by_loop = False
                        if not closed_by_loop:
                            canvas._rc_closed_by_loop = True  # type: ignore
                            canvas.close()
                        del canvas

        finally:
            self.__stop()

    def add_task(
        self,
        async_func: Callable[[], Coroutine],
        *args: Any,
        name: str = "unnamed",
    ) -> None:
        """Run an async function in the event-loop.

        All tasks are stopped when the loop stops.
        See :ref:`async` for the limitations of async code in rendercanvas.
        """
        if not (callable(async_func) and iscoroutinefunction(async_func)):
            raise TypeError("add_task() expects an async function.")

        async def wrapper():
            with log_exception(f"Error in {name} task:"):
                await async_func(*args)

        self._rc_add_task(wrapper, name)

    def call_soon(self, callback: CallbackFunction, *args: Any) -> None:
        """Arrange for a callback to be called as soon as possible.

        The callback will be called in the next iteration of the event-loop,
        but other pending events/callbacks may be handled first. Returns None.
        """
        if not callable(callback):
            raise TypeError("call_soon() expects a callable.")
        elif iscoroutinefunction(callback):
            raise TypeError("call_soon() expects a normal callable, not an async one.")

        async def wrapper():
            with log_exception("Callback error:"):
                callback(*args)

        self._rc_add_task(wrapper, "call_soon")

    def call_later(self, delay: float, callback: CallbackFunction, *args: Any) -> None:
        """Arrange for a callback to be called after the given delay (in seconds)."""
        if delay <= 0:
            return self.call_soon(callback, *args)

        if not callable(callback):
            raise TypeError("call_later() expects a callable.")
        elif iscoroutinefunction(callback):
            raise TypeError("call_later() expects a normal callable, not an async one.")

        async def wrapper():
            with log_exception("Callback error:"):
                await sleep(delay)
                callback(*args)

        self._rc_add_task(wrapper, "call_later")

    def run(self) -> None:
        """Enter the main loop.

        This provides a generic API to start the loop. When building an application (e.g. with Qt)
        its fine to start the loop in the normal way.

        This call usually blocks, but it can also return immediately, e.g. when there are no
        canvases, or when the loop is already active (e.g. interactve via IDE).
        """

        # Can we enter the loop?
        if self.__state == 0:
            # Euhm, I guess we can run it one iteration, just make sure our loop-task is running!
            self._register_canvas_group(0)
            self.__canvas_groups.discard(0)
        if self.__state == 1:
            # Yes we can
            pass
        elif self.__state == 2:
            # We look active, but have not been marked interactive
            pass
        elif self.__state == 3:
            # No, already marked active (interactive mode)
            return
        else:
            # No, what are you doing??
            raise RuntimeError(f"loop.run() is not reentrant ({self.__state}).")

        # Register interrupt handler
        prev_sig_handlers = self.__setup_interrupt()

        # Run. We could be in this loop for a long time. Or we can exit immediately if
        # the backend already has an (interactive) event loop and did not call _mark_as_interactive().
        self.__state = 3
        try:
            self._rc_run()
        finally:
            self.__state = min(self.__state, 1)
            for sig, cb in prev_sig_handlers.items():
                signal.signal(sig, cb)

    async def run_async(self) -> None:
        """ "Alternative to ``run()``, to enter the mainloop from a running async framework.

        Only supported by the asyncio and trio loops.
        """

        # Can we enter the loop?
        if self.__state == 0:
            # Euhm, I guess we can run it one iteration, just make sure our loop-task is running!
            self._register_canvas_group(0)
            self.__canvas_groups.discard(0)
        if self.__state == 1:
            # Yes we can
            pass
        else:
            raise RuntimeError(
                f"loop.run_async() can only be awaited once ({self.__state})."
            )

        await self._rc_run_async()

    def stop(self) -> None:
        """Close all windows and stop the currently running event-loop.

        If the loop is active but not running via our ``run()`` method, the loop
        moves back to its off-state, but the underlying loop is not stopped.
        """
        # Only take action when we're inside the run() method
        self.__should_stop += 1
        if self.__should_stop >= 4:
            # If for some reason the tick method is no longer being called, but the loop is still running, we can still stop it by spamming stop() :)
            self.__stop()

    def __stop(self):
        """Move to the off-state."""
        # If we used the async adapter, cancel any tasks
        while self.__tasks:
            task = self.__tasks.pop()
            with log_exception("task cancel:"):
                task.cancel()
        # Turn off
        self.__state = 0
        self.__should_stop = 0
        self._rc_stop()

    def __setup_interrupt(self):
        """Setup the interrupt handlers."""

        def on_interrupt(sig, _frame):
            logger.warning(f"Received signal {signal.strsignal(sig)}")
            self.stop()

        prev_handlers = {}

        for sig in HANDLED_SIGNALS:
            prev_handler = signal.getsignal(sig)
            if prev_handler in (None, signal.SIG_IGN, signal.SIG_DFL):
                # Only register if the old handler for SIGINT was not None,
                # which means that a non-python handler was installed, i.e. in
                # Julia, and not SIG_IGN which means we should ignore the interrupts.
                pass
            else:
                # Setting the signal can raise ValueError if this is not the main thread/interpreter
                try:
                    prev_handlers[sig] = signal.signal(signal.SIGINT, on_interrupt)
                except ValueError:
                    break
        return prev_handlers

    def _rc_init(self):
        """Put the loop in a ready state.

        Called when the first canvas is created to run in this loop. This is when we
        know pretty sure that this loop is going to be used, so time to start the
        engines. Note that in interactive settings, this method can be called again, after the
        loop has stopped, to restart it.

        * Import any dependencies.
        * If this loop supports some kind of interactive mode, activate it!
        * Optionally call ``_mark_as_interactive()``.
        * Return None.
        """
        pass

    def _rc_run_async(self):
        """Run async."""
        raise NotImplementedError()

    def _rc_run(self):
        """Start running the event-loop.

        * Start the event-loop.
        * The loop object must also work when the native loop is started
          in the GUI-native way (i.e. this method may not be called).
        * If the backend is in interactive mode (i.e. there already is
          an active native loop) this may return directly.
        """
        raise NotImplementedError()

    def _rc_stop(self):
        """Clean up the loop, going to the off-state.

        * Cancel any remaining tasks.
        * Stop the running event-loop, if applicable.
        * Be ready for another call to ``_rc_init()`` in case the loop is reused.
        * Return None.
        """
        raise NotImplementedError()

    def _rc_add_task(self, async_func, name):
        """Add an async task to the running loop.

        This method is optional. A subclass must either implement ``_rc_add_task`` or ``_rc_call_later``.

        * Schedule running the task defined by the given co-routine function.
        * The name is for debugging purposes only.
        * The subclass is responsible for cancelling remaining tasks in _rc_stop.
        * Return None.
        """
        task = asyncadapter.Task(self._rc_call_later, async_func(), name)
        self.__tasks.add(task)
        task.add_done_callback(self.__tasks.discard)

    def _rc_call_later(self, delay, callback):
        """Method to call a callback in delay number of seconds.

        This method is optional. A subclass must either implement ``_rc_add_task`` or ``_rc_call_later``.

        * If you implememt this, make ``_rc_add_task()`` call ``super()._rc_add_task()``.
        * If delay is zero, this should behave like "call_soon".
        * No need to catch errors from the callback; that's dealt with internally.
        * Return None.
        """
        raise NotImplementedError()

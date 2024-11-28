"""
The base loop implementation.
"""

import signal

from ._coreutils import logger, log_exception
from ._scheduler import Scheduler
from ._async_sniffs import sleep
from asyncio import iscoroutinefunction
from ._async_adapter import Task as AsyncAdapterTask

# Note: technically, we could have a global loop proxy object that defers to any of the other loops.
# That would e.g. allow using glfw with qt together. Probably a too weird use-case for the added complexity.


HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)


class LoopProxy:
    """Proxy loop object that canvases can use to register themselves before a loop is selected."""

    def __init__(self):
        self._current_loop = None
        self._pending_calls = []  # (method_name, args) elements

    def set_current_loop(self, loop):
        if loop is self._current_loop:
            return
        if self._current_loop:
            raise RuntimeError(
                "Cannot set the current loop while another loop is active."
            )
        self._current_loop = loop
        while self._pending_calls:
            method_name, args = self._pending_calls.pop(-1)
            func = getattr(self._current_loop, method_name)
            func(*args)

    def unset_current_loop(self, loop):
        if loop is self._current_loop:
            self._current_loop = None
        else:
            raise RuntimeError("Cannot unset loop that is not active.")

    # proxy methods

    def add_scheduler(self, *args):
        if self._current_loop:
            self._current_loop.add_scheduler(*args)
        else:
            self._pending_calls.append(("add_scheduler", args))

    def add_task(self, *args):
        if self._current_loop:
            self._current_loop.add_task(*args)
        else:
            self._pending_calls.append(("add_task", args))

    def call_soon(self, *args):
        if self._current_loop:
            self._current_loop.call_soon(*args)
        else:
            self._pending_calls.append(("call_soon", args))


global_loop_proxy = LoopProxy()


class BaseLoop:
    """The base class for an event-loop object.

    Each backend provides its own loop subclass, so that rendercanvas can run cleanly in the backend's event loop.
    """

    _loop_proxy = global_loop_proxy

    def __init__(self):
        self.__tasks = []
        self._schedulers = []
        self._is_inside_run = False
        self._should_stop = 0
        self.__created_loop_task = False

    def add_scheduler(self, scheduler):
        assert isinstance(scheduler, Scheduler)
        self._schedulers.append(scheduler)

    def get_canvases(self):
        """Get a list of currently active (not-closed) canvases."""
        canvases = []
        schedulers = []

        for scheduler in self._schedulers:
            canvas = scheduler.get_canvas()
            if canvas is not None:
                canvases.append(canvas)
                schedulers.append(scheduler)

        # Forget schedulers that no longer have a live canvas
        self._schedulers = schedulers

        return canvases

    async def _loop_task(self):
        # This task has multiple purposes:
        #
        # * Detect closed windows. Relying on the backend alone is tricky, since the
        #   loop usually stops when the last window is closed, so the close event may
        #   not be fired.
        # * Keep the GUI going even when the canvas loop is on pause e.g. because its
        #   minimized (applies to backends that implement _rc_gui_poll).

        while True:
            await sleep(0.1)

            # Clean internal schedulers list, and keep the loop alive
            for canvas in self.get_canvases():
                canvas._rc_gui_poll()
                del canvas

            # Our loop can still tick, even if the loop is not started via our run() method.
            # If this is the case, we don't run the close/stop logic
            if not self._is_inside_run:
                continue

            # Should we stop?
            if not self._schedulers:
                # Stop when there are no more canvases
                break
            elif self._should_stop >= 2:
                # force a stop without waiting for the canvases to close
                break
            elif self._should_stop:
                # Close all remaining canvases. Loop will stop in a next iteration.
                for canvas in self.get_canvases():
                    if not getattr(canvas, "_rc_closed_by_loop", False):
                        canvas._rc_closed_by_loop = True
                        canvas._rc_close()
                        del canvas

        self._stop()

    def add_task(self, async_func, *args, name="unnamed"):
        if not (callable(async_func) and iscoroutinefunction(async_func)):
            raise TypeError("call_soon() expects an async function.")

        async def wrapper():
            with log_exception(f"Error in {name} task:"):
                await async_func(*args)

        self._rc_add_task(wrapper, name)

    def call_soon(self, callback, *args):
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
        # self._rc_call_soon(callback, *args)

    def call_later(self, delay, callback, *args):
        """Arrange for a callback to be called after the given delay (in seconds).

        Returns a timer object (in one-shot mode) that can be used to
        stop the time (i.e. cancel the callback being called), and/or
        to restart the timer.

        It's not necessary to hold a reference to the timer object; a
        ref is held automatically, and discarded when the timer ends or stops.
        """
        raise NotImplementedError()

    def call_repeated(self, interval, callback, *args):
        """Arrange for a callback to be called repeatedly.

        Returns a timer object (in multi-shot mode) that can be used for
        further control.

        It's not necessary to hold a reference to the timer object; a
        ref is held automatically, and discarded when the timer is
        stopped.
        """
        raise NotImplementedError()

    def run(self):
        """Enter the main loop.

        This provides a generic API to start the loop. When building an application (e.g. with Qt)
        its fine to start the loop in the normal way.
        """
        # Note that when the loop is started via this method, we always stop
        # when the last canvas is closed. Keeping the loop alive is a use-case
        # for interactive sessions, where the loop is already running, or started
        # "behind our back". So we don't need to accomodate for this.

        if self._loop_proxy is not None:
            self._loop_proxy.set_current_loop(self)

        # Cannot run if already running
        if self._is_inside_run:
            raise RuntimeError("loop.run() is not reentrant.")

        # Make sure that the internal timer is running, even if no canvases.
        if not self.__created_loop_task:
            self.__created_loop_task = True
            self.add_task(self._loop_task, name="loop")

        # Register interrupt handler
        prev_sig_handlers = self.__setup_interrupt()

        # Run. We could be in this loop for a long time. Or we can exit
        # immediately if the backend already has an (interactive) event
        # loop. In the latter case, note how we restore the sigint
        # handler again, so we don't interfere with that loop.
        self._is_inside_run = True
        try:
            self._rc_run()
        finally:
            self._is_inside_run = False
            for sig, cb in prev_sig_handlers.items():
                signal.signal(sig, cb)

    async def run_async(self):
        """ "Alternative to ``run()``, to enter the mainloop from a running async framework."""
        if self._loop_proxy is not None:
            self._loop_proxy.set_current_loop(self)
        await self._rc_run_async()

    def stop(self):
        """Close all windows and stop the currently running event loop.

        This only has effect when the event loop is currently running via ``.run()``.
        I.e. not when a Qt app is started with ``app.exec()``, or when Qt or asyncio
        is running interactively in your IDE.
        """
        # Only take action when we're inside the run() method
        if self._is_inside_run:
            self._should_stop += 1
            if self._should_stop >= 4:
                # If for some reason the tick method is no longer being called, but the loop is still running, we can still stop it by spamming stop() :)
                self._stop()

    def _stop(self):
        if self._loop_proxy is not None:
            with log_exception("unset loop:"):
                self._loop_proxy.unset_current_loop(self)
        for task in self.__tasks:
            with log_exception("task cancel:"):
                task.cancel()
        self.__tasks = []
        self._rc_stop()

    def __setup_interrupt(self):
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

    def _rc_run(self):
        """Start running the event-loop.

        * Start the event loop.
        * The loop object must also work when the native loop is started
          in the GUI-native way (i.e. this method may not be called).
        * If the backend is in interactive mode (i.e. there already is
          an active native loop) this may return directly.
        """
        raise NotImplementedError()

    async def _rc_run_async(self):
        """Enter the mainloop by awaiting this co-routine.

        Should only be implemented by loop-backends that are async (asyncio, trio).
        Other backends can ignore this.
        """
        raise NotImplementedError()

    def _rc_stop(self):
        """Stop the event loop.

        * Stop the running event loop.
        * Cancel any remaining tasks.
        * todo: is the below still (supposed to be) true?
        * This will only be called when the process is inside _rc_run().
          I.e. not for interactive mode.
        """
        raise NotImplementedError()

    def _rc_add_task(self, async_func, name):
        """Add an async task to the running loop.

        This method is optional. A backend must either implement ``_rc_add_task``
        or implement both ``_rc_call_soon()`` and ``_rc_call_at``.

        * Schedule running the task defined by the given co-routine function.
        * The name is for debugging purposes only.
        * The backend is responsible for cancelling remaining tasks in _rc_stop.
        """
        task = AsyncAdapterTask(self, async_func(), name)
        self.__tasks.append(task)
        task.add_done_callback(self.__tasks.remove)

    def _rc_call_soon(self, callback):
        """Method to call a callback in the next iteraction of the event-loop.

        This method must only be implemented if ``_rc_add_task()`` is not.
        """

    def _rc_call_at(self, when, callback):
        """Method to call a callback at a specific time.

        This method must only be implemented if ``_rc_add_task()`` is not.
        """

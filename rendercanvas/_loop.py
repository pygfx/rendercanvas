"""
The base loop implementation.
"""

from __future__ import annotations

import signal
import weakref
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING

from ._coreutils import logger, log_exception, call_later_from_thread
from .utils.asyncs import sleep
from .utils import asyncadapter

if TYPE_CHECKING:
    from typing import Any, Callable, Coroutine
    from base import BaseRenderCanvas

    CallbackFunction = Callable[[], Any]


HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)


class BaseLoop:
    """The base class for an event-loop object.

    Canvas backends can implement their own loop subclass (like qt and wx do), but a
    canvas backend can also rely on one of multiple loop implementations (like glfw
    running on asyncio or trio).

    The lifecycle states of a loop are:

    * off (0): the initial state, the subclass should probably not even import dependencies yet.
    * ready (1): the first canvas is created, ``_rc_init()`` is called to get the loop ready for running.
    * active (2): the loop is active (we detect it because our task is running), but we don't know how.
    * active (3): the loop is inter-active in e.g. an IDE, reported by the backend.
    * running (4): the loop is running via ``_rc_run()`` or ``_rc_run_async()``.

    Notes:

    * The loop goes back to the "off" state once all canvases are closed.
    * Stopping the loop (via ``.stop()``) closes the canvases, which will then stop the loop.
    * From there it can go back to the ready state (which would call ``_rc_init()`` again).
    * In backends like Qt, the native loop can be started without us knowing: state "active".
    * In interactive settings like an IDE that runs an asyncio or Qt loop, the
      loop can become "active" as soon as the first canvas is created.

    The lifecycle of this loop does not necessarily co-inside with the native loop's cycle:

    * The rendercanvas loop can be in the 'off' state while the native loop is running.
    * When we stop the loop, the native loop likely runs slightly longer.
    * When the loop is interactive (asyncio or Qt) the native loop keeps running when rendercanvas' loop stops.
    * For async loops (asyncio or trio), the native loop may run before and after this loop.
    * On Qt, we detect the app's aboutToQuit to stop this loop.
    * On wx, we detect all windows closed to stop this loop.

    """

    def __init__(self):
        self.__tasks = set()
        self.__canvas_groups = set()
        self.__should_stop = 0
        # 0: off, 1: ready, 2: detected-active, 3: inter-active, 4: running
        self.__state = 0
        self.__is_initialized = False
        self._asyncgens = weakref.WeakSet()
        # self._setup_debug_thread()

    def _setup_debug_thread(self):
        # Super-useful to track the loop's lifetime while running various examples / use-cases.

        import threading, time  # noqa

        def thread():
            state = self.__state
            print(f"loop state: {state}")
            while True:
                time.sleep(0.01)
                cur_state = self.__state
                if cur_state != state:
                    state = cur_state
                    print(f"loop state: {state}")
                    if state == 0:
                        print("bye")

        self._debug_thread = threading.Thread(target=thread)
        self._debug_thread.start()

    def __repr__(self):
        full_class_name = f"{self.__class__.__module__}.{self.__class__.__name__}"
        state = self.__state
        statemap = {0: "off", 1: "ready", 2: "active", 3: "active", 4: "running"}
        state_str = statemap.get(state, str(state))
        return f"<{full_class_name} '{state_str}' ({state}) at {hex(id(self))}>"

    def _mark_as_interactive(self):
        # For subclasses to set active from ``_rc_init()`` If the loop is
        # interactive, run() becomes a no-op. The stop() will still close all
        # canvases, but the backend loop should keep running.
        if self.__state in (1, 2):
            self.__state = 3

    def _register_canvas_group(self, canvas_group):
        # A CanvasGroup will call this every time that a new canvas is created for this loop.
        # So now is also a good time to initialize.
        self._ensure_initialized()
        self.__canvas_groups.add(canvas_group)

    def _unregister_canvas_group(self, canvas_group):
        # A CanvasGroup will call this when it selects a different loop.
        self.__canvas_groups.discard(canvas_group)

    def get_canvases(self, *, close_closed=False) -> list[BaseRenderCanvas]:
        """Get a list of currently active (not-closed) canvases."""
        canvases = []
        for canvas_group in self.__canvas_groups:
            canvases += canvas_group.get_canvases(close_closed=close_closed)
        return canvases

    def _ensure_initialized(self):
        """Make sure that the loop is ready to run."""
        if self.__is_initialized:
            return

        if self.__state == 0:
            self.__state = 1

        async def wrapper():
            try:
                with log_exception("Error in loop-task:"):
                    await self._loop_task()
            finally:
                # We get here when the task is finished or cancelled.
                self.__is_initialized = False

        self.__is_initialized = True
        self._rc_init()
        self._rc_add_task(wrapper, "loop-task")

    async def _loop_task(self):
        # This task has multiple purposes:
        #
        # * Detect when the the loop starts running. When this code runs, it
        #   means something is running the task.
        # * Detect closed windows while the loop is running. This is nice,
        #   because it means backends only have to mark the canvas as closed,
        #   and the base canvas takes care that .close() is called and the close
        #   event is emitted.
        # * Stop the loop when there are no more canvases. Note that the loop
        #   may also be stopped from the outside, in which case *this* task is
        #   cancelled along with the other tasks.
        # * Detect when the loop stops running, in case the native loop stops in
        #   a friendly way, cancelling tasks, including *this* task.
        # * Keep the GUI going even when the canvas loop is on pause e.g.
        #   because its minimized (applies to backends that implement
        #   _rc_gui_poll).

        # The loop has started!
        self.__start()

        try:
            while True:
                await sleep(0.1)

                # Note that this triggers .close() on closed canvases, for proper cleanup and sending close event.
                canvases = self.get_canvases(close_closed=True)

                # Keep canvases alive
                for canvas in canvases:
                    canvas._rc_gui_poll()
                    del canvas

                # Break?
                canvas_count = len(canvases)
                del canvases
                if not canvas_count:
                    break

        finally:
            # We get here when we break the while-loop, but also when the task
            # is cancelled (e.g. because the asyncio loop stops). In both cases
            # we call stop from the *end* of the task, which is important since
            # __stop() cancels all tasks, but cannot cancel the task that it is
            # currently in.
            self.stop(force=True)

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

        self._ensure_initialized()

        async def wrapper():
            with log_exception(f"Error in {name} task:"):
                await async_func(*args)

        self._rc_add_task(wrapper, name)

    def call_soon(self, callback: CallbackFunction, *args: Any) -> None:
        """Arrange for a callback to be called as soon as possible.

        The callback will be called in the next iteration of the event-loop, but
        other pending events/callbacks may be handled first. Returns None.

        Not thread-safe; use ``call_soon_threadsafe()`` for scheduling callbacks
        from another thread.
        """
        if not callable(callback):
            raise TypeError("call_soon() expects a callable.")
        elif iscoroutinefunction(callback):
            raise TypeError("call_soon() expects a normal callable, not an async one.")

        async def wrapper():
            with log_exception("Callback error:"):
                callback(*args)

        self._rc_add_task(wrapper, "call_soon")

    def call_soon_threadsafe(self, callback: CallbackFunction, *args: Any) -> None:
        """A thread-safe variant of ``call_soon()``."""

        if not callable(callback):
            raise TypeError("call_soon_threadsafe() expects a callable.")
        elif iscoroutinefunction(callback):
            raise TypeError(
                "call_soon_threadsafe() expects a normal callable, not an async one."
            )

        def wrapper():
            with log_exception("Callback error:"):
                callback(*args)

        self._rc_call_soon_threadsafe(wrapper)

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
        canvases, or when the loop is already active (e.g. interactive via IDE).
        """

        # Can we enter the loop?
        if self.__state == 0:
            # We're in the off state, no canvases. Allow running one iteration.
            pass
        elif self.__state == 1:
            # Yes we can.
            pass
        elif self.__state == 2:
            # The loop is running, but not sure how. Maybe natively, or maybe this is the offscreen's stub loop. Allow.
            pass
        elif self.__state == 3:
            # Already marked active (interactive mode). For code compat, silent return!
            return
        else:
            # Already running via this method. Disallow re-entrance!
            raise RuntimeError(f"loop is already running ({self.__state}).")

        self._ensure_initialized()

        # Register interrupt handler
        prev_sig_handlers = self.__setup_interrupt()

        # Run. We could be in this loop for a long time. Or we can exit immediately if
        # the backend already has an (interactive) event loop and did not call _mark_as_interactive().
        self.__state = 4
        try:
            self._rc_run()
        finally:
            # Lower state to not 4, but also not 0 because we may still be running
            self.__state = min(self.__state, 2)
            for sig, cb in prev_sig_handlers.items():
                signal.signal(sig, cb)

    async def run_async(self) -> None:
        """ "Alternative to ``run()``, to enter the mainloop from a running async framework.

        Only supported by the asyncio and trio loops.
        """

        # Can we enter the loop?
        if self.__state >= 2:
            raise RuntimeError(
                f"loop.run_async() can only be awaited once ({self.__state})."
            )

        self._ensure_initialized()
        await self._rc_run_async()

    def stop(self, *, force=False) -> None:
        """Close all windows and stop the currently running event-loop.

        If the loop is active but not running via our ``run()`` method, the loop
        moves back to its off-state, but the underlying loop is not stopped.

        Normally, the windows are closed and the underlying event loop is given
        time to clean up and actually destroy the window. If ``force`` is set,
        the loop stops immediately. This can be an effective way to stop the
        loop when the native event loop has stopped.
        """

        if self.__state == 0:
            return

        # Only take action when we're inside the run() method
        self.__should_stop += 2 if force else 1

        # Close all canvases
        canvases = self.get_canvases(close_closed=True)
        for canvas in canvases:
            try:
                closed_by_loop = canvas._rc_closed_by_loop  # type: ignore
            except AttributeError:
                closed_by_loop = False
            if not closed_by_loop:
                canvas._rc_closed_by_loop = True  # type: ignore
                canvas.close()
            del canvas

        # Do a real stop?
        if len(canvases) == 0 or self.__should_stop >= 2:
            self.__stop()

    def __start(self):
        """Move to running state."""
        self.__state = max(self.__state, 2)

        # def init(gen):
        #     print("init gen", gen)

        # def fin(gen):
        #     print("fin gen", gen)

        # print("in loop task", self._using_adapter)
        # import sys

        # old_agen_hooks = sys.get_asyncgen_hooks()
        # sys.set_asyncgen_hooks(init, fin)

    def __stop(self):
        """Move to the off-state."""

        # Note that in here, we must fully bring our loop to a stop.
        # We cannot rely on future loop cycles.

        # Set flags to off state
        self.__state = 0
        self.__should_stop = 0

        # sys.set_asyncgen_hooks(*old_agen_hooks)  -> move into __stop

        # If we used the async adapter, cancel any tasks. If we could assume
        # that the backend processes pending events before actually shutting
        # down, we could only call .cancel(), and leave the event-loop to do the
        # final .step() that will do the cancellation (i.e. running code in
        # finally blocks), but (I found) we cannot make that assumption, so we
        # do it ourselves.
        for task in list(self.__tasks):
            with log_exception("task cancel:"):
                task.cancel()
                if not task.running:  # not *this* task
                    task.step()

        # Note that backends that do not use the asyncadapter are responsible
        # for cancelling pending tasks.

        # Tell the backend to stop the loop. This usually means it will stop
        # soon, but not *now*; remember that we're currently in a task as well.
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
        * Make sure its ok if this is called a second time, after a run.
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

        True async loop-backends (like asyncio and trio) should implement this.
        When they do, ``_rc_call_later`` is not used.

        Other loop-backends can use the default implementation, which uses the
        ``asyncadapter`` which runs coroutines using ``_rc_call_later``.

        * If you implement this, make ``_rc_call_later()`` raise an exception.
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

        Backends that implement ``_rc_add_task`` should not implement this.
        Other backends can use the default implementation, which uses a
        scheduler thread and ``_rc_call_soon_threadsafe``. But they can also
        implement this using the loop-backend's own mechanics.

        * If you implement this, make ``_rc_add_task()`` call ``super()._rc_add_task()``.
        * Take into account that on Windows, timers are usually inaccurate.
        * If delay is zero, this should behave like "call_soon".
        * No need to catch errors from the callback; that's dealt with
          internally.
        * Return None.
        """
        call_later_from_thread(delay, self._rc_call_soon_threadsafe, callback)

    def _rc_call_soon_threadsafe(self, callback):
        """Method to schedule a callback in the loop's thread.

        Must be thread-safe; this may be called from a different thread.
        """
        raise NotImplementedError()

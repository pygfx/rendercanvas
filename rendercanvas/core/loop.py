"""
The base loop implementation.
"""

from __future__ import annotations

import signal
import sys
import weakref
from inspect import iscoroutinefunction
from typing import TYPE_CHECKING

from ..utils import asyncadapter
from .coreutils import (
    call_later_from_thread,
    close_agen,
    log_exception,
    log_this_exception,
    logger,
)
from .enums import LoopState

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

    The rendercanvas ``loop`` object is a proxy to a real event-loop. It abstracts away methods like ``run()``,
    ``call_later``, ``call_soon_threadsafe()``, and more.

    Canvas backends can implement their own loop subclass (like qt and wx do), but a
    canvas backend can also rely on one of multiple loop implementations (like glfw
    running on ``raw``, ``asyncio`` or ``trio``).

    In the majority of use-cases, users don't need to know much about the loop. It will typically
    run once. In more complex scenario's the section below explains the working of the loop in more detail.

    **Details about loop lifetime**

    The rendercanvas loop object is a proxy, which has to support a variety of backends.
    To realize this, it has the following lifetime model:

    * off:
        * Entered when the loop is instantiated, and when the loop has stopped.
        * This is the 'idle' state.
        * The backend probably has not even imported dependencies yet.
    * ready:
        * Entered when the first canvas is created that is associated with this loop, or when a task is added.
        * It is assumed that the loop will become active soon.
        * This is when ``_rc_init()`` is called to get the backend ready for running.
        * A co-routine is created that will detect when the loop starts running, so things can be initialized at the right moment.
    * running:
        * Entered when ``loop.run()`` is called.
        * The loop is now running.
        * Signal handlers and asyncgen hooks are installed if applicable.
    * interactive:
        * Entered in ``_rc_init()`` when the backend detects that the loop is interactive.
        * Example use-cases are a notebook or interactive IDE, usually via asyncio.
        * This means there is a persistent native loop already running, which rendercanvas makes use of.
    * active:
        * Entered when the backend-loop starts running, but not via the loop's ``run()`` method.
        * This is detected via the aforementioned co-routine.
        * Signal handlers and asyncgen hooks are installed if applicable.

    Notes related to starting and stopping:

    * The loop goes back to the "off" state once all canvases are closed.
    * Stopping the loop (via ``.stop()``) closes all canvases.
    * From there it can go back to the ready state (which would call ``_rc_init()`` again).
    * In backends like Qt, the native loop can be started without us knowing: state "active".
    * In interactive settings like an IDE that runs an asyncio or Qt loop, the
      loop becomes "interactive" as soon as the first canvas is created.
    * The rendercanvas loop can be in the 'off' state while the native loop is running (especially for the 'interactive' case).

    """

    def __init__(self):
        self.__tasks = set()  # only used by the async adapter
        self.__canvas_groups = set()
        self.__should_stop = 0
        self.__state = LoopState.off
        self.__is_initialized = False
        self.__interrupt_hook_data = None
        self.__callback_handles = set()
        self.__asyncgens = weakref.WeakSet()
        # self._setup_debug_thread()

    def _setup_debug_thread(self):
        # Super-useful to track the loop's lifetime while running various examples / use-cases.
        # In test_loop.py -> test_not_using_loop_debug_thread()  we make sure that it's not accidentally active by default.

        import threading, time  # noqa

        weakself = weakref.ref(self)

        def get_state():
            self = weakself()
            if self is not None:
                return self.__state

        def thread():
            prev_state = None
            while cur_state := get_state():
                if cur_state != prev_state:
                    prev_state = cur_state
                    print(f"loop state: {cur_state}")
                time.sleep(0.01)

        self._debug_thread = threading.Thread(target=thread, daemon=True)
        self._debug_thread.start()

    def __repr__(self):
        full_class_name = f"{self.__class__.__module__}.{self.__class__.__name__}"
        return f"<{full_class_name} '{self.__state}' at {hex(id(self))}>"

    def _mark_as_interactive(self):
        # For subclasses to set active from ``_rc_init()`` If the loop is
        # interactive, run() becomes a no-op. The stop() will still close all
        # canvases, but the backend loop should keep running.
        if self.__state in (LoopState.ready, LoopState.running):
            self.__state = LoopState.interactive

    def _register_canvas_group(self, canvas_group):
        # A CanvasGroup will call this every time that a new canvas is created for this loop.
        # So now is also a good time to initialize.
        self._ensure_initialized()
        self.__canvas_groups.add(canvas_group)

    def _unregister_canvas_group(self, canvas_group):
        # A CanvasGroup will call this when it selects a different loop.
        self.__canvas_groups.discard(canvas_group)

    def get_canvases(self) -> list[BaseRenderCanvas]:
        """Get a list of currently active (not-closed) canvases."""
        canvases = []
        for canvas_group in self.__canvas_groups:
            canvases += canvas_group.get_canvases()
        return canvases

    def _ensure_initialized(self):
        """Make sure that the loop is ready to run."""
        if self.__is_initialized:
            return

        if self.__state == LoopState.off:
            self.__state = LoopState.ready

        self.__is_initialized = True
        self._rc_init()

        self.call_soon(self._loop_start_detection_callback)

    def _loop_start_detection_callback(self):
        if self.__state != LoopState.off:
            self.__start()

    def add_task(
        self,
        async_func: Callable[[], Coroutine],
        *args: Any,
        name: str | None = None,
    ) -> None:
        """Run an async function in the event-loop.

        All tasks are stopped when the loop stops.
        See :ref:`async` for the limitations of async code in rendercanvas.
        """

        # Checks
        if not (callable(async_func) and iscoroutinefunction(async_func)):
            raise TypeError("add_task() expects an async function.")
        if name is None:
            name = async_func.__name__
        self._ensure_initialized()

        # Create and register task
        task = asyncadapter.Task(self._unchecked_call_later, async_func(), name)
        self.__tasks.add(task)
        task.add_done_callback(self.__tasks.discard)
        # TODO: use a different type of Handle, also to have the task name in the error messages?
        # TODO: return Task object?

    def _unregister_callback_handle(self, handle: CallbackHandle):
        """Let a CallbackHandle unregister itself when done or cancelled."""
        self.__callback_handles.discard(handle)

    def call_soon(self, callback: CallbackFunction, *args: Any) -> CallbackHandle:
        """Arrange for a callback to be called as soon as possible.

        The callback will be called in the next iteration of the event-loop, but
        other pending events/callbacks may be handled first. Returns a handle that
        can be used to ``.cancel()`` the callback.

        Not thread-safe; use ``call_soon_threadsafe()`` for scheduling callbacks
        from another thread.
        """

        # Checks
        if not callable(callback):
            raise TypeError("call_soon() expects a callable.")
        elif iscoroutinefunction(callback):
            raise TypeError("call_soon() expects a normal callable, not an async one.")

        self._ensure_initialized()

        # Create handle and dispatch it
        handle = CallbackHandle(self, callback, args)
        self.__callback_handles.add(handle)
        self._rc_call_soon(handle._run)

        return handle

    def call_soon_threadsafe(
        self, callback: CallbackFunction, *args: Any
    ) -> CallbackHandle:
        """A thread-safe variant of ``call_soon()``."""

        # Checks
        if not callable(callback):
            raise TypeError("call_soon() expects a callable.")
        elif iscoroutinefunction(callback):
            raise TypeError("call_soon() expects a normal callable, not an async one.")
        self._ensure_initialized()

        # Create handle and dispatch it
        handle = CallbackHandle(self, callback, args)
        self.__callback_handles.add(handle)
        self._rc_call_soon_threadsafe(handle._run)

        return handle

    def call_later(
        self, delay: float, callback: CallbackFunction, *args: Any
    ) -> CallbackHandle:
        """Arrange for a callback to be called after the given delay (in seconds).

        Returns a handle that can be used to ``.cancel()`` the callback. In contrast to asyncio's
        ``call_later()``, this method does not suffer from Window's notorious imprecision.
        """

        if delay <= 0:
            return self.call_soon(callback, *args)

        # Checks
        if not callable(callback):
            raise TypeError("call_later() expects a callable.")
        elif iscoroutinefunction(callback):
            raise TypeError("call_later() expects a normal callable, not an async one.")
        self._ensure_initialized()

        # Create handle and dispatch it
        handle = CallbackHandle(self, callback, args)
        self.__callback_handles.add(handle)
        self._rc_call_later(delay, handle._run)

        return handle

    def _unchecked_call_later(
        self, delay: float, callback: CallbackFunction, *args: Any
    ) -> CallbackHandle:
        """Call later without some checks for better performance, for the Task objects."""
        handle = CallbackHandle(self, callback, args)
        self.__callback_handles.add(handle)
        if delay <= 0:
            self._rc_call_soon(handle._run)
        else:
            self._rc_call_later(delay, handle._run)
        return handle

    def run(self) -> None:
        """Enter the main loop.

        This provides a generic API to start the loop. When building an application (e.g. with Qt)
        its fine to start the loop in the normal way.

        This call usually blocks, but it can also return immediately, e.g. when there are no
        canvases, or when the loop is already active (e.g. interactive via IDE).
        """

        # Can we enter the loop?
        if self.__state in (LoopState.off, LoopState.ready):
            # 'off': no canvases, but allow running one iteration.
            # 'ready': normal operation.
            pass
        elif self.__state == LoopState.active:
            # The loop is active, but not sure how. Maybe natively, or maybe this is the offscreen's stub loop.
            # Allow, maybe the backend raises an error.
            pass
        elif self.__state == LoopState.interactive:
            # Already marked active (interactive mode). For code compat, silent return!
            return
        else:
            # Already running via this method. Disallow re-entrance!
            raise RuntimeError(f"loop is already {self.__state}.")

        self._ensure_initialized()

        need_unregister = self.__setup_interrupt_hooks()

        # Run. We could be in this loop for a long time. Or we can exit immediately if
        # the backend already has an (interactive) event loop and did not call _mark_as_interactive().
        self.__state = LoopState.running
        try:
            self._rc_run()
        finally:
            # Mark state as not 'running', but also not to 'off', that happens elsewhere.
            if self.__state == LoopState.running:
                self.__state = LoopState.active
            if need_unregister:
                self.__restore_interrupt_hooks()

    async def run_async(self) -> None:
        """ "Alternative to ``run()``, to enter the mainloop from a running async framework.

        Only supported by the asyncio and trio loops.
        """

        # Can we enter the loop?
        if self.__state in (LoopState.off, LoopState.ready):
            pass
        else:
            raise RuntimeError(
                f"loop.run_async() can only be awaited once ({self.__state})."
            )

        # Get ready. If we were not initialized yet, this will probably mark us as interactive, because the loop is already running.
        self._ensure_initialized()

        # Mark as active, but not running, because we may just be a task in the native loop.
        self.__state = LoopState.active

        try:
            await self._rc_run_async()
        finally:
            self.stop(force=True)

    def stop(self, *, force=False) -> None:
        """Close all windows and stop the currently running event-loop.

        If the loop is active but not running via the ``run()`` method, the loop
        moves back to its off-state, but the underlying loop is not stopped.

        Normally, the windows are closed and the underlying event loop is given
        time to clean up and actually destroy the window. If ``force`` is set,
        the loop stops immediately. This can be an effective way to stop the
        loop when the native event loop has stopped.
        """

        if self.__state == LoopState.off:
            return

        # Only take action when we're inside the run() method
        self.__should_stop += 2 if force else 1

        # Close all canvases
        canvases = self.get_canvases()
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
        if len(self.get_canvases()) == 0 or self.__should_stop >= 2:
            self.__stop()

    def __setup_interrupt_hooks(self):
        """Setup asycgen hooks and interrupt hooks."""
        if self.__interrupt_hook_data is not None:
            return False

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

        self.__interrupt_hook_data = prev_handlers
        return True

    def __restore_interrupt_hooks(self):
        """Unregister hooks."""

        # This is separated from stop(), so that a loop can be 'active' by repeated calls to ``run()``, but will only
        # actually have registered hooks while inside ``run()``. The StubLoop has this behavior, and it may be a bit silly
        # to organize for this special use-case, but it does make it more clean/elegant, and maybe someday we will want another
        # loop class that runs for short periods. This now works, even when another loop is running.

        if self.__interrupt_hook_data is None:
            return

        prev_interrupt_hooks = self.__interrupt_hook_data
        self.__interrupt_hook_data = None

        for sig, cb in prev_interrupt_hooks.items():
            signal.signal(sig, cb)

    def __start(self):
        """Move to running state."""
        # Update state, but leave 'interactive' and 'running'
        if self.__state in (LoopState.off, LoopState.ready):
            self.__state = LoopState.active

        self.__setup_interrupt_hooks()

    def __stop(self):
        """Move to the off-state."""

        self.__is_initialized = False

        # Note that in here, we must fully bring our loop to a stop.
        # We cannot rely on future loop cycles.
        # Set flags to off state
        self.__state = LoopState.off
        self.__should_stop = 0

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

        # Cancel callbacks
        for handle in list(self.__callback_handles):
            handle.cancel()

        # Close alive async generators
        self._asyncgen_cancel_agens()

        # Restore interrupt hooks
        self.__restore_interrupt_hooks()

        # Tell the backend to stop the loop. This usually means it will stop
        # soon, but not *now*; remember that we're currently in a task as well.
        self._rc_stop()

    # Note: these hooks are implemented on the loop object, because wgpu checks them and is thereby able to detect call_soon_threadsafe.

    def _asyncgen_firstiter_hook(self, agen):
        self.__asyncgens.add(agen)

    def _asyncgen_finalizer_hook(self, agen):
        self.__asyncgens.discard(agen)
        close_agen(agen)

    def _asyncgen_cancel_agens(self):
        if len(self.__asyncgens):
            closing_agens = list(self.__asyncgens)
            self.__asyncgens.clear()
            for agen in closing_agens:
                close_agen(agen)

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

    def _rc_call_soon(self, callback):
        """Method to schedule a callback.

        Depending on the backend, it can sometimes use a faster/easier path than ``_rc_call_soon_threadsafe``.
        """
        raise NotImplementedError()

    def _rc_call_soon_threadsafe(self, callback):
        """Method to schedule a callback in the loop's thread.

        Must be thread-safe; this may be called from a different thread.
        """
        raise NotImplementedError()

    def _rc_call_later(self, delay, callback):
        """Method to call a callback in delay number of seconds.

        * It's optional for backends to implement this method;
          the default implementation uses ``call_later_from_thread`` and then ``_rc_call_soon_threadsafe``.
        * When overloading this method, keep in mind the notorious inaccurate timers on Windows!
        * No need to catch errors from the callback; that's dealt with internally.
        * You can assume that ``delay > 0``; the base class will use ``_rc_call_soon`` when ``delay <= 0``.
        * Return None.
        """
        # Default that is accurate on all platforms, but overloadable, e.g. Pyodide does not support threading.
        call_later_from_thread(delay, self._rc_call_soon_threadsafe, callback)


class CallbackHandle:
    """A wrapper for a callback that is scheduled to run by the rendercanvas loop."""

    # Note that this is user-facing API

    def __init__(self, loop: BaseLoop, func: Callable, args: tuple):
        self._loop = loop
        self._func = func
        self._args = args
        self._cancelled = False

    def __repr__(self):
        state = "pending"
        if self._cancelled:
            state = "cancelled"
        elif self._func is None:
            state = "done"
        return f"<{self.__class__.__name__} {state} at {hex(id(self))}>"

    def cancel(self):
        """Cancel the callback."""
        self._cancelled = True
        self._clear()

    def cancelled(self) -> bool:
        """Return whether the callback was cancelled."""
        return self._cancelled

    # TODO: also add 'when' method to indicate when it will be run?

    def _clear(self):
        self._func = None
        self._args = None
        if self._loop is not None:
            self._loop._unregister_callback_handle(self)
            self._loop = None

    def _run(self):
        if self._cancelled:
            return
        old_hooks = sys.get_asyncgen_hooks()
        sys.set_asyncgen_hooks(
            self._loop._asyncgen_firstiter_hook, self._loop._asyncgen_finalizer_hook
        )
        try:
            self._func(*self._args)
        except Exception as err:
            try:
                func_name = self._func.__name__
            except AttributeError:
                func_name = repr(self._func)
            log_this_exception(f"Callback error in {func_name}:", err)
        finally:
            sys.set_asyncgen_hooks(*old_hooks)
            self._clear()

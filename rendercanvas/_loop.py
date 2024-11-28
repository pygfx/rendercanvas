"""
The loop mechanics: the base timer, base loop, and scheduler.
"""

import time
import signal
import weakref

from ._coreutils import logger, log_exception, BaseEnum

from ._async_sniffs import sleep, Event  # rename this module
from asyncio import iscoroutinefunction
from ._async_adapter import Task as AsyncAdapterTask

# Note: technically, we could have a global loop proxy object that defers to any of the other loops.
# That would e.g. allow using glfw with qt together. Probably a too weird use-case for the added complexity.


HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)


class BaseLoop:
    """The base class for an event-loop object.

    Each backend provides its own loop subclass, so that rendercanvas can run cleanly in the backend's event loop.
    """

    def __init__(self):
        self.__tasks = []
        self._schedulers = []
        self._is_inside_run = False
        self._should_stop = 0
        self.__created_loop_task = False

    def _register_scheduler(self, scheduler):
        # Gets called whenever a canvas in instantiated
        self._schedulers.append(scheduler)
        # self._gui_timer.start(0.1)  # (re)start our internal timer
        if not self.__created_loop_task:
            self.__created_loop_task = True
            self.add_task(self._loop_task, name="loop")

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

            # Keep the GUI alive on every tick. This is extra, since the canvas task also calls it.
            self._rc_gui_poll()

            # Clean internal schedulers list
            self.get_canvases()

            # Our loop can still tick, even if the loop is not started via our run() method.
            # If this is the case, we don't run the close/stop logic
            if not self._is_inside_run:
                continue

            # Should we stop?
            if not self._schedulers:
                # Stop when there are no more canvases
                self._rc_stop()
            elif self._should_stop >= 2:
                # force a stop without waiting for the canvases to close
                self._rc_stop()
            elif self._should_stop:
                # Close all remaining canvases. Loop will stop in a next iteration.
                for canvas in self.get_canvases():
                    if not getattr(canvas, "_rc_closed_by_loop", False):
                        canvas._rc_closed_by_loop = True
                        canvas._rc_close()
                        del canvas

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
        for task in self.__tasks:
            task.cancel()
        self.__tasks = []

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

    def _rc_gui_poll(self):
        """Process GUI events.

        Some event loops (e.g. asyncio) are just that and dont have a GUI to update.
        Other loops (like Qt) already process events. So this is only intended for
        backends like glfw.
        """
        pass


class UpdateMode(BaseEnum):
    """The different modes to schedule draws for the canvas."""

    manual = None  #: Draw events are never scheduled. Draws only happen when you ``canvas.force_draw()``, and maybe when the GUI system issues them (e.g. when resizing).
    ondemand = None  #: Draws are only scheduled when ``canvas.request_draw()`` is called when an update is needed. Safes your laptop battery. Honours ``min_fps`` and ``max_fps``.
    continuous = None  #: Continuously schedules draw events, honouring ``max_fps``. Calls to ``canvas.request_draw()`` have no effect.
    fastest = None  #: Continuously schedules draw events as fast as possible. Gives high FPS (and drains your battery).


class Scheduler:
    """Helper class to schedule event processing and drawing."""

    # This class makes the canvas tick. Since we do not own the event-loop, but
    # ride on e.g. Qt, asyncio, wx, JS, or something else, our little "loop" is
    # implemented with a timer.
    #
    # The loop looks a little like this:
    #
    #     ________________      __      ________________      __      rd = request_draw
    #   /   wait           \  / rd \  /   wait           \  / rd \
    #  |                    ||      ||                    ||      |
    # --------------------------------------------------------------------> time
    #  |                    |       |                     |       |
    #  schedule             tick    draw                  tick    draw
    #
    # With update modes 'ondemand' and 'manual', the loop ticks at the same rate
    # as on 'continuous' mode, but won't draw every tick:
    #
    #     ________________     ________________      __
    #   /    wait          \  /   wait          \  / rd \
    #  |                    ||                   ||      |
    # --------------------------------------------------------------------> time
    #  |                    |                    |       |
    #  schedule             tick                tick     draw
    #
    # A tick is scheduled by calling _schedule_next_tick(). If this method is
    # called when the timer is already running, it has no effect. In the _tick()
    # method, events are processed (including animations). Then, depending on
    # the mode and whether a draw was requested, a new tick is scheduled, or a
    # draw is requested. In the latter case, the timer is not started, but we
    # wait for the canvas to perform a draw. In _draw_drame_and_present() the
    # draw is done, and a new tick is scheduled.
    #
    # The next tick is scheduled when a draw is done, and not earlier, otherwise
    # the drawing may not keep up with the ticking.
    #
    # On desktop canvases the draw usually occurs very soon after it is
    # requested, but on remote frame buffers, it may take a bit longer. To make
    # sure the rendered image reflects the latest state, these backends may
    # issue an extra call to _process_events() right before doing the draw.
    #
    # When the window is minimized, the draw will not occur until the window is
    # shown again. For the canvas to detect minimized-state, it will need to
    # receive GUI events. This is one of the reasons why the loop object also
    # runs a timer-loop.
    #
    # The drawing itself may take longer than the intended wait time. In that
    # case, it will simply take longer than we hoped and get a lower fps.
    #
    # Note that any extra draws, e.g. via force_draw() or due to window resizes,
    # don't affect the scheduling loop; they are just extra draws.

    def __init__(self, canvas, events, loop, *, mode="ondemand", min_fps=1, max_fps=30):
        assert loop is not None

        # We don't keep a ref to the canvas to help gc. This scheduler object can be
        # referenced via a callback in an event loop, but it won't prevent the canvas
        # from being deleted!
        self._canvas_ref = weakref.ref(canvas)
        self._events = events
        # ... = canvas.get_context() -> No, context creation should be lazy!

        # Scheduling variables
        if mode not in UpdateMode:
            raise ValueError(
                f"Invalid update_mode '{mode}', must be in {set(UpdateMode)}."
            )
        self._mode = mode
        self._min_fps = float(min_fps)
        self._max_fps = float(max_fps)
        self._draw_requested = True  # Start with a draw in ondemand mode
        self._last_draw_time = 0
        self._async_draw_event = None

        # Keep track of fps
        self._draw_stats = 0, time.perf_counter()

        # Initialise the timer that runs our scheduling loop.
        # Note that the backend may do a first draw earlier, starting the loop, and that's fine.
        self._last_tick_time = -0.1
        # self._timer = loop.call_later(0.1, self._tick)

        # Register this scheduler/canvas at the loop object
        loop._register_scheduler(self)
        loop.add_task(
            self.__scheduler_task, name=f"{canvas.__class__.__name__} scheduler"
        )

    def get_canvas(self):
        """Get the canvas, or None if it is closed or gone."""
        canvas = self._canvas_ref()
        if canvas is None or canvas.get_closed():
            # Pretty nice, we can send a close event, even if the canvas no longer exists
            self._events._rc_close()
            return None
        else:
            return canvas

    def request_draw(self):
        """Request a new draw to be done. Only affects the 'ondemand' mode."""
        # Just set the flag
        self._draw_requested = True

    async def __scheduler_task(self):
        """Schedule _tick() to be called via our timer."""

        while True:
            # Determine delay
            if self._mode == "fastest" or self._max_fps <= 0:
                delay = 0
            else:
                delay = 1 / self._max_fps
                delay = 0 if delay < 0 else delay  # 0 means cannot keep up

            # Offset delay for time spent on processing events, etc.
            time_since_tick_start = time.perf_counter() - self._last_tick_time
            delay -= time_since_tick_start
            delay = max(0, delay)

            # Wait
            await sleep(delay)

            # Get canvas or stop
            if (canvas := self.get_canvas()) is None:
                return

            # Below is the "tick"

            self._last_tick_time = time.perf_counter()

            # Process events, handlers may request a draw
            await canvas._process_events()

            # Determine what to do next ...

            do_draw = False

            if self._mode == "fastest":
                # fastest: draw continuously as fast as possible, ignoring fps settings.
                do_draw = True
            elif self._mode == "continuous":
                # continuous: draw continuously, aiming for a steady max framerate.
                do_draw = True
            elif self._mode == "ondemand":
                # ondemand: draw when needed (detected by calls to request_draw).
                # Aim for max_fps when drawing is needed, otherwise min_fps.
                if self._draw_requested:
                    do_draw = True
                elif (
                    self._min_fps > 0
                    and time.perf_counter() - self._last_draw_time > 1 / self._min_fps
                ):
                    do_draw = True

            elif self._mode == "manual":
                pass
            else:
                raise RuntimeError(f"Unexpected scheduling mode: '{self._mode}'")

            # If we don't want to draw, we move to the next iter
            if not do_draw:
                continue

            canvas._rc_request_draw()
            self._async_draw_event = Event()
            await self._async_draw_event.wait()

    def on_draw(self):
        # Bookkeeping
        self._last_draw_time = time.perf_counter()
        self._draw_requested = False

        # Keep ticking
        if self._async_draw_event:
            self._async_draw_event.set()
            self._async_draw_event = None

        # Update stats
        count, last_time = self._draw_stats
        count += 1
        if time.perf_counter() - last_time > 1.0:
            fps = count / (time.perf_counter() - last_time)
            self._draw_stats = 0, time.perf_counter()
        else:
            fps = None
            self._draw_stats = count, last_time

        # Return fps or None. Will change with better stats at some point
        return fps

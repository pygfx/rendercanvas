"""
The loop mechanics: the base timer, base loop, and scheduler.
"""

import time
import signal
import weakref

from ._coreutils import logger, log_exception, BaseEnum


# Note: technically, we could have a global loop proxy object that defers to any of the other loops.
# That would e.g. allow using glfw with qt together. Probably a too weird use-case for the added complexity.


HANDLED_SIGNALS = (
    signal.SIGINT,  # Unix signal 2. Sent by Ctrl+C.
    signal.SIGTERM,  # Unix signal 15. Sent by `kill <pid>`.
)
# if sys.platform == "win32":
#     HANDLED_SIGNALS += (signal.SIGBREAK,)  # Windows signal 21. Sent by Ctrl+Break.


class BaseTimer:
    """The Base class for a timer object.

    Each backends provides its own timer subclass. The timer is used by the internal scheduling mechanics,
    and is also returned by user-facing API such as ``loop.call_later()``.
    """

    _running_timers = set()

    def __init__(self, loop, callback, *args, one_shot=False):
        # The loop arg is passed as an argument, so that the Loop object itself can create a timer.
        self._loop = loop
        # Check callable
        if not callable(callback):
            raise TypeError("Given timer callback is not a callable.")
        self._callback = callback
        self._args = args
        # Internal variables
        self._one_shot = bool(one_shot)
        self._interval = None
        self._expect_tick_at = None

    def start(self, interval):
        """Start the timer with the given interval.

        When the interval has passed, the callback function will be called,
        unless the timer is stopped earlier.

        When the timer is currently running, it is first stopped and then
        restarted.
        """
        if self._interval is None:
            self._rc_init()
        if self.is_running:
            self._rc_stop()
        BaseTimer._running_timers.add(self)
        self._interval = max(0.0, float(interval))
        self._expect_tick_at = time.perf_counter() + self._interval
        self._rc_start()

    def stop(self):
        """Stop the timer.

        If the timer is currently running, it is stopped, and the
        callback is *not* called. If the timer is currently not running,
        this method does nothing.
        """
        BaseTimer._running_timers.discard(self)
        self._expect_tick_at = None
        self._rc_stop()

    def _tick(self):
        """The implementations must call this method."""
        # Stop or restart
        if self._one_shot:
            BaseTimer._running_timers.discard(self)
            self._expect_tick_at = None
        else:
            self._expect_tick_at = time.perf_counter() + self._interval
            self._rc_start()
        # Callback
        with log_exception("Timer callback error"):
            self._callback(*self._args)

    @property
    def time_left(self):
        """The expected time left before the callback is called.

        None means that the timer is not running. The value can be negative
        (which means that the timer is late).
        """
        if self._expect_tick_at is None:
            return None
        else:
            return self._expect_tick_at - time.perf_counter()

    @property
    def is_running(self):
        """Whether the timer is running.

        A running timer means that a new call to the callback is scheduled and
        will happen in ``time_left`` seconds (assuming the event loop keeps
        running).
        """
        return self._expect_tick_at is not None

    @property
    def is_one_shot(self):
        """Whether the timer is one-shot or continuous.

        A one-shot timer stops running after the currently scheduled call to the callback.
        It can then be started again. A continuous timer (i.e. not one-shot) automatically
        schedules new calls.
        """
        return self._one_shot

    def _rc_init(self):
        """Initialize the (native) timer object.

        Opportunity to initialize the timer object. This is called right
        before the timer is first started.
        """
        pass

    def _rc_start(self):
        """Start the timer.

        * Must schedule for ``self._tick`` to be called in ``self._interval`` seconds.
        * Must call it exactly once (the base class takes care of repeating the timer).
        * When ``self._rc_stop()`` is called before the timer finished, the call to ``self._tick()`` must be cancelled.
        """
        raise NotImplementedError()

    def _rc_stop(self):
        """Stop the timer.

        * If the timer is running, cancel the pending call to ``self._tick()``.
        * Otherwise, this should do nothing.
        """
        raise NotImplementedError()


class BaseLoop:
    """The base class for an event-loop object.

    Each backends provides its own loop subclass, so that rendercanvas can run cleanly in the backend's event loop.
    """

    _TimerClass = None  # subclases must set this

    def __init__(self):
        self._schedulers = []
        self._is_inside_run = False
        self._should_stop = 0

        # The loop object runs a lightweight timer for a few reasons:
        # * Support running the loop without windows (e.g. to keep animations going).
        # * Detect closed windows. Relying on the backend alone is tricky, since the
        #   loop usually stops when the last window is closed, so the close event may
        #   not be fired.
        # * Keep the GUI going even when the canvas loop is on pause e.g. because its
        #   minimized (applies to backends that implement _rc_gui_poll).
        self._gui_timer = self._TimerClass(self, self._tick, one_shot=False)

    def _register_scheduler(self, scheduler):
        # Gets called whenever a canvas in instantiated
        self._schedulers.append(scheduler)
        self._gui_timer.start(0.1)  # (re)start our internal timer

    def get_canvases(self):
        """Get a list of currently active (not-closed) canvases."""
        canvases = []
        schedulers = []

        for scheduler in self._schedulers:
            canvas = scheduler._get_canvas()
            if canvas is not None:
                canvases.append(canvas)
                schedulers.append(scheduler)

        # Forget schedulers that no longer have a live canvas
        self._schedulers = schedulers

        return canvases

    def _tick(self):
        # Keep the GUI alive on every tick
        self._rc_gui_poll()

        # Clean internal schedulers list
        self.get_canvases()

        # Our loop can still tick, even if the loop is not started via our run() method.
        # If this is the case, we don't run the close/stop logic
        if not self._is_inside_run:
            return

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

    def call_soon(self, callback, *args):
        """Arrange for a callback to be called as soon as possible.

        The callback will be called in the next iteration of the event-loop,
        but other pending events/callbacks may be handled first. Returns None.
        """
        self._rc_call_soon(callback, *args)

    def call_later(self, delay, callback, *args):
        """Arrange for a callback to be called after the given delay (in seconds).

        Returns a timer object (in one-shot mode) that can be used to
        stop the time (i.e. cancel the callback being called), and/or
        to restart the timer.

        It's not necessary to hold a reference to the timer object; a
        ref is held automatically, and discarded when the timer ends or stops.
        """
        timer = self._TimerClass(self, callback, *args, one_shot=True)
        timer.start(delay)
        return timer

    def call_repeated(self, interval, callback, *args):
        """Arrange for a callback to be called repeatedly.

        Returns a timer object (in multi-shot mode) that can be used for
        further control.

        It's not necessary to hold a reference to the timer object; a
        ref is held automatically, and discarded when the timer is
        stopped.
        """
        timer = self._TimerClass(self, callback, *args, one_shot=False)
        timer.start()
        return timer

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

    def _rc_stop(self):
        """Stop the event loop.

        * Stop the running event loop.
        * This will only be called when the process is inside _rc_run().
          I.e. not for interactive mode.
        """
        raise NotImplementedError()

    def _rc_call_soon(self, callback, *args):
        """Method to call a callback in the next iteraction of the event-loop.

        * A quick path to have callback called in a next invocation of the event loop.
        * This method is optional: the default implementation just calls ``call_later()`` with a zero delay.
        """
        self.call_later(0, callback, *args)

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

        # Keep track of fps
        self._draw_stats = 0, time.perf_counter()

        # Initialise the timer that runs our scheduling loop.
        # Note that the backend may do a first draw earlier, starting the loop, and that's fine.
        self._last_tick_time = -0.1
        self._timer = loop.call_later(0.1, self._tick)

        # Register this scheduler/canvas at the loop object
        loop._register_scheduler(self)

    def _get_canvas(self):
        canvas = self._canvas_ref()
        if canvas is None or canvas.is_closed():
            # Pretty nice, we can send a close event, even if the canvas no longer exists
            self._events._rc_close()
            return None
        else:
            return canvas

    def request_draw(self):
        """Request a new draw to be done. Only affects the 'ondemand' mode."""
        # Just set the flag
        self._draw_requested = True

    def _schedule_next_tick(self):
        """Schedule _tick() to be called via our timer."""

        if self._timer.is_running:
            return

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

        # Go!
        self._timer.start(delay)

    def _tick(self):
        """Process event and schedule a new draw or tick."""

        self._last_tick_time = time.perf_counter()

        # Get canvas or stop
        if (canvas := self._get_canvas()) is None:
            return

        # Process events, handlers may request a draw
        canvas._process_events()

        # Determine what to do next ...

        if self._mode == "fastest":
            # fastest: draw continuously as fast as possible, ignoring fps settings.
            canvas._rc_request_draw()

        elif self._mode == "continuous":
            # continuous: draw continuously, aiming for a steady max framerate.
            canvas._rc_request_draw()

        elif self._mode == "ondemand":
            # ondemand: draw when needed (detected by calls to request_draw).
            # Aim for max_fps when drawing is needed, otherwise min_fps.
            if self._draw_requested:
                canvas._rc_request_draw()
            elif (
                self._min_fps > 0
                and time.perf_counter() - self._last_draw_time > 1 / self._min_fps
            ):
                canvas._rc_request_draw()
            else:
                self._schedule_next_tick()

        elif self._mode == "manual":
            # manual: never draw, except when ... ?
            self._schedule_next_tick()

        else:
            raise RuntimeError(f"Unexpected scheduling mode: '{self._mode}'")

    def on_draw(self):
        """Called from canvas._draw_frame_and_present()."""

        # Bookkeeping
        self._last_draw_time = time.perf_counter()
        self._draw_requested = False

        # Keep ticking
        self._schedule_next_tick()

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

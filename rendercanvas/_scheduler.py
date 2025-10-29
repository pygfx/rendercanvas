"""
The scheduler class/loop.
"""

import sys
import time
import weakref

from ._enums import UpdateMode
from .utils.asyncs import sleep, Event


IS_WIN = sys.platform.startswith("win")


class Scheduler:
    """Helper class to schedule event processing and drawing."""

    # This class makes the canvas tick. Since we do not own the event-loop, but
    # ride on e.g. Qt, asyncio, wx, JS, or something else, we need to abstract the loop.
    # We implement it as an async function, that way we can cleanly support async event
    # handlers. Note, however, that the draw-event cannot be async, so it does not
    # fit well into the loop. An event is used to wait for it.
    #
    # We have to make sure that there is only one invocation of the scheduler task,
    # or we'd get double the intended FPS.
    #
    # After a draw is requested, we wait for it to happen, otherwise
    # the drawing may not keep up with the ticking.
    #
    # On desktop canvases the draw usually occurs very soon after it is
    # requested, but on remote frame buffers, it may take a bit longer,
    # which may cause a laggy feeling.
    #
    # When the window is minimized, the draw will not occur until the window is
    # shown again. For the canvas to detect minimized-state, it will need to
    # receive GUI events. This is one of the reasons why the loop object also
    # runs a loop-task.
    #
    # The drawing itself may take longer than the intended wait time. In that
    # case, it will simply take longer than we hoped and get a lower fps.
    #
    # Note that any extra draws, e.g. via force_draw() or due to window resizes,
    # don't affect the scheduling loop; they are just extra draws.

    def __init__(
        self, canvas, events, *, update_mode="ondemand", min_fps=0.0, max_fps=30.0
    ):
        self.name = f"{canvas.__class__.__name__} scheduler"

        # We don't keep a ref to the canvas to help gc. This scheduler object can be
        # referenced via a callback, but it won't prevent the canvas from being deleted!
        self._canvas_ref = weakref.ref(canvas)
        self._events = events
        # ... = canvas.get_context() -> No, context creation should be lazy!

        # Scheduling variables
        self.set_update_mode(update_mode, min_fps=min_fps, max_fps=max_fps)
        self._draw_requested = True  # Start with a draw in ondemand mode
        self._async_draw_event = None

        # Keep track of fps
        self._draw_stats = 0, time.perf_counter()

    def get_task(self):
        """Get task. Can be called exactly once. Used by the canvas."""
        task = self.__scheduler_task
        self.__scheduler_task = None  # type: ignore
        assert task is not None
        return task

    def get_canvas(self):
        """Get the canvas, or None if it is closed or gone."""
        canvas = self._canvas_ref()
        if canvas is None or canvas.get_closed():
            return None
        else:
            return canvas

    def set_update_mode(self, update_mode, *, min_fps=None, max_fps=None):
        update_mode = str(update_mode)
        if update_mode not in UpdateMode:
            raise ValueError(
                f"Invalid update_mode '{update_mode}', must be in {set(UpdateMode)}."
            )
        self._mode = update_mode

        if min_fps is not None:
            self._min_fps = max(0.0, float(min_fps))

        if max_fps is not None:
            # For users setting max_fps=-1 to try to disable the fps cap, as was the way to go in wgpu.gui
            if max_fps < 1:
                raise ValueError(
                    "max_fps should be a >= 1. Use update_mode='fastest' to disable the fps cap. Also see ``vsync=False`` to unlock higher frame rates."
                )
            self._max_fps = max(1, float(max_fps))

    def request_draw(self):
        """Request a new draw to be done. Only affects the 'ondemand' mode."""
        # Just set the flag
        self._draw_requested = True

    async def __scheduler_task(self):
        """The coro that represents the scheduling loop for a canvas."""

        last_draw_time = 0
        last_tick_time = 0

        # Little startup sleep
        await sleep(0.05)

        while True:
            # Determine delay
            if self._mode == "fastest" or self._max_fps <= 0:
                delay = 0
            else:
                delay = 1 / self._max_fps
                delay = 0 if delay < 0 else delay  # 0 means cannot keep up

            # Determine amount of sleep
            sleep_time = delay - (time.perf_counter() - last_tick_time)

            if IS_WIN:
                # On Windows OS-level timers have an in accuracy of 15.6 ms.
                # This can cause sleep to take longer than intended. So we sleep
                # less, and then do a few small sync-sleeps that have high accuracy.
                await sleep(max(0, sleep_time - 0.0156))
                sleep_time = delay - (time.perf_counter() - last_tick_time)
                while sleep_time > 0:
                    time.sleep(min(sleep_time, 0.001))  # sleep hard for at most 1ms
                    await sleep(0)  # Allow other tasks to run but don't wait
                    sleep_time = delay - (time.perf_counter() - last_tick_time)
            else:
                # Wait. Even if delay is zero, it gives control back to the loop,
                # allowing other tasks to do work.
                await sleep(max(0, sleep_time))

            # Below is the "tick"

            last_tick_time = time.perf_counter()

            # Determine whether to draw or not yet

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
                    and time.perf_counter() - last_draw_time > 1 / self._min_fps
                ):
                    do_draw = True
            elif self._mode == "manual":
                pass
            else:
                raise RuntimeError(f"Unexpected scheduling mode: '{self._mode}'")

            # Get canvas object or stop the loop
            if (canvas := self.get_canvas()) is None:
                break

            # Process events now.
            # Note that we don't want to emit events *during* the draw, because event
            # callbacks do stuff, and that stuff may include changing the canvas size,
            # or affect layout in a UI application, all which are not recommended during
            # the main draw-event (a.k.a. animation frame), and may even lead to errors.
            # The one exception is resize events, which we do emit during a draw, if the
            # size has changed since the last time that events were processed.
            canvas._process_events()

            if not do_draw:
                # If we don't want to draw, move to the next iter
                del canvas
                continue
            else:
                # Otherwise, request a draw ...
                canvas._rc_request_draw()
                del canvas
                # ... and wait for the draw to happen
                self._async_draw_event = Event()
                await self._async_draw_event.wait()
                last_draw_time = time.perf_counter()

        # Note that when the canvas is closed, we may detect it here and break from the loop.
        # But the task may also be waiting for a draw to happen, or something else. In that case
        # this task will be cancelled when the loop ends. In any case, this is why this is not
        # a good place to detect the canvas getting closed, the loop does this.

    def on_draw(self):
        # Bookkeeping
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

"""
Offscreen canvas. No scheduling.
"""

__all__ = ["RenderCanvas", "loop"]

from .base import BaseRenderCanvas, BaseLoop, BaseTimer


class ManualOffscreenRenderCanvas(BaseRenderCanvas):
    """An offscreen canvas intended for manual use.

    Call the ``.draw()`` method to perform a draw and get the result.
    """

    def __init__(self, *args, pixel_ratio=1.0, **kwargs):
        super().__init__(*args, **kwargs)
        self._pixel_ratio = pixel_ratio
        self._closed = False
        self._last_image = None
        self._final_canvas_init()

    # %% Methods to implement RenderCanvas

    def _rc_get_loop(self):
        return None  # No scheduling

    def _rc_get_present_methods(self):
        return {
            "bitmap": {
                "formats": ["rgba-u8"],
            }
        }

    def _rc_request_draw(self):
        # Ok, cool, the scheduler want a draw. But we only draw when the user
        # calls draw(), so that's how this canvas ticks.
        pass

    def _rc_force_draw(self):
        self._draw_frame_and_present()

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        self._last_image = data

    def _rc_get_physical_size(self):
        return int(self._logical_size[0] * self._pixel_ratio), int(
            self._logical_size[1] * self._pixel_ratio
        )

    def _rc_get_logical_size(self):
        return self._logical_size

    def _rc_get_pixel_ratio(self):
        return self._pixel_ratio

    def _rc_set_logical_size(self, width, height):
        self._logical_size = width, height

    def _rc_close(self):
        self._closed = True

    def _rc_is_closed(self):
        return self._closed

    def _rc_set_title(self, title):
        pass

    # %% events - there are no GUI events

    # %% Extra API

    def draw(self):
        """Perform a draw and get the resulting image.

        The image array is returned as an NxMx4 memoryview object.
        This object can be converted to a numpy array (without copying data)
        using ``np.asarray(arr)``.
        """
        loop._process_timers()  # Little trick to keep the event loop going
        self._draw_frame_and_present()
        return self._last_image


RenderCanvas = ManualOffscreenRenderCanvas


class StubTimer(BaseTimer):
    def _rc_init(self):
        pass

    def _rc_start(self):
        pass

    def _rc_stop(self):
        pass


class StubLoop(BaseLoop):
    # If we consider the use-cases for using this offscreen canvas:
    #
    # * Using rendercanvas.auto in test-mode: in this case run() should not hang,
    #   and call_later should not cause lingering refs.
    # * Using the offscreen canvas directly, in a script: in this case you
    #   do not have/want an event system.
    # * Using the offscreen canvas in an evented app. In that case you already
    #   have an app with a specific event-loop (it might be PySide6 or
    #   something else entirely).
    #
    # In summary, we provide a call_later() and run() that behave pretty
    # well for the first case.

    _TimerClass = StubTimer  # subclases must set this

    def _process_timers(self):
        # Running this loop processes any timers
        for timer in list(BaseTimer._running_timers):
            if timer.time_left <= 0:
                timer._tick()

    def _rc_run(self):
        self._process_timers()

    def _rc_stop(self):
        pass

    def _rc_call_soon(self, callback):
        super()._rc_call_soon(callback)

    def _rc_gui_poll(self):
        pass


loop = StubLoop()
run = loop.run

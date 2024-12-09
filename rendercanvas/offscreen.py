"""
Offscreen canvas. No scheduling.
"""

__all__ = ["OffscreenRenderCanvas", "RenderCanvas", "loop"]

import time

from .base import BaseCanvasGroup, BaseRenderCanvas, BaseLoop


class OffscreenCanvasGroup(BaseCanvasGroup):
    pass


class OffscreenRenderCanvas(BaseRenderCanvas):
    """An offscreen canvas intended for manual use.

    Call the ``.draw()`` method to perform a draw and get the result.
    """

    _rc_canvas_group = OffscreenCanvasGroup(None)  # no loop, no scheduling

    def __init__(self, *args, pixel_ratio=1.0, **kwargs):
        super().__init__(*args, **kwargs)
        self._pixel_ratio = pixel_ratio
        self._closed = False
        self._last_image = None
        self._final_canvas_init()

    # %% Methods to implement RenderCanvas

    def _rc_gui_poll(self):
        pass

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

    def _rc_get_closed(self):
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
        loop.process_tasks()  # Little trick to keep the event loop going
        self._draw_frame_and_present()
        return self._last_image


RenderCanvas = OffscreenRenderCanvas


class StubLoop(BaseLoop):
    # Note: we can move this into its own module if it turns out we need this in more places.
    #
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

    def __init__(self):
        super().__init__()
        self._callbacks = []

    def process_tasks(self):
        callbacks_to_run = []
        new_callbacks = []
        for etime, callback in self._callbacks:
            if time.perf_counter() >= etime:
                callbacks_to_run.append(callback)
            else:
                new_callbacks.append((etime, callback))
        if callbacks_to_run:
            self._callbacks = new_callbacks
            for callback in callbacks_to_run:
                callback()

    def _rc_run(self):
        self.process_tasks()

    def _rc_stop(self):
        self._callbacks = []

    def _rc_add_task(self, async_func, name):
        super()._rc_add_task(async_func, name)

    def _rc_call_later(self, delay, callback):
        self._callbacks.append((time.perf_counter() + delay, callback))


loop = StubLoop()

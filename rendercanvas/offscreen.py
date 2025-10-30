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

    Arguments:
        pixel_ratio (float): the ratio of logical to physical pixels.
        format (str): the preferred format. Multiple formats are supported, but by
            setting the preferred format here, other systems (e.g. Pygfx) will
            automatically use that format.
    """

    _rc_canvas_group = OffscreenCanvasGroup(None)  # no loop, no scheduling

    def __init__(self, *args, pixel_ratio=1.0, format="rgba-u8", **kwargs):
        super().__init__(*args, **kwargs)
        self._pixel_ratio = float(pixel_ratio)
        self._closed = False
        self._last_image = None

        self._present_formats = ["rgba-u8", "rgba-f16", "rgba-f32", "rgba-u16"]
        if format != self._present_formats[0]:
            colors, _, dtype = format.partition("-")
            if not (
                colors in ("i", "rgb", "rgba", "bgra")
                and dtype in ("u8", "u16", "u32", "f16", "f32")
            ):
                raise ValueError(f"Unexpected format: {format!r}")
            if format in self._present_formats:
                self._present_formats.remove(format)
            self._present_formats.insert(0, format)

        self._final_canvas_init()

    # %% Methods to implement RenderCanvas

    def _rc_gui_poll(self):
        pass

    def _rc_get_present_methods(self):
        return {
            "bitmap": {
                "formats": self._present_formats,
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

    def _rc_set_logical_size(self, width, height):
        logical_size = float(width), float(height)

        physical_size = (
            int(logical_size[0] * self._pixel_ratio),
            int(logical_size[1] * self._pixel_ratio),
        )
        self._set_size_info(physical_size, self._pixel_ratio)

    def _rc_close(self):
        self._closed = True

    def _rc_get_closed(self):
        return self._closed

    def _rc_set_title(self, title):
        pass

    def _rc_set_cursor(self, cursor):
        pass

    # %% events - there are no GUI events

    # %% Extra API

    def set_physical_size(self, width: int, height: int):
        """Set the size of the backbuffer (in physical pixels).

        The logical size is re-calculated using the current pixel ratio.
        """
        physical_size = int(width), int(height)
        self._set_size_info(physical_size, self._pixel_ratio)

    def set_pixel_ratio(self, pixel_ratio: float):
        """Set the pixel ratio, changing the logical size of the canvas.

        The physical size remains the same. If you want to retain a certain
        logical size, first set the pixel ratio and then the logical size.
        """
        self._pixel_ratio = float(pixel_ratio)
        physical_size = self.get_physical_size()
        self._set_size_info(physical_size, self._pixel_ratio)

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

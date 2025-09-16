import rendercanvas
print("rendercanvas version:", rendercanvas.__version__)
from rendercanvas.base import BaseRenderCanvas, BaseCanvasGroup, BaseLoop

from rendercanvas.asyncio import loop

import logging
import numpy as np

# packages available inside pyodide
from pyodide.ffi import run_sync
from js import document, ImageData, Uint8ClampedArray, window
# import sys
# assert sys.platform == "emscripten" # use in the future to direct the auto backend?

logger = logging.getLogger("rendercanvas")
logger.setLevel(logging.DEBUG)
# needed for completeness? somehow is required for other examples - hmm?
class HTMLCanvasGroup(BaseCanvasGroup):
    pass

# TODO: make this a proper RenderCanvas, just a poc for now
# https://rendercanvas.readthedocs.io/stable/backendapi.html#rendercanvas.stub.StubRenderCanvas
class HTMLBitmapCanvas(BaseRenderCanvas):
    _rc_canvas_group = HTMLCanvasGroup(loop) # todo do we need the group?
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        canvas_element = document.getElementById("canvas")
        self.canvas_element = canvas_element
        self.context = canvas_element.getContext("bitmaprenderer")

        self._final_canvas_init()

    def _rc_gui_poll(self):
        # not sure if anything has to be done
        pass

    def _rc_get_present_methods(self):
        # in the future maybe we can get the webgpu context (as JsProxy) or something... future stuff!
        return {
            "bitmap": {
                "formats": ["rgba-u8"],
            }
        }

    def _rc_request_draw(self):
        # loop.call_soon?
        # window.requestAnimationFrame(self._draw_frame_and_present)
        self._rc_force_draw()
        print("request draw called?")

    def _rc_force_draw(self):
        self._draw_frame_and_present()

    def _rc_present_bitmap(self):
        print("presenting...")
        # this actually "writes" the data to the canvas I guess.
        self.context.transferFromImageBitmap(self._image_bitmap)
        print("presented!")

    def _rc_get_physical_size(self):
        return self.canvas_element.style.width, self.canvas_element.style.height

    def _rc_get_logical_size(self):
        return float(self.canvas_element.width), float(self.canvas_element.height)

    def _rc_get_pixel_ratio(self) -> float:
        ratio = window.devicePixelRatio
        return ratio

    def _rc_set_logical_size(self, width: float, height: float):
        return
        ratio = self._rc_get_pixel_ratio()
        self.canvas_element.width = f"{int(width * ratio)}px"
        self.canvas_element.height = f"{int(height * ratio)}px"
        # also set the physical scale here?
        # self.canvas_element.style.width = f"{width}px"
        # self.canvas_element.style.height = f"{height}px"

    def set_bitmap(self, bitmap):
        # doesn't really exist? as it's part of the context? maybe we move it into the draw function...
        h, w, _ = bitmap.shape
        flat_bitmap = bitmap.flatten()
        js_array = Uint8ClampedArray.new(flat_bitmap.tolist())
        image_data = ImageData.new(js_array, w, h)
        # now this is the fake async call so it should be blocking
        self._image_bitmap = run_sync(window.createImageBitmap(image_data))

    def _rc_close(self):
        # self.canvas_element.remove() # shouldn't really be needed?
        pass

    def _rc_get_closed(self):
        # TODO: like check if the element still exists?
        return False

    def _rc_set_title(self, title: str):
        # canvas element doens't have a title directly... but maybe the whole page?
        document.title = title

    # TODO: events

# TODO event loop for js? https://rendercanvas.readthedocs.io/stable/backendapi.html#rendercanvas.stub.StubLoop
# https://pyodide.org/en/stable/usage/api/python-api/webloop.html
# https://pyodide.org/en/stable/usage/sdl.html#working-with-infinite-loop
# also the asyncio implementation
class HTMLLoop(BaseLoop):
    def _rc_init():
        from pyodide.webloop import WebLoop, PyodideFuture, PyodideTask



canvas = HTMLBitmapCanvas(title="RenderCanvas in Pyodide", max_fps=10.0)
def animate():
    # based on the noise.py example
    w, h = canvas._rc_get_logical_size()
    shape = (int(h), int(w), 4) # third dimension sounds like it's needed
    print(shape)
    bitmap = np.random.uniform(0, 255, shape).astype(np.uint8)
    canvas.set_bitmap(bitmap)
    print("bitmap set")

animate()
# canvas.force_draw()
canvas._rc_force_draw()
canvas._rc_present_bitmap()
# canvas.request_draw(animate)
# loop.run()

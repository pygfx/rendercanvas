"""
Test the base canvas class.
"""

import numpy as np
import rendercanvas
from testutils import run_tests, can_use_wgpu_lib
from pytest import mark


def test_base_canvas_context():
    assert hasattr(rendercanvas.BaseRenderCanvas, "get_context")


class CanvasThatRaisesErrorsDuringDrawing(rendercanvas.BaseRenderCanvas):
    def __init__(self):
        super().__init__()
        self._count = 0

    def _draw_frame(self):
        self._count += 1
        if self._count <= 4:
            self.foo_method()
        else:
            self.spam_method()

    def foo_method(self):
        self.bar_method()

    def bar_method(self):
        raise Exception("call-failed-" + "but-test-passed")

    def spam_method(self):
        msg = "intended-fail"  # avoid line with the message to show in the tb
        raise Exception(msg)


def test_canvas_logging(caplog):
    """As we attempt to draw, the canvas will error, which are logged.
    Each first occurrence is logged with a traceback. Subsequent same errors
    are much shorter and have a counter.
    """

    canvas = CanvasThatRaisesErrorsDuringDrawing()

    canvas._draw_frame_and_present()  # prints traceback
    canvas._draw_frame_and_present()  # prints short logs ...
    canvas._draw_frame_and_present()
    canvas._draw_frame_and_present()

    text = caplog.text
    assert text.count("bar_method") == 2  # one traceback => 2 mentions
    assert text.count("foo_method") == 2
    assert text.count("call-failed-but-test-passed") == 4
    assert text.count("(4)") == 1
    assert text.count("(5)") == 0

    assert text.count("spam_method") == 0
    assert text.count("intended-fail") == 0

    canvas._draw_frame_and_present()  # prints traceback
    canvas._draw_frame_and_present()  # prints short logs ...
    canvas._draw_frame_and_present()
    canvas._draw_frame_and_present()

    text = caplog.text
    assert text.count("bar_method") == 2  # one traceback => 2 mentions
    assert text.count("foo_method") == 2
    assert text.count("call-failed-but-test-passed") == 4

    assert text.count("spam_method") == 2
    assert text.count("intended-fail") == 4


class MyOffscreenCanvas(rendercanvas.BaseRenderCanvas):
    def __init__(self):
        super().__init__()
        self.frame_count = 0
        self.physical_size = 100, 100

    def _rc_get_present_methods(self):
        return {
            "bitmap": {
                "formats": ["rgba-u8"],
            }
        }

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        self.frame_count += 1
        self.array = np.frombuffer(data, np.uint8).reshape(data.shape)

    def get_pixel_ratio(self):
        return 1

    def get_logical_size(self):
        return self.get_physical_size()

    def get_physical_size(self):
        return self.physical_size


@mark.skipif(not can_use_wgpu_lib, reason="Needs wgpu lib")
def test_run_bare_canvas():
    """Test that a bare canvas does not error."""

    # This is (more or less) the equivalent of:
    #
    #     from rendercanvas.auto import RenderCanvas, loop
    #     canvas = RenderCanvas()
    #     loop.run()
    #
    # Note: loop.run() calls _draw_frame_and_present() in event loop.

    canvas = MyOffscreenCanvas()
    canvas._draw_frame_and_present()


@mark.skipif(not can_use_wgpu_lib, reason="Needs wgpu lib")
def test_simple_offscreen_canvas():
    import wgpu

    canvas = MyOffscreenCanvas()
    device = wgpu.gpu.request_adapter_sync().request_device_sync()
    present_context = canvas.get_context("wgpu")
    present_context.configure(device=device, format=None)

    def draw_frame():
        # Note: we deliberately obtain the texture, and only create the view
        # where the dict is constructed below. This covers the case where
        # begin_render_pass() has to prevent the texture-view-object from being
        # deleted before its native handle is passed to wgpu-native.
        current_texture = present_context.get_current_texture()
        command_encoder = device.create_command_encoder()
        render_pass = command_encoder.begin_render_pass(
            color_attachments=[
                {
                    "view": current_texture.create_view(),
                    "resolve_target": None,
                    "clear_value": (0, 1, 0, 1),
                    "load_op": wgpu.LoadOp.clear,
                    "store_op": wgpu.StoreOp.store,
                }
            ],
        )
        render_pass.end()
        device.queue.submit([command_encoder.finish()])

    assert canvas.frame_count == 0

    canvas.request_draw(draw_frame)

    # Draw 1
    canvas.force_draw()
    assert canvas.array.shape == (100, 100, 4)
    assert np.all(canvas.array[:, :, 0] == 0)
    assert np.all(canvas.array[:, :, 1] == 255)

    # Draw 2
    canvas.force_draw()
    assert canvas.array.shape == (100, 100, 4)
    assert np.all(canvas.array[:, :, 0] == 0)
    assert np.all(canvas.array[:, :, 1] == 255)

    # Change resolution
    canvas.physical_size = 120, 100

    # Draw 3
    canvas.force_draw()
    assert canvas.array.shape == (100, 120, 4)
    assert np.all(canvas.array[:, :, 0] == 0)
    assert np.all(canvas.array[:, :, 1] == 255)

    # Change resolution
    canvas.physical_size = 120, 140

    # Draw 4
    canvas.force_draw()
    assert canvas.array.shape == (140, 120, 4)
    assert np.all(canvas.array[:, :, 0] == 0)
    assert np.all(canvas.array[:, :, 1] == 255)

    # We now have four unique texture objects
    assert canvas.frame_count == 4


def test_canvas_base_events():
    c = rendercanvas.BaseRenderCanvas()

    # We test events extensively in another test module. This is just
    # to make sure that events are working for the base canvas.

    events = []

    def handler(event):
        events.append(event["value"])

    c.add_event_handler(handler, "key_down")
    c.submit_event({"event_type": "key_down", "value": 1})
    c.submit_event({"event_type": "key_down", "value": 2})

    def sync_flush(events):
        coro = events.flush()
        while True:
            try:
                coro.send(None)
            except StopIteration:
                break

    sync_flush(c._events)
    assert events == [1, 2]


if __name__ == "__main__":
    run_tests(globals())

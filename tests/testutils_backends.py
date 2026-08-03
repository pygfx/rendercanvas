"""
Some tests that can be run for different (GUI) backends.
"""

# ruff: noqa: N803, N806

import gc
import os
import time
import weakref
import signal
import threading

import numpy as np
from rendercanvas.utils.asyncs import sleep as async_sleep

from testutils import can_use_wgpu_lib
import pytest


# A list of generic backend test functions
BACKEND_TEST_FUNCS = []


def add_test_func(func):
    BACKEND_TEST_FUNCS.append(func)
    return func


class NativeHelper:
    def close_canvas(self, canvas):
        raise NotImplementedError()


def events_is_closed(canvas):
    if hasattr(canvas, "_subwidget"):
        return canvas._subwidget._events._closed
    else:
        return canvas._events._closed


# ==================== loop deletion


@add_test_func
def backend_loop_deletion1(RenderCanvas: type, loop, helper: NativeHelper):
    # Loops get gc'd when instantiated but not used.

    SomeLoop = loop.__class__

    loop = SomeLoop()

    assert loop._BaseLoop__state == "off"

    loop_ref = weakref.ref(loop)
    del loop
    gc.collect()
    gc.collect()

    assert loop_ref() is None


@add_test_func
def backend_loop_deletion2(RenderCanvas: type, loop, helper: NativeHelper):
    # Loops get gc'd when in ready state
    SomeLoop = loop.__class__

    async def foo():
        pass

    loop = SomeLoop()
    loop.add_task(foo)
    assert "ready" in repr(loop)

    loop_ref = weakref.ref(loop)
    del loop
    for _ in range(4):
        time.sleep(0.01)
        gc.collect()

    assert loop_ref() is None


@add_test_func
def backend_loop_deletion3(RenderCanvas: type, loop, helper: NativeHelper):
    # Loops get gc'd when closed after use
    SomeLoop = loop.__class__

    flag = []

    async def foo():
        flag.append(True)

    loop = SomeLoop()
    loop.add_task(foo)
    assert "ready" in repr(loop)
    loop.run()
    assert flag == [True]
    assert loop._BaseLoop__state == "off"

    loop_ref = weakref.ref(loop)
    del loop
    for _ in range(4):
        time.sleep(0.02)
        gc.collect()

    assert loop_ref() is None


# TODO: a test that makes sure that pending call_later's are cancelled when the loop is closed
# TODO: -> may need to refactor to focus fully on call_soon_threadsafe.


# ==================== running and closing


@add_test_func
def backend_run_loop_and_close_bc_no_canvases(
    RenderCanvas: type, loop, helper: NativeHelper
):
    # Run the loop without canvas; closes immediately

    loop.call_later(1.0, loop.stop)  # failsafe

    # TODO: also test pending call_soons etc. also see test_loop_lifetime_normal in test_loop.py

    t0 = time.perf_counter()
    loop.run()
    t1 = time.perf_counter()

    assert (t1 - t0) < 0.3
    assert loop._BaseLoop__state == "off"


@add_test_func
def backend_loop_detects_canvases(RenderCanvas: type, loop, helper: NativeHelper):
    # After all canvases are closed, it can take one tick before its detected.

    _canvas1 = RenderCanvas()
    assert len(loop.get_canvases()) == 1

    _canvas2 = RenderCanvas()
    _canvas3 = RenderCanvas()
    assert len(loop.get_canvases()) == 3

    # Call stop explicitly. Because we created some canvases, but never ran the
    # loops, they are in a 'ready' state, ready to move to the running state
    # when the loop-task starts running. For raw/asyncio/trio this is fine,
    # because cleanup will cancel all tasks. But for the QtLoop, the QTimer has
    # a reference to the callback, which refs asyncadapter.Task, which refs the
    # coroutine which refs the loop object. So there will not be any cleanup and
    # *this* loop will start running at the next test func.
    loop.stop()
    loop.stop()
    assert loop._BaseLoop__state == "off"


@add_test_func
def backend_run_loop_without_canvases(RenderCanvas: type, loop, helper: NativeHelper):
    # After all canvases are closed, it can take one tick before its detected.

    leeway = 0.20 if os.getenv("CI") else 0
    if "Qt" in loop.__class__.__name__ or "PySide" in loop.__class__.__name__:
        leeway = 0.10

    # The loop is in its stopped state, but it fires up briefly to do one tick

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.0 <= et < 0.15 + leeway
    assert loop._BaseLoop__state == "off"

    # Create a canvas and close it right away

    canvas1 = RenderCanvas()
    assert len(loop.get_canvases()) == 1
    canvas1.close()
    assert len(loop.get_canvases()) == 0

    # This time the loop is in its ready state, so it will actually
    # run for one tick for it to notice that all canvases are gone.

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.0 <= et < 0.15 + leeway
    assert loop._BaseLoop__state == "off"

    # Now its in its stopped state again

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.0 <= et < 0.15 + leeway
    assert loop._BaseLoop__state == "off"


@add_test_func
def backend_run_loop_and_close_canvases(RenderCanvas: type, loop, helper: NativeHelper):
    # After all canvases are closed, it can take one tick before its detected.

    leeway = 0.20 if os.getenv("CI") else 0

    canvas1 = RenderCanvas()
    canvas2 = RenderCanvas()

    loop.call_later(0.1, canvas1.close)
    loop.call_later(0.3, canvas2.close)

    t0 = time.time()
    print(loop)
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.25 < et < 0.50 + leeway

    assert events_is_closed(canvas1)
    assert events_is_closed(canvas2)
    assert loop._BaseLoop__state == "off"


@add_test_func
def backend_run_loop_and_close_by_loop_stop(
    RenderCanvas: type, loop, helper: NativeHelper
):
    # Close, then wait at most one tick to close canvases, and another to confirm close.

    leeway = 0.20 if os.getenv("CI") else 0

    canvas1 = RenderCanvas()

    loop.call_later(0.1, print, "hi from loop!")
    loop.call_later(0.3, loop.stop)

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.25 < et < 0.55 + leeway

    assert events_is_closed(canvas1)
    assert loop._BaseLoop__state == "off"


@add_test_func
def backend_run_loop_and_close_by_loop_stop_via_async(
    RenderCanvas: type, loop, helper: NativeHelper
):
    # Close using a coro

    leeway = 0.20 if os.getenv("CI") else 0

    canvas1 = RenderCanvas()

    async def stopper():
        await async_sleep(0.3)
        loop.stop()

    loop.add_task(stopper)

    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.25 < et < 0.55 + leeway

    assert events_is_closed(canvas1)
    assert loop._BaseLoop__state == "off"


@add_test_func
def backend_run_loop_and_close_by_del(RenderCanvas: type, loop, helper: NativeHelper):
    # Make the canvases be deleted by the gc.

    leeway = 0.20 if os.getenv("CI") else 0

    canvases = [RenderCanvas() for _ in range(2)]
    weak = [weakref.ref(c) for c in canvases]

    def print_refs():
        print([type(x) for x in gc.get_referrers(weak[0]())])
        print([x for x in gc.get_referrers(weak[0]())])

    loop.call_later(0.2, canvases.clear)
    loop.call_later(1.3, loop.stop)  # failsafe
    t0 = time.time()
    loop.run()
    et = time.time() - t0

    print(et)
    assert 0.15 < et < 0.55 + leeway, et

    assert loop._BaseLoop__state == "off"


@add_test_func
def backend_run_loop_and_interrupt(RenderCanvas: type, loop, helper: NativeHelper):
    # Interrupt, calls close, can take one tick to close canvases, and another to conform close.

    if RenderCanvas.__name__.startswith("Wx"):
        pytest.skip("wx seems to overload interrupt by a hard exit")

    leeway = 0.50 if os.getenv("CI") else 0

    canvas1 = RenderCanvas()

    loop.call_later(0.1, print, "hi from loop!")

    def interrupt_soon():
        time.sleep(0.3)
        signal.raise_signal(signal.SIGINT)

    t = threading.Thread(target=interrupt_soon)
    t.start()

    t0 = time.time()
    loop.run()
    et = time.time() - t0
    t.join()

    print(et)
    assert 0.25 < et < 0.55 + leeway

    assert events_is_closed(canvas1)
    assert loop._BaseLoop__state == "off"


@add_test_func
def backend_close_by_pressing_cross(RenderCanvas: type, loop, helper: NativeHelper):
    # Emulate the user pressing the cross

    canvas1 = RenderCanvas()
    canvas2 = RenderCanvas()

    loop.call_later(0.5, lambda: helper.close_canvas(canvas1))  # noqa: F821
    loop.call_later(0.6, lambda: helper.close_canvas(canvas2))  # noqa: F821
    loop.run()

    assert canvas1.get_closed()
    assert canvas2.get_closed()

    canvas_ref1 = weakref.ref(canvas1)
    canvas_ref2 = weakref.ref(canvas2)
    del canvas1, canvas2
    gc.collect()
    time.sleep(0.02)
    gc.collect()

    assert canvas_ref1() is None
    assert canvas_ref2() is None
    assert loop._BaseLoop__state == "off"


# ==================== Resizing


@add_test_func
def backend_sizing(RenderCanvas: type, loop, helper: NativeHelper):
    canvas = RenderCanvas(size=(640, 480))
    canvas._rc_gui_poll()

    lsize = canvas.get_logical_size()
    assert isinstance(lsize, tuple) and len(lsize) == 2
    assert isinstance(lsize[0], float) and isinstance(lsize[1], float)
    assert lsize == (640, 480)

    canvas.set_logical_size(700, 600)
    canvas._rc_gui_poll()

    lsize = canvas.get_logical_size()
    assert isinstance(lsize, tuple) and len(lsize) == 2
    assert isinstance(lsize[0], float) and isinstance(lsize[1], float)
    assert lsize == (700, 600)

    assert len(canvas.get_physical_size()) == 2
    assert isinstance(canvas.get_pixel_ratio(), float)

    # Close
    assert not canvas.get_closed()
    canvas.close()
    canvas._rc_gui_poll()
    assert canvas.get_closed()
    assert loop._BaseLoop__state == "off"


# ==================== Rendering


@add_test_func
def backend_render_bitmap(RenderCanvas: type, loop, helper: NativeHelper):
    canvas = RenderCanvas(size=(640, 480))
    ctx = canvas.get_bitmap_context()

    w, h = ctx.physical_size
    h4 = h // 4
    array = np.zeros((h, w, 4), np.uint8)
    array[0 * h4 : 1 * h4, :, 0] = 255
    array[1 * h4 : 2 * h4, :, 1] = 255
    array[2 * h4 : 3 * h4, :, 2] = 255
    array[:, :, 3] = 255

    @canvas.request_draw
    def draw():
        ctx.set_bitmap(array)

    loop.call_later(0.5, canvas.close)
    loop.run()

    assert canvas.get_closed()

    canvas_ref = weakref.ref(canvas)
    del canvas
    gc.collect()
    time.sleep(0.02)
    gc.collect()

    assert canvas_ref() is None
    assert loop._BaseLoop__state == "off"


@add_test_func
def backend_render_wgpu(RenderCanvas: type, loop, helper: NativeHelper):
    if not can_use_wgpu_lib:
        pytest.skip("Skipping tests that needs the wgpu lib")

    import wgpu

    canvas = RenderCanvas(size=(640, 480))

    device = wgpu.gpu.request_adapter_sync().request_device_sync()
    draw_frame1 = _get_draw_function(device, canvas)

    canvas.request_draw(draw_frame1)

    loop.call_later(0.5, canvas.close)
    loop.run()

    assert canvas.get_closed()

    canvas_ref = weakref.ref(canvas)
    del canvas
    gc.collect()
    time.sleep(0.02)
    gc.collect()

    assert canvas_ref() is None
    assert loop._BaseLoop__state == "off"


def _get_draw_function(device, canvas):
    import wgpu

    shader_source = """
    @vertex
    fn vs_main(@builtin(vertex_index) vertex_index : u32) -> @builtin(position) vec4<f32> {
        var positions: array<vec2<f32>, 3> = array<vec2<f32>, 3>(vec2<f32>(0.0, -0.5), vec2<f32>(0.5, 0.5), vec2<f32>(-0.5, 0.7));
        let p: vec2<f32> = positions[vertex_index];
        return vec4<f32>(p, 0.0, 1.0);
    }

    @fragment
    fn fs_main() -> @location(0) vec4<f32> {
        return vec4<f32>(1.0, 0.5, 0.0, 1.0);
    }
    """

    # Bindings and layout
    pipeline_layout = device.create_pipeline_layout(bind_group_layouts=[])

    shader = device.create_shader_module(code=shader_source)

    present_context = canvas.get_context("wgpu")
    render_texture_format = present_context.get_preferred_format(device.adapter)
    present_context.configure(device=device, format=render_texture_format)

    render_pipeline = device.create_render_pipeline(
        label="my-debug-pipeline",
        layout=pipeline_layout,
        vertex={
            "module": shader,
            "entry_point": "vs_main",
            "buffers": [],
        },
        primitive={
            "topology": wgpu.PrimitiveTopology.triangle_strip,
            "strip_index_format": wgpu.IndexFormat.uint32,
            "front_face": wgpu.FrontFace.ccw,
            "cull_mode": wgpu.CullMode.none,
        },
        depth_stencil=None,
        multisample={
            "count": 1,
            "mask": 0xFFFFFFFF,
            "alpha_to_coverage_enabled": False,
        },
        fragment={
            "module": shader,
            "entry_point": "fs_main",
            "targets": [
                {
                    "format": render_texture_format,
                    "blend": {
                        "color": {},  # use defaults
                        "alpha": {},  # use defaults
                    },
                },
            ],
        },
    )

    def draw_frame():
        current_texture_view = present_context.get_current_texture().create_view()
        command_encoder = device.create_command_encoder()
        assert current_texture_view.size
        ca = {
            "view": current_texture_view,
            "resolve_target": None,
            "clear_value": (0, 0, 0, 0),
            "load_op": wgpu.LoadOp.clear,
            "store_op": wgpu.StoreOp.store,
        }
        render_pass = command_encoder.begin_render_pass(
            color_attachments=[ca],
        )

        render_pass.set_pipeline(render_pipeline)
        render_pass.draw(4, 1, 0, 0)
        render_pass.end()
        device.queue.submit([command_encoder.finish()])

    return draw_frame

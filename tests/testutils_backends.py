"""
Some tests that can be run for different (GUI) backends.
"""

import gc
import time
import weakref
import importlib
import numpy as np

from testutils import can_use_wgpu_lib
import pytest


# A list of generic backend test functions
BACKEND_TEST_FUNCS = []


def import_canvas_class_and_loop(backend) -> tuple[type, object]:
    mod = importlib.import_module(f"rendercanvas.{backend}")
    return mod.RenderCanvas, mod.loop


@BACKEND_TEST_FUNCS.append
def canvas_close_by_canvas(backend):
    RenderCanvas, loop = import_canvas_class_and_loop(backend)  # noqa: N806

    canvas1 = RenderCanvas()
    canvas2 = RenderCanvas()

    loop.call_later(0.5, canvas1.close)
    loop.call_later(0.6, canvas2.close)
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


@BACKEND_TEST_FUNCS.append
def canvas_close_by_loop(backend):
    RenderCanvas, loop = import_canvas_class_and_loop(backend)  # noqa: N806

    canvas1 = RenderCanvas()
    canvas2 = RenderCanvas()

    loop.call_later(0.5, loop.stop)
    loop.run()

    assert canvas1.get_closed()
    assert canvas2.get_closed()


@BACKEND_TEST_FUNCS.append
def canvas_sizing(backend):
    RenderCanvas, _ = import_canvas_class_and_loop(backend)  # noqa: N806

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


@BACKEND_TEST_FUNCS.append
def canvas_render_bitmap(backend):
    RenderCanvas, loop = import_canvas_class_and_loop(backend)  # noqa: N806

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


@BACKEND_TEST_FUNCS.append
def canvas_render_wgpu(backend):
    if not can_use_wgpu_lib:
        pytest.skip("Skipping tests that needs the wgpu lib")

    import wgpu

    RenderCanvas, loop = import_canvas_class_and_loop(backend)  # noqa: N806

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

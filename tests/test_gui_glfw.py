"""
Test the canvas, and parts of the rendering that involves a canvas,
like the canvas context and surface texture.
"""

import os
import time
import weakref
import asyncio
import gc

from pytest import skip
from testutils import run_tests, can_use_glfw, can_use_wgpu_lib, is_pypy
# from renderutils import render_to_texture, render_to_screen


if not can_use_glfw or not can_use_wgpu_lib:
    skip("Skipping tests that need a window or the wgpu lib", allow_module_level=True)


def setup_module():
    import glfw

    glfw.init()


def teardown_module():
    import glfw
    from rendercanvas.glfw import poll_glfw_briefly

    poll_glfw_briefly()

    # Terminate; otherwise it gets in the way of tests for the Qt loop.
    glfw.terminate()


def test_is_canvas_base():
    from rendercanvas import BaseRenderCanvas
    from rendercanvas.glfw import RenderCanvas

    assert issubclass(RenderCanvas, BaseRenderCanvas)


def test_glfw_canvas_basics():
    """Create a window and check some of its behavior. No wgpu calls here."""

    import glfw
    from rendercanvas.glfw import RenderCanvas

    canvas = RenderCanvas()

    canvas.set_logical_size(300, 200)
    etime = time.time() + 0.1
    while time.time() < etime:
        glfw.poll_events()
    lsize = canvas.get_logical_size()
    assert isinstance(lsize, tuple) and len(lsize) == 2
    assert isinstance(lsize[0], float) and isinstance(lsize[1], float)
    assert lsize == (300.0, 200.0)

    assert len(canvas.get_physical_size()) == 2
    assert isinstance(canvas.get_pixel_ratio(), float)

    # Close
    assert not canvas.get_closed()
    canvas.close()
    glfw.poll_events()
    assert canvas.get_closed()


def test_glfw_canvas_del():
    from rendercanvas.glfw import RenderCanvas, loop

    aio_loop = asyncio.new_event_loop()
    loop_task = aio_loop.create_task(loop.run_async())

    def run_briefly():
        aio_loop.run_until_complete(asyncio.sleep(0.5))

    canvas = RenderCanvas()
    ref = weakref.ref(canvas)

    assert ref() is not None
    run_briefly()
    assert ref() is not None
    del canvas
    if is_pypy:
        gc.collect()  # force garbage collection for pypy
    assert ref() is None

    # Loop shuts down
    assert not loop_task.done()
    run_briefly()
    assert loop_task.done()


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


def test_glfw_canvas_render():
    """Render an orange square ... in a glfw window."""

    import wgpu
    from rendercanvas.glfw import RenderCanvas
    from rendercanvas.asyncio import loop

    aio_loop = asyncio.new_event_loop()
    loop_task = aio_loop.create_task(loop.run_async())

    def run_briefly():
        aio_loop.run_until_complete(asyncio.sleep(0.5))

    canvas = RenderCanvas(max_fps=9999, update_mode="ondemand")

    device = wgpu.gpu.request_adapter_sync().request_device_sync()
    draw_frame1 = _get_draw_function(device, canvas)

    allowed_frames = (1,)
    if os.getenv("CI"):
        allowed_frames = (1, 2, 3)

    frame_counter = 0

    def draw_frame2():
        nonlocal frame_counter
        frame_counter += 1
        draw_frame1()

    canvas.request_draw(draw_frame2)

    run_briefly()
    # There should have been exactly one draw now
    # This assumes ondemand scheduling mode
    assert frame_counter in allowed_frames
    frame_counter = 0

    # Ask for a lot of draws
    for i in range(5):
        canvas.request_draw()
    # Process evens for a while
    run_briefly()
    # We should have had just one draw
    assert frame_counter in allowed_frames
    frame_counter = 0

    # Change the canvas size
    canvas.set_logical_size(300, 200)
    canvas.set_logical_size(400, 300)
    # We should have had just one draw, but sometimes (more so on CI) we can have more
    run_briefly()
    assert frame_counter in allowed_frames
    frame_counter = 0

    # Stopping
    assert not loop_task.done()
    canvas.close()
    assert not loop_task.done()
    run_briefly()
    assert loop_task.done()


def _get_draw_function(device, canvas):
    import wgpu

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


if __name__ == "__main__":
    setup_module()
    run_tests(globals())
    teardown_module()

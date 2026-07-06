"""
Test the canvas, and parts of the rendering that involves a canvas,
like the canvas context and surface texture.

In contrast to the other test_backend_xx.py tests, this test is run when glfw is
available.
"""

import os
import weakref
import asyncio
import gc

import pytest
from testutils import run_tests, can_use_glfw, can_use_wgpu_lib, is_pypy
from testutils_backends import BACKEND_TEST_FUNCS, _get_draw_function


if not can_use_glfw:
    pytest.skip("Skipping tests that needs glfw", allow_module_level=True)

import glfw
# def setup_module():
#     import glfw
#     glfw.init()
#
# def teardown_module():
#     import glfw
#     from rendercanvas.glfw import poll_glfw_briefly
#     poll_glfw_briefly()
#     # Terminate; otherwise it gets in the way of tests for the Qt or wx loop.
#     glfw.terminate()


def test_is_canvas_classes():
    from rendercanvas.base import BaseRenderCanvas
    from rendercanvas.glfw import RenderCanvas, GlfwRenderCanvas

    assert GlfwRenderCanvas is RenderCanvas
    assert issubclass(RenderCanvas, BaseRenderCanvas)


def glfw_close(canvas):
    glfw.set_window_should_close(canvas._window, 1)


@pytest.mark.parametrize("backend", ["glfw"])
@pytest.mark.parametrize("func", BACKEND_TEST_FUNCS)
def test_backend_generic(func, backend):
    func(backend, close_func=glfw_close)


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

    aio_loop.close()


def test_glfw_canvas_render():
    """Render an orange square ... in a glfw window."""

    if not can_use_wgpu_lib:
        pytest.skip("Skipping tests that needs the wgpu lib")

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

    allowed_frames = (1, 2)
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

    aio_loop.close()


if __name__ == "__main__":
    run_tests(globals())

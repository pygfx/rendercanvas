"""
Test the offscreen canvas and some related mechanics.
"""

import os
import gc
import weakref

from testutils import is_pypy, run_tests


def test_offscreen_selection_using_env_var():
    from rendercanvas.offscreen import ManualOffscreenRenderCanvas

    ori = os.getenv("RENDERCANVAS_FORCE_OFFSCREEN")
    os.environ["RENDERCANVAS_FORCE_OFFSCREEN"] = "1"

    # We only need the func, but this triggers the auto-import
    from rendercanvas.auto import select_backend

    try:
        if not os.getenv("CI"):
            for value in ["", "0", "false", "False", "wut"]:
                os.environ["RENDERCANVAS_FORCE_OFFSCREEN"] = value
                module = select_backend()
                assert module.RenderCanvas is not ManualOffscreenRenderCanvas

        for value in ["1", "true", "True"]:
            os.environ["RENDERCANVAS_FORCE_OFFSCREEN"] = value
            module = select_backend()
            assert module.RenderCanvas is ManualOffscreenRenderCanvas

    finally:
        if ori is not None:
            os.environ["RENDERCANVAS_FORCE_OFFSCREEN"] = ori


def test_offscreen_selection_using_legacyt_env_var():
    from rendercanvas.offscreen import ManualOffscreenRenderCanvas

    ori1 = os.getenv("RENDERCANVAS_FORCE_OFFSCREEN")
    ori2 = os.getenv("WGPU_FORCE_OFFSCREEN")

    os.environ.pop("RENDERCANVAS_FORCE_OFFSCREEN", None)
    os.environ["WGPU_FORCE_OFFSCREEN"] = "1"

    # We only need the func, but this triggers the auto-import
    from rendercanvas.auto import select_backend

    try:
        if not os.getenv("CI"):
            for value in ["", "0", "false", "False", "wut"]:
                os.environ["WGPU_FORCE_OFFSCREEN"] = value
                module = select_backend()
                assert module.RenderCanvas is not ManualOffscreenRenderCanvas

        for value in ["1", "true", "True"]:
            os.environ["WGPU_FORCE_OFFSCREEN"] = value
            module = select_backend()
            assert module.RenderCanvas is ManualOffscreenRenderCanvas

    finally:
        if ori1 is not None:
            os.environ["RENDERCANVAS_FORCE_OFFSCREEN"] = ori1
        if ori2 is not None:
            os.environ["WGPU_FORCE_OFFSCREEN"] = ori2


def test_offscreen_event_loop():
    """Check that the event loop handles queued tasks and then returns."""
    # Note: if this test fails, it may run forever, so it's a good idea to have a timeout on the CI job or something

    from rendercanvas.offscreen import loop

    ran = False

    def check():
        nonlocal ran
        ran = True

    loop.call_later(0, check)
    loop.run()

    assert ran


def test_offscreen_canvas_del():
    from rendercanvas.offscreen import RenderCanvas

    canvas = RenderCanvas()
    ref = weakref.ref(canvas)

    assert ref() is not None
    del canvas
    if is_pypy:
        gc.collect()
    assert ref() is None


if __name__ == "__main__":
    run_tests(globals())

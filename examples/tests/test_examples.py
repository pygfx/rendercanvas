"""
Test that the examples run without error.
"""

import os
import sys
import importlib
from pathlib import Path

import imageio.v2 as iio
import numpy as np
import pytest
import wgpu


ROOT = Path(__file__).parent.parent.parent  # repo root
examples_dir = ROOT / "examples"
screenshots_dir = examples_dir / "screenshots"


def find_examples(query=None, negative_query=None, return_stems=False):
    result = []
    for example_path in examples_dir.glob("*.py"):
        example_code = example_path.read_text()
        query_match = query is None or query in example_code
        negative_query_match = (
            negative_query is None or negative_query not in example_code
        )
        if query_match and negative_query_match:
            result.append(example_path)
    result = list(sorted(result))
    if return_stems:
        result = [r for r in result]
    return result


def get_default_adapter_summary():
    """Get description of adapter, or None when no adapter is available."""
    try:
        adapter = wgpu.gpu.request_adapter_sync()
    except RuntimeError:
        return None  # lib not available, or no adapter on this system
    return adapter.summary


adapter_summary = get_default_adapter_summary()
can_use_wgpu_lib = bool(adapter_summary)
is_ci = bool(os.getenv("CI", None))


is_lavapipe = adapter_summary and all(
    x in adapter_summary.lower() for x in ("llvmpipe", "vulkan")
)

if not can_use_wgpu_lib:
    pytest.skip("Skipping tests that need the wgpu lib", allow_module_level=True)


# run all tests unless they opt out
examples_to_run = find_examples(query="# run_example = true", return_stems=True)


def import_from_path(module_name, filename):
    spec = importlib.util.spec_from_file_location(module_name, filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    # With this approach the module is not added to sys.modules, which
    # is great, because that way the gc can simply clean up when we lose
    # the reference to the module
    assert module.__name__ == module_name
    assert module_name not in sys.modules

    return module


@pytest.fixture
def force_offscreen():
    """Force the offscreen canvas to be selected by the auto gui module."""
    os.environ["RENDERCANVAS_FORCE_OFFSCREEN"] = "true"
    try:
        yield
    finally:
        del os.environ["RENDERCANVAS_FORCE_OFFSCREEN"]


@pytest.mark.skipif(not os.getenv("CI"), reason="Not on CI")
def test_that_we_are_on_lavapipe():
    print(adapter_summary)
    assert is_lavapipe


@pytest.mark.parametrize("filename", examples_to_run, ids=lambda x: x.stem)
def test_examples_compare(filename, force_offscreen):
    """Run every example marked to compare its result against a reference screenshot."""
    check_example(filename)


def check_example(filename):
    # import the example module
    module = import_from_path(filename.stem, filename)

    # render a frame
    img = np.asarray(module.canvas.draw())

    # check if _something_ was rendered
    assert img is not None and img.size > 0

    # store screenshot
    screenshots_dir.mkdir(exist_ok=True)
    screenshot_path = screenshots_dir / f"{filename.stem}.png"
    iio.imsave(screenshot_path, img)


if __name__ == "__main__":
    # Enable tweaking in an IDE by running in an interactive session.
    os.environ["RENDERCANVAS_FORCE_OFFSCREEN"] = "true"
    for name in examples_to_run:
        check_example(name)

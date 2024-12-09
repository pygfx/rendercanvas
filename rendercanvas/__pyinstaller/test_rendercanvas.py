script = """
# The script part
import sys
import importlib

from rendercanvas.auto import RenderCanvas

if "glfw" not in RenderCanvas.__name__.lower():
    raise RuntimeError(f"Expected a glfw canvas, got {RenderCanvas.__name__}")

# The test part
if "is_test" in sys.argv:
    included_modules = [
        "rendercanvas.glfw",
        "rendercanvas.offscreen",
        "glfw",
        "asyncio"
    ]
    excluded_modules = [
        "PySide6.QtGui",
        "PyQt6.QtGui",
        "trio",
    ]
    for module_name in included_modules:
        importlib.import_module(module_name)
    for module_name in excluded_modules:
        try:
            importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        raise RuntimeError(module_name + " is not supposed to be importable.")
"""


def test_pyi_rendercanvas(pyi_builder):
    pyi_builder.test_source(script, app_args=["is_test"])


# We could also test the script below, but it's not that interesting since it uses direct imports.
# To safe CI-time we don't actively test it.
script_qt = """
import sys
import importlib

import PySide6
from rendercanvas.qt import RenderCanvas

assert "qt" in RenderCanvas.__name__.lower()
"""

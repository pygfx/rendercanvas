"""
Cube qt
-------

Run a wgpu example on the Qt backend.

Works with either PySide6, PyQt6, PyQt5 or PySide2.
"""

# ruff: noqa: E402

import importlib

# The `rendercanvas.qt` module checks what Qt libs is imported, so we need to import that first.
# For the sake of making this example Just Work, we try multiple Qt libs
for lib in ("PySide6", "PyQt6", "PySide2", "PyQt5"):
    try:
        QtWidgets = importlib.import_module(".QtWidgets", lib)
        break
    except ModuleNotFoundError:
        pass


from rendercanvas.qt import RenderCanvas, loop
from rendercanvas.utils.cube import setup_drawing_sync


canvas = RenderCanvas(title=f"The wgpu cube example on {lib}", update_mode="continuous")
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)


if __name__ == "__main__":
    loop.run()

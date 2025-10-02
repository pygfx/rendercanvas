[![CI](https://github.com/pygfx/rendercanvas/workflows/CI/badge.svg)](https://github.com/pygfx/rendercanvas/actions)
[![Documentation Status](https://readthedocs.org/projects/rendercanvas/badge/?version=stable)](https://rendercanvas.readthedocs.io)
[![PyPI version](https://badge.fury.io/py/rendercanvas.svg)](https://badge.fury.io/py/rendercanvas)
[![EffVer Versioning](https://img.shields.io/badge/version_scheme-EffVer-0097a7)](https://jacobtomlinson.dev/effver)

<h1 align="center"><img src="https://github.com/user-attachments/assets/74ddfc1e-03ae-4965-afe9-8697ec4614b5" height="128"><br>rendercanvas</h1>

One canvas API, multiple backends 🚀

<div>
  <img width=354 src='https://github.com/user-attachments/assets/42656d13-0d81-47dd-b9c7-d76da8cfa6c1' />
  <img width=354 src='https://github.com/user-attachments/assets/af8eefe0-4485-4daf-9fbd-36710e44f07c' />
</div>

*This project is part of [pygfx.org](https://pygfx.org)*


## Introduction

See how the two windows above look the same? That's the idea; they also look the
same to the code that renders to them. Yet, the GUI systems are very different
(Qt vs glfw in this case). Now that's a powerful abstraction!

Coming from `wgpu.gui`? Check [from_wgpu_canvas.md](from_wgpu_canvas.md).


## Purpose

* Provide a generic canvas API to render to.
* Provide an event loop for scheduling events and draws.
* Provide a simple but powerful event system with standardized event objects.
* Provide various canvas implementations:
  * One that is light and easily installed (glfw).
  * For various GUI libraries (e.g. qt and wx), so visuzalizations can be embedded in a GUI.
  * For specific platforms (e.g. Jupyter, browser).


The main use-case is rendering with [wgpu](https://github.com/pygfx/wgpu-py),
but ``rendercanvas``can be used by anything that can render based on a window-id or
by producing bitmap images.


## Installation

```
pip install rendercanvas
```

To have at least one backend, we recommend:
```
pip install rendercanvas glfw
```

## Usage

Also see the [online documentation](https://rendercanvas.readthedocs.io) and the [examples](https://github.com/pygfx/rendercanvas/tree/main/examples).

A minimal example that renders noise:
```py
import numpy as np
from rendercanvas.auto import RenderCanvas, loop

canvas = RenderCanvas(update_mode="continuous")
context = canvas.get_context("bitmap")

@canvas.request_draw
def animate():
    w, h = canvas.get_logical_size()
    bitmap = np.random.uniform(0, 255, (h, w)).astype(np.uint8)
    context.set_bitmap(bitmap)

loop.run()
```

Run wgpu visualizations:
```py
from rendercanvas.auto import RenderCanvas, loop
from rendercanvas.utils.cube import setup_drawing_sync


canvas = RenderCanvas(
    title="The wgpu cube example on $backend", update_mode="continuous"
)
draw_frame = setup_drawing_sync(canvas)
canvas.request_draw(draw_frame)

loop.run()
````

Embed in a Qt application:
```py
from PySide6 import QtWidgets
from rendercanvas.qt import QRenderWidget

class Main(QtWidgets.QWidget):

    def __init__(self):
        super().__init__()

        splitter = QtWidgets.QSplitter()
        self.canvas = QRenderWidget(splitter)
        ...


app = QtWidgets.QApplication([])
main = Main()
app.exec()
```

## Async or not async

We support both; a render canvas can be used in a fully async setting using e.g. Asyncio or Trio, or in an event-drived framework like Qt.
If you like callbacks, ``loop.call_later()`` always works. If you like async, use ``loop.add_task()``. Event handlers can always be async.
See the [docs on async](https://rendercanvas.readthedocs.io/stable/start.html#async) for details.


## License

This code is distributed under the 2-clause BSD license.


## Developers

* Clone the repo.
* Install `rendercanvas` and developer deps using `pip install -e .[dev]`.
* Use `ruff format` to apply autoformatting.
* Use `ruff check` to check for linting errors.
* Optionally, if you install [pre-commit](https://github.com/pre-commit/pre-commit/) hooks with `pre-commit install`, lint fixes and formatting will be automatically applied on `git commit`.
* Use `pytest tests` to run the tests.
* Use `pytest examples` to run a subset of the examples.


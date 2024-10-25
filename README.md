[![CI](https://github.com/pygfx/rendercanvas/workflows/CI/badge.svg)](https://github.com/pygfx/rendercanvas/actions)
[![Documentation Status](https://readthedocs.org/projects/rendercanvas/badge/?version=stable)](https://rendercanvas.readthedocs.io)
[![PyPI version](https://badge.fury.io/py/rendercanvas.svg)](https://badge.fury.io/py/rendercanvas)


# rendercanvas

One canvas API, multiple backends 🚀

<div>
  <img width=354 src='https://github.com/user-attachments/assets/42656d13-0d81-47dd-b9c7-d76da8cfa6c1' />
  <img width=354 src='https://github.com/user-attachments/assets/af8eefe0-4485-4daf-9fbd-36710e44f07c' />
</div>


## Introduction

See how the two windows above look the same? That's the idea; they also look the
same to the code that renders to them. Yet, the GUI systems are very different
(Qt vs glfw in this case). Now that's a powerful abstraction!


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
by producing rgba images.


## Installation

```
pip install rendercanvas
```

To have at least one GUI backend, we recommend:
```
pip install rendercanvas glfw
```

## Usage

Also see the [online documentation](https://rendercanvas.readthedocs.io) and the [examples](https://github.com/pygfx/rendercanvas/tree/main/examples).

```py
# Select either the glfw, qt or jupyter backend
from rendercanvas.auto import WgpuCanvas, loop

# Visualizations can be embedded as a widget in a Qt application.
# Supported qt libs are PySide6, PyQt6, PySide2 or PyQt5.
from rendercanvas.pyside6 import QWgpuWidget


# Now specify what the canvas should do on a draw
TODO

```


## License

This code is distributed under the 2-clause BSD license.


## Developers

* Clone the repo.
* Install `rendercanvas` and developer deps using `pip install -e .[dev]`.
* Use `ruff format` to apply autoformatting.
* Use `ruff check` to check for linting errors.
* Optionally, if you install [pre-commit](https://github.com/pre-commit/pre-commit/) hooks with `pre-commit install`, lint fixes and formatting will be automatically applied on `git commit`.
* Use `pytest tests` to run the tests.

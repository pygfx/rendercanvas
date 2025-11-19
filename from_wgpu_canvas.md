# Migrating from wgpu.gui.WgpuCanvas

This project was spun out of wgpu-py, and has evolved to meet our requirements for update-propagation and more.
This document lists all the changes w.r.t. the last version of the canvas in wgpu-py.

## Changes

*Let me know if I missed any!*

* `WgpuCanvas` -> `RenderCanvas`.
* `run` -> `loop.run()`.
* `call_later` -> `loop.call_later`.
* `canvas.is_closed()` -> `canvas.get_closed()`.
* Instead of `canvas.get_context()`, use `canvas.get_wgpu_context()` (or `canvas.get_context('bitmap')`).


## Improvements

* Overall cleaner code, more tests, better docs.
* Support for contexts other than wgpu.
* Bitmap rendering via builtin`canvas.get_bitmap_context()`.
* Handling of sigint (ctrl+c).
* Support for Trio.
* Support for async event handlers.
* Support for running async functions via `loop.add_task()`.
* Simpler Qt lib selection with `from rendercanvas.pyside6 import RenderCanvas`.
* Generic scheduling system with modes "ondemand", "continious", "fastest".


## By example

In wgpu-py:
```py
from wgpu.gui.auto import WgpuCanvas, run

...

run()
```

In rendercanvas:
```py
from rendercanvas.auto import RenderCanvas, loop

...

loop.run()
```

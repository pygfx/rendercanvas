Backends
========

Overview
--------

The table below gives an overview of the names in the different ``rendercanvas`` backend modules.

.. list-table::

    *   - **backend module**
        - **names**
        - **purpose**
    *   - ``auto``
        - | ``RenderCanvas``
          | ``loop``
        - | Select a backend automatically.
    *   - ``glfw``
        - | ``GlfwRenderCanvas``
          | ``RenderCanvas`` (alias)
          | ``loop`` (an ``AsyncioLoop``)
        - | A lightweight backend.
    *   - ``jupyter``
        - | ``JupyterRenderCanvas``
          | ``RenderCanvas`` (alias)
          | ``loop`` (an ``AsyncioLoop``)
        - | Integrate in Jupyter notebook / lab.
    *   - ``offscreen``
        - | ``OffscreenRenderCanvas``
          | ``RenderCanvas`` (alias)
          | ``loop`` (a ``StubLoop``)
        - | For offscreen rendering.
    *   - ``qt``
        - | ``QRenderCanvas`` (toplevel)
          | ``RenderCanvas`` (alias)
          | ``QRenderWidget`` (subwidget)
          | ``QtLoop``
          | ``loop``
        - | Create a standalone canvas using Qt, or
          | integrate a render canvas in a Qt application.
    *   - ``wx``
        - | ``WxRenderCanvas`` (toplevel)
          | ``RenderCanvas`` (alias)
          | ``WxRenderWidget`` (subwidget)
          | ``WxLoop``
          | ``loop``
        - | Create a standalone canvas using wx, or
          | integrate a render canvas in a wx application.
    *   - ``pyodide``
        - | ``PyodideRenderCanvas`` (toplevel)
          | ``RenderCanvas`` (alias)
          | ``loop`` (an ``AsyncioLoop``)
        - | Backend when Python is running in the browser,
          | via Pyodide or PyScript.


There are also three loop-backends. These are mainly intended for use with the glfw backend:

.. list-table::

    *   - **backend module**
        - **names**
        - **purpose**
    *   - ``raw``
        - | ``RawLoop``
          | ``loop``
        - | Provide a pure Python event loop.
    *   - ``asyncio``
        - | ``AsyncoLoop``
          | ``loop``
        - | Provide a generic loop based on Asyncio. Recommended.
    *   - ``trio``
        - | ``TrioLoop``
          | ``loop``
        - | Provide a loop based on Trio.


The auto backend
-----------------

Generally the best approach for examples and small applications is to use the
automatically selected backend. This ensures that the code is portable
across different machines and environments. Importing from ``rendercanvas.auto`` selects a
suitable backend depending on the environment and more. See
:ref:`interactive_use` for details.

.. code-block:: py

    from rendercanvas.auto import RenderCanvas, loop

    canvas = RenderCanvas(title="Example")
    canvas.request_draw(your_draw_function)

    loop.run()


Support for GLFW
----------------

`GLFW <https://github.com/FlorianRhiem/pyGLFW>`_ is a lightweight windowing toolkit.
Install it with ``pip install glfw``. The preferred approach is to use the auto backend,
but you can replace ``from rendercanvas.auto`` with ``from rendercanvas.glfw`` to force using GLFW.

.. code-block:: py

    from rendercanvas.glfw import RenderCanvas, loop

    canvas = RenderCanvas(title="Example")
    canvas.request_draw(your_draw_function)

    loop.run()


By default, the ``glfw`` backend uses an event-loop based on asyncio. But you can also select e.g. trio:

.. code-block:: py

    from rendercanvas.glfw import RenderCanvas
    from rendercanvas.trio import loop

    # Use another loop than the default
    RenderCanvas.select_loop(loop)

    canvas = RenderCanvas(title="Example")
    canvas.request_draw(your_draw_function)

    async def main():
        .. do your trio stuff
        await loop.run_async()

    trio.run(main)


Support for Qt
--------------

RenderCanvas has support for PyQt5, PyQt6, PySide2 and PySide6.
For a toplevel widget, the ``rendercanvas.qt.RenderCanvas`` class can be imported. If you want to
embed the canvas as a subwidget, use ``rendercanvas.qt.QRenderWidget`` instead.

Importing ``rendercanvas.qt`` detects what qt library is currently imported:

.. code-block:: py

    # Import Qt first, otherwise rendercanvas does not know what qt-lib to use
    from PySide6 import QtWidgets

    from rendercanvas.qt import RenderCanvas  # use this for top-level windows
    from rendercanvas.qt import QRenderWidget  # use this for widgets in you application

    app = QtWidgets.QApplication([])

    # Instantiate the canvas
    canvas = RenderCanvas(title="Example")

    # Tell the canvas what drawing function to call
    canvas.request_draw(your_draw_function)

    app.exec_()


Alternatively, you can select the specific qt library to use, making it easy to e.g. test an example on a specific Qt library.

.. code-block:: py

    from rendercanvas.pyside6 import RenderCanvas, loop

    # Instantiate the canvas
    canvas = RenderCanvas(title="Example")

    # Tell the canvas what drawing function to call
    canvas.request_draw(your_draw_function)

    loop.run()  # calls app.exec_()


It is technically possible to e.g. use a ``glfw`` canvas with the Qt loop. However, this is not recommended because Qt gets confused in the presence of other windows and may hang or segfault.
But the other way around, running a Qt canvas in e.g. the trio loop, works fine:

.. code-block:: py

    from rendercanvas.pyside6 import RenderCanvas
    from rendercanvas.trio import loop

    # Use another loop than the default
    RenderCanvas.select_loop(loop)

    canvas = RenderCanvas(title="Example")
    canvas.request_draw(your_draw_function)

    trio.run(loop.run_async)


There are known issue with Qt widgets that render directly to screen (i.e. widgets that obtain ``widget.winId()``),
related to how they interact with other widgets and in docks.
If you encounter such issues, consider using the bitmap present-method. That way, the rendering happens
off-screen, and is than provided to Qt as an image. This is a safer approach, albeit lowers the performance (FPS)
somewhat when the render area is large.

.. code-block:: py

    widget = QRenderWidget(present_method="bitmap")


Support for wx
--------------

RenderCanvas has support for wxPython. However, because of wx's specific behavior, this backend is less well tested than the other backends.
For a toplevel widget, the ``rendercanvas.wx.RenderCanvas`` class can be imported. If you want to
embed the canvas as a subwidget, use ``rendercanvas.wx.RenderWidget`` instead.


.. code-block:: py

    import wx
    from rendercanvas.wx import RenderCanvas

    app = wx.App()

    # Instantiate the canvas
    canvas = RenderCanvas(title="Example")

    # Tell the canvas what drawing function to call
    canvas.request_draw(your_draw_function)

    app.MainLoop()


Support for offscreen
---------------------

You can also use a "fake" canvas to draw offscreen and get the result as a numpy array.
Note that you can render to a texture without using any canvas
object, but in some cases it's convenient to do so with a canvas-like API.

.. autoclass:: rendercanvas.offscreen.OffscreenRenderCanvas
    :members:

.. code-block:: py

    from rendercanvas.offscreen import RenderCanvas

    # Instantiate the canvas
    canvas = RenderCanvas(size=(500, 400), pixel_ratio=1)

    # ...

    # Tell the canvas what drawing function to call
    canvas.request_draw(your_draw_function)

    # Perform a draw
    array = canvas.draw()  # numpy array with shape (400, 500, 4)


Support for Jupyter lab and notebook
------------------------------------

RenderCanvas can be used in Jupyter lab and the Jupyter notebook. This canvas
is based on `jupyter_rfb <https://github.com/vispy/jupyter_rfb>`_, an ipywidget
subclass implementing a remote frame-buffer. There are also some `wgpu examples <https://jupyter-rfb.readthedocs.io/en/stable/examples/>`_.

.. code-block:: py

    # from rendercanvas.jupyter import RenderCanvas  # Direct approach
    from rendercanvas.auto import RenderCanvas  # also works, because rendercanvas detects Jupyter

    canvas = RenderCanvas()

    # ... rendering code

    canvas  # Use as cell output


Support for Pyodide
-------------------

When Python is running in the browser using Pyodide, the auto backend selects
the ``rendercanvas.pyodide.PyodideRenderCanvas`` class. This backend requires no
additional dependencies. Currently only presenting a bitmap is supported, as
shown in the examples :doc:`noise.py <gallery/noise>` and :doc:`snake.py<gallery/snake>`.
Support for wgpu is underway.

An HTMLCanvasElement is assumed to be present in the
DOM. By default it connects to the canvas with id "canvas", but a
different id or element can also be provided using ``RenderCanvas(canvas_element)``.

An example using PyScript (which uses Pyodide):

.. code-block:: html

    <!doctype html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width,initial-scale=1.0">
        <script type="module" src="https://pyscript.net/releases/2025.11.1/core.js"></script>
    </head>
    <body>
        <canvas id='canvas' style="background:#aaa; width: 640px; height: 480px;"></canvas>
        <br>
        <script type="py" src="yourcode.py" config='{"packages": ["numpy", "sniffio", "rendercanvas"]}'>
        </script>
    </body>
    </html>


An example using Pyodide directly:

.. code-block:: html

    <!DOCTYPE html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width,initial-scale=1.0">
        <script src="https://cdn.jsdelivr.net/pyodide/v0.29.0/full/pyodide.js"></script>
    </head>
    <body>
        <canvas id="canvas" width="640" height="480"></canvas>
        <script type="text/javascript">
            async function main(){
                pythonCode = `
                    # Use python script as normally
                    import numpy as np
                    from rendercanvas.auto import RenderCanvas, loop

                    canvas = RenderCanvas()
                    context = canvas.get_bitmap_context()
                    data = np.random.uniform(127, 255, size=(24, 32, 4)).astype(np.uint8)

                    @canvas.request_draw
                    def animate():
                        context.set_bitmap(data)
                `
            // load Pyodide and install Rendercanvas
            let pyodide = await loadPyodide();
            await pyodide.loadPackage("micropip");
            const micropip = pyodide.pyimport("micropip");
            await micropip.install("numpy");
            await micropip.install("sniffio");
            await micropip.install("rendercanvas");
            // have to call as runPythonAsync
            pyodide.runPythonAsync(pythonCode);
            }
        main();
        </script>
    </body>
    </html>


.. _env_vars:

Selecting a backend with env vars
---------------------------------

The automatic backend selection can be influenced with the use of environment
variables. This makes it possible to e.g. create examples using the
auto-backend, and allow these examples to run on CI with the offscreen backend.
Note that once ``rendercanvas.auto`` is imported, the selection has been made,
and importing it again always yields the same backend.

* ``RENDERCANVAS_BACKEND``: Set the name of the backend that the auto-backend should select. Case insensituve.
* ``RENDERCANVAS_FORCE_OFFSCREEN``: force the auto-backend to select the offscreen canvas, ignoring the above env var. Truethy values are '1', 'true', and 'yes'.

Rendercanvas also supports the following env vars for backwards compatibility, but only when the corresponding ``RENDERCANVAS_`` env var is unset or an empty string:

* ``WGPU_GUI_BACKEND``:  legacy alias.
* ``WGPU_FORCE_OFFSCREEN``: legacy alias.


.. _interactive_use:

Interactive use
---------------

The rendercanvas backends are designed to support interactive use. Firstly, this is
realized by automatically selecting the appropriate backend. Secondly, the
``loop.run()`` method (which normally enters the event-loop) does nothing in an
interactive session.

Many interactive environments have some sort of GUI support, allowing the repl
to stay active (i.e. you can run new code), while the GUI windows is also alive.
In rendercanvas we try to select the GUI that matches the current environment.

On ``jupyter notebook`` and ``jupyter lab`` the jupyter backend (i.e.
``jupyter_rfb``) is normally selected. When you are using ``%gui qt``, rendercanvas will
honor that and use Qt instead.

On ``jupyter console`` and ``qtconsole``, the kernel is the same as in ``jupyter notebook``,
making it (about) impossible to tell that we cannot actually use
ipywidgets. So it will try to use ``jupyter_rfb``, but cannot render anything.
It's therefore advised to either use ``%gui qt`` or set the ``RENDERCANVAS_BACKEND`` env var
to "glfw". The latter option works well, because these kernels *do* have a
running asyncio event-loop!

On other environments that have a running ``asyncio`` loop, the glfw backend is
preferred. E.g on ``ptpython --asyncio``.

On IPython (the old-school terminal app) it's advised to use ``%gui qt`` (or
``--gui qt``). It seems not possible to have a running asyncio loop here.

On IDE's like Spyder or Pyzo, rendercanvas detects the integrated GUI, running on
glfw if asyncio is enabled or Qt if a qt app is running.

On an interactive session without GUI support, one must call ``loop.run()`` to make
the canvases interactive. This enters the main loop, which prevents entering new
code. Once all canvases are closed, the loop returns. If you make new canvases
afterwards, you can call ``loop.run()`` again. This is similar to ``plt.show()`` in Matplotlib.

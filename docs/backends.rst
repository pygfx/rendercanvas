Backends
========

The auto backend
-----------------

Generally the best approach for examples and small applications is to use the
automatically selected backend. This ensures that the code is portable
across different machines and environments. Using ``rendercanvas.auto`` selects a
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


Support for Qt
--------------

RenderCanvas has support for PyQt5, PyQt6, PySide2 and PySide6. It detects what
qt library you are using by looking what module has been imported.
For a toplevel widget, the ``rendercanvas.qt.RenderCanvas`` class can be imported. If you want to
embed the canvas as a subwidget, use ``rendercanvas.qt.QRenderWidget`` instead.

.. code-block:: py

    # Import any of the Qt libraries before importing the RenderCanvas.
    # This way rendercanvas knows which Qt library to use.
    from PySide6 import QtWidgets
    from rendercanvas.qt import RenderCanvas  # use this for top-level windows
    from rendercanvas.qt import QRenderWidget  # use this for widgets in you application

    app = QtWidgets.QApplication([])

    # Instantiate the canvas
    canvas = RenderCanvas(title="Example")

    # Tell the canvas what drawing function to call
    canvas.request_draw(your_draw_function)

    app.exec_()


Support for wx
--------------

RenderCanvas has support for wxPython.
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
running asyncio event loop!

On other environments that have a running ``asyncio`` loop, the glfw backend is
preferred. E.g on ``ptpython --asyncio``.

On IPython (the old-school terminal app) it's advised to use ``%gui qt`` (or
``--gui qt``). It seems not possible to have a running asyncio loop here.

On IDE's like Spyder or Pyzo, rendercanvas detects the integrated GUI, running on
glfw if asyncio is enabled or Qt if a qt app is running.

On an interactive session without GUI support, one must call ``loop.run()`` to make
the canvases interactive. This enters the main loop, which prevents entering new
code. Once all canvases are closed, the loop returns. If you make new canvases
afterwards, you can call ``run()`` again. This is similar to ``plt.show()`` in Matplotlib.

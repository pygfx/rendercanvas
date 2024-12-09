Getting started
===============

Installation
------------

You can install ``rendercanvas`` via pip (or most other Python package managers).
Python 3.9 or higher is required. Pypy is supported.

.. code-block:: bash

    pip install rendercanvas


Multiple backends are supported, including multiple GUI libraries, but none of these are installed by default. See :doc:`backends` for details.

We recommend also installing `GLFW <https://github.com/FlorianRhiem/pyGLFW>`_, so that you have a lightweight backend available from the start:

.. code-block:: bash

    pip install rendercanvas glfw


Creating a canvas
-----------------

In general, it's easiest to let ``rendercanvas`` select a backend automatically:

.. code-block:: py

    from rendercanvas.auto import RenderCanvas, loop

    canvas = RenderCanvas()

    # ... code to setup the rendering

    loop.run()  # Enter main-loop


Rendering to the canvas
-----------------------

The above just shows a grey window. We want to render to it by using wgpu or by generating images.

Depending on the tool you'll use to render to the canvas, you need a different context.
The purpose of the context is to present the rendered result to the canvas.
There are currently two types of contexts.

Rendering using bitmaps:

.. code-block:: py

    context = canvas.get_context("bitmap")

    @canvas.request_draw
    def animate():
        # ... produce an image, represented with e.g. a numpy array
        context.set_bitmap(image)

Rendering with wgpu:

.. code-block:: py

    context = canvas.get_context("wgpu")
    context.configure(device)

    @canvas.request_draw
    def animate():
        texture = context.get_current_texture()
        # ... wgpu code



.. _async:

Async
-----

A render canvas can be used in a fully async setting using e.g. Asyncio or Trio, or in an event-drived framework like Qt.
If you like callbacks, ``loop.call_later()`` always works. If you like async, use ``loop.add_task()``. Event handlers can always be async.

If you make use of async functions (co-routines), and want to keep your code portable accross
different canvas backends, restrict your use of async features to ``sleep``  and ``Event``;
these are the only features currently implemened in our async adapter utility.
We recommend importing these from :doc:`rendercanvas.utils.asyncs <utils_asyncs>` or use ``sniffio`` to detect the library that they can be imported from.

On the other hand, if you know your code always runs on the asyncio loop, you can fully make use of ``asyncio``. Dito for Trio.


Freezing apps
-------------

In ``rendercanvas`` a PyInstaller-hook is provided to help simplify the freezing process. This hook requires
PyInstaller version 4+. Our hook includes ``glfw`` when it is available, so code using ``rendercanvas.auto``
should Just Work.

Note that PyInstaller needs ``rendercanvas`` to be installed in `site-packages` for
the hook to work (i.e. it seems not to work with a ``pip -e .`` dev install).

Getting started
===============

Installation
------------

You can install ``rendercanvas`` via pip or similar.
Python 3.9 or higher is required. Pypy is supported.

.. code-block:: bash

    pip install rendercanvas


Since most users will want to render something to screen, we recommend installing GLFW as well:

.. code-block:: bash

    pip install rendercanvas glfw


Multiple backends are supported, including multiple GUI libraries, but none of these are installed by default. See :doc:`backends` for details.


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
The purpose of the context to present the rendered result to the canvas.
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


Freezing apps
-------------

In ``rendercanvas`` a PyInstaller-hook is provided to help simplify the freezing process. This hook requires
PyInstaller version 4+. Our hook includes ``glfw`` when it is available, so code using ``rendercanvas.auto``
should Just Work.

Note that PyInstaller needs ``rendercanvas`` to be installed in `site-packages` for
the hook to work (i.e. it seems not to work with a ``pip -e .`` dev install).

Getting started
===============

Installation
------------

You can install ``rendercanvas`` via pip (or most other Python package managers).
Python 3.10 or higher is required. Pypy is supported.

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

    context = canvas.get_bitmap_context()

    @canvas.request_draw
    def animate():
        # ... produce an image, represented with e.g. a numpy array
        context.set_bitmap(image)

Rendering with wgpu:

.. code-block:: py

    context = canvas.get_wgpu_context()
    context.configure(device)

    @canvas.request_draw
    def animate():
        texture = context.get_current_texture()
        # ... wgpu code


Physical size, logical size, and pixel-ratio
--------------------------------------------

The context has properties for the logical size, physical size, and the
pixel-ratio.

* The physical size represent the actual number of "harware pixels" of the canvas surface.
* The logical size represents the size in "virtual pixels", which is used to scale elements like text, points, line thickness etc.
* The pixel-ratio represents the factor between the physical size and the logical size.

On regular screens, the physical size and logical size are often equal:

.. code-block::

    +----+----+----+----+
    |    |    |    |    |   Physical pixels
    +----+----+----+----+
    +----+----+
    |    |    |             Logical pixels, pixel-ratio 1.0
    +----+----+

On HiDPI / Retina displays, there are many more pixels, but they are much smaller. To prevent things like text to become tiny,
the logical pixels are made larger, i.e. pixel-ratio is increased (by the operating system), usually by a factor 2:

.. code-block::

    +--+--+--+--+
    |  |  |  |  |   Physical pixels
    +--+--+--+--+
    +-----+-----+
    |     |     |    Logical pixels, pixel-ratio 2.0
    +-----+-----+

Other operating system may increase the pixel-ratio as a global zoom factor, to increase the size of elements such as text in all applications.
This means that the pixel-ratio can indeed be fractional:

.. code-block::

    +----+----+----+----+
    |    |    |    |    |   Physical pixels
    +----+----+----+----+
    +-----+-----+
    |     |     |           Logical pixels, pixel-ratio ± 1.2
    +-----+-----+

Side note: on MacOS, the pixel-ratio is fixed to either 1.0 or 2.0, usually the latter on a Retina display with reasonable resolution settings. (The OS level
zooming is implemented by rendering the whole screen to an offscreen buffer with
a different size than the physical screen, and then up/down-scaling that to the
screen.)


.. _async:

Async
-----

A render canvas can be used in a fully async setting using e.g. Asyncio or Trio, or in an event-drived framework like Qt.
If you like callbacks, use ``loop.call_soon()`` and ``loop.call_later()`` for cancellable callbacks (that works the same, independent of the used backend).

If you like async, use ``loop.add_task()`` to register a co-routine. Your toolbelt of async functions is limited to
``sleep``  and ``Event`` from :doc:`rendercanvas.utils.asyncs <utils_asyncs>`. The good news
is that code that uses it works on any rendercanvas backend. Rendercanvas implements its own micro async framework to support this.

If you need more async features and/or your code always runs asyncio anyway, start your tasks via asyncio's ``create_task``. Same story for Trio.
That way it's also clear that your code relies on a specific async framework.

If you use Qt and get nervous from async code, no worries: when running on Qt, ``asyncio`` is not even imported. You can regard most async functions
as syntactic sugar for pieces of code chained with ``call_later`` (That's more or less how our micro async framework works.)


Freezing apps
-------------

In ``rendercanvas`` a PyInstaller-hook is provided to help simplify the freezing process. This hook requires
PyInstaller version 4+. Our hook includes ``glfw`` when it is available, so code using ``rendercanvas.auto``
should Just Work.

Note that PyInstaller needs ``rendercanvas`` to be installed in `site-packages` for
the hook to work (i.e. it seems not to work with a ``pip -e .`` dev install).

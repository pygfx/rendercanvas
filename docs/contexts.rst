Context API
===========

A context provides an API to provide a rendered image, and implements a
mechanism to present that image for display. The concept of a context is
heavily inspired by the ``<canvas>`` and its contexts in the browser.

**Available context classes**

* The :class:`~rendercanvas.contexts.BaseContext` exposes the common API.
* The :class:`~rendercanvas.contexts.BitmapContext` exposes an API that takes image bitmaps in RAM.
* The :class:`~rendercanvas.contexts.WgpuContext` exposes an API that provides image textures on the GPU to render to.

**Getting a context**

Context objects must be created using ``context = canvas.get_context(..)``,
or the dedicated ``canvas.get_bitmap_context()`` and
``canvas.get_wgpu_context()``.

**Using a context**

All contexts provide detailed size information (which is kept up-to-date by
the canvas). A rendering system should generally be capable to perform the
rendering with just the context object; without a reference to the canvas.
With this, we try to promote a clear separation of concerns, where one
system listens to events from the canvas to update a certain state, and the
renderer uses this state and the context to render the image.

**Advanced: creating a custom context API**

It's possible for users to create their own context sub-classes. This can be
a good solution, e.g. when your system needs to handle the presentation by
itself. In general it's better, when possible, to create an object that *wraps* a
built-in context object: ``my_ob = MyClass(canvas.get_context(..))``. That
way your code will not break if the internal interface between the context
and the canvas is changed.


.. autoclass:: rendercanvas.contexts.BaseContext
    :members:

.. autoclass:: rendercanvas.contexts.BitmapContext
    :members:

.. autoclass:: rendercanvas.contexts.WgpuContext
    :members:

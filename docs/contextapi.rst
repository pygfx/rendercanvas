How context objects work
========================

This page documents the inner working between the ``RenderCanvas`` and the context object.


Introduction
------------

The process of rendering to a canvas can be separated in two parts: *rendering*
and *presenting*. The role of the context is to facilitate the rendering, and to
then present the result to the screen. For this, the canvas provides one or more
*present-methods*. Each canvas backend must provide at least the 'screen' or
'bitmap' present-method.

.. code-block::

    Rendering                 Presenting

                ┌─────────┐               ┌────────┐
                │         │  ──screen──►  │        │
    ──render──► | Context │      or       │ Canvas │
                │         │  ──bitmap──►  │        │
                └─────────┘               └────────┘

If the context is a ``BitmapContext``, and the canvas supports the bitmap present-method,
things are easy. Similarly, if the context is a ``WgpuContext``, and the canvas
supports the screen present-method, the presenting is simply delegated to wgpu.

When there's a mismatch, we use different context sub-classes that handle the conversion.
With the ``WgpuContextToBitmap`` context, the rendered result is inside a texture on the GPU.
This texture is then downloaded to a bitmap on the CPU that can be passed to the canvas.

.. code-block::

                ┌─────────┐                     ┌────────┐
                │         │  ──tex─┐            │        │
    ──render──► | Context │        |            │ Canvas │
                │         │        └─bitmap──►  │        |
                └─────────┘                     └────────┘
                              download to CPU

With the ``BitmapContextToWgpu`` context, the bitmap is uploaded to a GPU texture,
which is then rendered to screen using the lower-level canvas-context from ``wgpu``.

.. code-block::

                ┌─────────┐                        ┌────────┐
                │         │           ┌─screen──►  │        │
    ──render──► | Context │           │            │ Canvas │
                │         │  ──bitmap─┘            │        |
                └─────────┘                        └────────┘
                               upload to GPU

This way, contexts can be made to work with all canvas backens.

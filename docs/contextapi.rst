How context objects work
========================

This page documents the working bentween the ``RenderCanvas`` and the context object.


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

This means that for the context to be able to present to any canvas, it must
support *both* the 'bitmap' and 'screen' present-methods. If the context prefers
presenting to the screen, and the canvas supports that, all is well. Similarly,
if the context has a bitmap to present, and the canvas supports the
bitmap-method, there's no problem.

It get's a little trickier when there's a mismatch, but we can deal with these
cases too. When the context prefers presenting to screen, the rendered result is
probably a texture on the GPU. This texture must then be downloaded to a bitmap
on the CPU. All GPU API's have ways to do this.

.. code-block::

                ┌─────────┐                     ┌────────┐
                │         │  ──tex─┐            │        │
    ──render──► | Context │        |            │ Canvas │
                │         │        └─bitmap──►  │        |
                └─────────┘                     └────────┘
                         download from gpu to cpu

If the context has a bitmap to present, and the canvas only supports presenting
to screen, you can usse a small utility: the ``BitmapPresentAdapter`` takes a
bitmap and presents it to the screen.

.. code-block::

                ┌─────────┐                        ┌────────┐
                │         │           ┌─screen──►  │        │
    ──render──► | Context │           │            │ Canvas │
                │         │  ──bitmap─┘            │        |
                └─────────┘                        └────────┘
                          use BitmapPresentAdapter

This way, contexts can be made to work with all canvas backens.

Canvases may also provide additionaly present-methods. If a context knows how to
use that present-method, it can make use of it. Examples could be presenting
diff images or video streams.

.. code-block::

                ┌─────────┐                               ┌────────┐
                │         │                               │        │
    ──render──► | Context │  ──special-present-method──►  │ Canvas │
                │         │                               │        |
                └─────────┘                               └────────┘


Context detection
-----------------

Anyone can make a context that works with ``rendercanvas``. In order for ``rendercanvas`` to find, it needs a little hook.

.. autofunction:: rendercanvas._context.rendercanvas_context_hook
    :no-index:


Context API
-----------

The class below describes the API and behavior that is expected of a context object.
Also see https://github.com/pygfx/rendercanvas/blob/main/rendercanvas/_context.py.

.. autoclass:: rendercanvas._context.ContextInterface
    :members:
    :no-index:


Adapter
-------

.. autoclass:: rendercanvas.utils.bitmappresentadapter.BitmapPresentAdapter
    :members:
    :no-index:

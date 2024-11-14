Context API
===========

This page documents the contract bentween the ``RenderCanvas`` and the context object.


Context detection
-----------------

.. autofunction:: rendercanvas._context.rendercanvas_context_hook
    :no-index:


Context
-------

.. autoclass:: rendercanvas._context.ContextInterface
    :members:
    :no-index:


RenderCanvas
------------

This shows the subset of methods of a canvas that relates to the context (see :doc:`backendapi` for the complete list).

.. autoclass:: rendercanvas.stub.StubRenderCanvas
    :members: _rc_get_present_methods, get_context, get_physical_size, get_logical_size,
    :no-index:

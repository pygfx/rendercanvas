API
===

These are the base classes that make up the rendercanvas API:

* The :class:`~rendercanvas.BaseRenderCanvas` represents the main API.
* The :class:`~rendercanvas.BaseLoop` provides functionality to work with the event-loop in a generic way.
* The :class:`~rendercanvas.EventType` specifies the different types of events that can be connected to with :func:`canvas.add_event_handler() <rendercanvas.BaseRenderCanvas.add_event_handler>`.

.. autoclass:: rendercanvas.BaseRenderCanvas
    :members:
    :member-order: bysource

.. autoclass:: rendercanvas.BaseLoop
    :members:
    :member-order: bysource

.. autoclass:: rendercanvas.EventType
    :members:
    :member-order: bysource

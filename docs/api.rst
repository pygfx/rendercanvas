API
===

These are the base classes that make up the rendercanvas API:

* The :class:`~rendercanvas.BaseRenderCanvas` represets the main API.
* The :class:`~rendercanvas.BaseLoop` provides functionality to work with the event-loop and timers in a generic way.
* The :class:`~rendercanvas.BaseTimer` is returned by some methods of ``loop``.
* The :class:`~rendercanvas.EventType` specifies the different types of events that can be connected to with :func:`canvas.add_event_handler() <rendercanvas.BaseRenderCanvas.add_event_handler>`.

.. autoclass:: rendercanvas.BaseRenderCanvas
    :members:
    :member-order: bysource

.. autoclass:: rendercanvas.BaseLoop
    :members:
    :member-order: bysource

.. autoclass:: rendercanvas.BaseTimer
    :members:
    :member-order: bysource

.. autoclass:: rendercanvas.EventType
    :members:
    :member-order: bysource

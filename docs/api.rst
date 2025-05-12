API
===

These are the classes that make up the rendercanvas API:

* The :class:`~rendercanvas.BaseRenderCanvas` represents the main API.
* The :class:`~rendercanvas.BaseLoop` provides functionality to work with the event-loop in a generic way.
* The :class:`~rendercanvas.EventType` enum specifies the types of events for :func:`canvas.add_event_handler() <rendercanvas.BaseRenderCanvas.add_event_handler>`.
* The :class:`~rendercanvas.UpdateMode` enum specifies the scheduler behaviour for  :func:`canvas.set_update_mode() <rendercanvas.BaseRenderCanvas.set_update_mode>`.
* The :class:`~rendercanvas.CursorShape` enum specifies the cursor shapes for :func:`canvas.set_cursor() <rendercanvas.BaseRenderCanvas.set_cursor>`.

.. autoclass:: rendercanvas.BaseRenderCanvas
    :members:
    :member-order: bysource

.. autoclass:: rendercanvas.BaseLoop
    :members:
    :member-order: bysource

.. autoclass:: rendercanvas.EventType
    :members:
    :member-order: bysource

.. autoclass:: rendercanvas.UpdateMode
    :members:
    :member-order: bysource

.. autoclass:: rendercanvas.CursorShape
    :members:
    :member-order: bysource

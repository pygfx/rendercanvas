"""
The event system.
"""

import time
from inspect import iscoroutinefunction
from collections import defaultdict, deque

from ._coreutils import log_exception, BaseEnum


class EventType(BaseEnum):
    """The EventType enum specifies the possible events for a RenderCanvas.

    This includes the events from the jupyter_rfb event spec (see
    https://jupyter-rfb.readthedocs.io/en/stable/events.html) plus some
    rendercanvas-specific events.
    """

    # Jupter_rfb spec

    resize = None  #: The canvas has changed size. Has 'width' and 'height' in logical pixels, 'pixel_ratio'.
    close = None  #: The canvas is closed. No additional fields.
    pointer_down = None  #: The pointing device is pressed down. Has 'x', 'y', 'button', 'butons', 'modifiers', 'ntouches', 'touches'.
    pointer_up = None  #: The pointing device is released. Same fields as pointer_down. Can occur outside of the canvas.
    pointer_move = None  #: The pointing device is moved. Same fields as pointer_down. Can occur outside of the canvas if the pointer is currently down.
    pointer_enter = None  #: The pointing device is moved into the canvas.
    pointer_leave = None  #: The pointing device is moved outside of the canvas (regardless of a button currently being pressed).
    double_click = None  #: A double-click / long-tap. This event looks like a pointer event, but without the touches.
    wheel = None  #: The mouse-wheel is used (scrolling), or the touchpad/touchscreen is scrolled/pinched. Has 'dx', 'dy', 'x', 'y', 'modifiers'.
    key_down = None  #: A key is pressed down. Has 'key', 'modifiers'.
    key_up = None  #: A key is released. Has 'key', 'modifiers'.

    # Pending for the spec, may become part of key_down/key_up
    char = None  #: Experimental

    # Our extra events

    before_draw = (
        None  #: Event emitted right before a draw is performed. Has no extra fields.
    )
    animate = None  #: Animation event. Has 'step' representing the step size in seconds. This is stable, except when the 'catch_up' field is nonzero.


valid_event_types = set(EventType)


class EventEmitter:
    """The EventEmitter stores event handlers, collects incoming events, and dispatched them.

    Subsequent events of ``event_type`` 'pointer_move' and 'wheel' are merged.
    """

    _EVENTS_THAT_MERGE = {
        "pointer_move": {
            "match_keys": {"buttons", "modifiers", "ntouches"},
            "accum_keys": {},
        },
        "wheel": {
            "match_keys": {"modifiers"},
            "accum_keys": {"dx", "dy"},
        },
        "resize": {
            "match_keys": {},
            "accum_keys": {},
        },
    }

    def __init__(self):
        self._pending_events = deque()
        self._event_handlers = defaultdict(list)
        self._closed = False

    def _release(self):
        self._closed = True
        self._pending_events.clear()
        self._event_handlers.clear()

    def add_handler(self, *args, order: float = 0):
        """Register an event handler to receive events.

        Arguments:
            callback (callable): The event handler. Must accept a single event argument.
                Can be a plain function or a coroutine function.
                If you use async callbacks, see :ref:`async` for the limitations.
            *types (list of strings): A list of event types.
            order (float): Set callback priority order. Callbacks with lower priorities
                are called first. Default is 0. When an event is emitted, callbacks with
                the same priority are called in the order that they were added.

        For the available events, see
        https://jupyter-rfb.readthedocs.io/en/stable/events.html.

        The callback is stored, so it can be a lambda or closure. This also
        means that if a method is given, a reference to the object is held,
        which may cause circular references or prevent the Python GC from
        destroying that object.

        Example:

        .. code-block:: py

            def my_handler(event):
                print(event)

            canvas.add_event_handler(my_handler, "pointer_up", "pointer_down")

        Can also be used as a decorator:

        .. code-block:: py

            @canvas.add_event_handler("pointer_up", "pointer_down") def
            my_handler(event):
                print(event)

        Catch 'm all:

        .. code-block:: py

            canvas.add_event_handler(my_handler, "*")

        """
        order = float(order)
        decorating = not callable(args[0])
        callback = None if decorating else args[0]
        types = args if decorating else args[1:]

        if not types:
            raise TypeError("No event types are given to add_event_handler.")
        for type in types:
            if not isinstance(type, str):
                raise TypeError(f"Event types must be str, but got {type}")
            if not (type == "*" or type in valid_event_types):
                raise ValueError(f"Adding handler with invalid event_type: '{type}'")

        def decorator(_callback):
            self._add_handler(_callback, order, *types)
            return _callback

        if decorating:
            return decorator
        return decorator(callback)

    def _add_handler(self, callback, order, *types):
        if self._closed:
            return
        self.remove_handler(callback, *types)
        for type in types:
            self._event_handlers[type].append((order, callback))
            self._event_handlers[type].sort(key=lambda x: x[0])
            # Note: that sort is potentially expensive. I tried an approach with a custom dequeu to add the handler
            # at the correct position, but the overhead was apparently larger than the benefit of avoiding sort.

    def remove_handler(self, callback, *types):
        """Unregister an event handler.

        Arguments:
            callback (callable): The event handler.
            *types (list of strings): A list of event types.
        """
        for type in types:
            self._event_handlers[type] = [
                (o, cb) for o, cb in self._event_handlers[type] if cb is not callback
            ]

    def submit(self, event):
        """Submit an event.

        Events are emitted later by the scheduler.
        """
        if self._closed:
            return
        event_type = event["event_type"]
        if event_type not in valid_event_types:
            raise ValueError(f"Submitting with invalid event_type: '{event_type}'")

        event.setdefault("time_stamp", time.perf_counter())
        event_merge_info = self._EVENTS_THAT_MERGE.get(event_type, None)

        if event_merge_info and self._pending_events:
            # Try merging the event with the last one
            last_event = self._pending_events[-1]
            if last_event["event_type"] == event_type:
                match_keys = event_merge_info["match_keys"]
                accum_keys = event_merge_info["accum_keys"]
                if all(
                    event.get(key, None) == last_event.get(key, None)
                    for key in match_keys
                ):
                    # Merge-able event
                    self._pending_events.pop()  # remove last_event
                    # Update new event
                    for key in accum_keys:
                        event[key] += last_event[key]

        self._pending_events.append(event)

    async def flush(self):
        """Dispatch all pending events.

        This should generally be left to the scheduler.
        """
        while True:
            try:
                event = self._pending_events.popleft()
            except IndexError:
                break
            await self.emit(event)

    async def emit(self, event):
        """Directly emit the given event.

        In most cases events should be submitted, so that they are flushed
        with the rest at a good time.
        """
        # Collect callbacks
        event_type = event.get("event_type")
        callbacks = self._event_handlers[event_type] + self._event_handlers["*"]
        # Dispatch
        for _order, callback in callbacks:
            if event.get("stop_propagation", False):
                break
            with log_exception(f"Error during handling {event_type} event"):
                if iscoroutinefunction(callback):
                    await callback(event)
                else:
                    callback(event)
        # Close?
        if event_type == "close":
            self._release()

    async def close(self):
        """Close the event handler.

        Drops all pending events, send the close event, and disables the emitter.
        """
        # This is a little feature because detecting a widget from closing can be tricky.
        if not self._closed:
            self._pending_events.clear()
            self.submit({"event_type": "close"})
            await self.flush()

import types
from typing import Literal

# ----- Base enum class

# We implement a custom enum class that's much simpler than Python's enum.Enum,
# and simply maps to strings or ints. The enums are classes, so IDE's provide
# autocompletion, and documenting with Sphinx is easy. That does mean we need a
# metaclass though.


class EnumType(type):
    """Metaclass for enums and flags."""

    def __new__(cls, name, bases, dct):
        # Collect and check fields
        member_map = {}
        for key, val in dct.items():
            if not key.startswith("_"):
                val = key if val is None else val
                if not isinstance(val, (int, str)):
                    raise TypeError("Enum fields must be str or int.")
                member_map[key] = val
        # Some field values may have been updated
        dct.update(member_map)
        # Create class
        klass = super().__new__(cls, name, bases, dct)
        # Attach some fields
        klass.__fields__ = tuple(member_map)
        klass.__members__ = types.MappingProxyType(member_map)  # enums.Enum compat
        # Create bound methods
        for name in ["__dir__", "__iter__", "__getitem__", "__setattr__", "__repr__"]:
            setattr(klass, name, types.MethodType(getattr(cls, name), klass))
        return klass

    def __dir__(cls):
        # Support dir(enum). Note that this order matches the definition, but dir() makes it alphabetic.
        return cls.__fields__

    def __iter__(cls):
        # Support list(enum), iterating over the enum, and doing ``x in enum``.
        return iter([getattr(cls, key) for key in cls.__fields__])

    def __getitem__(cls, key):
        # Support enum[key]
        return cls.__dict__[key]

    def __repr__(cls):
        if cls is BaseEnum:
            return "<rendercanvas.BaseEnum>"
        pkg = cls.__module__.split(".")[0]
        name = cls.__name__
        options = []
        for key in cls.__fields__:
            val = cls[key]
            options.append(f"'{key}' ({val})" if isinstance(val, int) else f"'{val}'")
        return f"<{pkg}.{name} enum with options: {', '.join(options)}>"

    def __setattr__(cls, name, value):
        if name.startswith("_"):
            super().__setattr__(name, value)
        else:
            raise RuntimeError("Cannot set values on an enum.")


class BaseEnum(metaclass=EnumType):
    """Base class for flags and enums.

    Looks like Python's builtin Enum class, but is simpler; fields are simply ints or strings.
    """

    def __init__(self):
        raise RuntimeError("Cannot instantiate an enum.")


# ----- The enums

# The Xxxx(BaseEnum) classes are for Sphynx docs, and maybe discovery in interactive sessions.
# The XxxxEnum Literals are for type checking, and static autocompletion of string args in funcs that accept an enum.


CursorShapeEnum = Literal[
    "default",
    "text",
    "crosshair",
    "pointer",
    "ew_resize",
    "ns_resize",
    "nesw_resize",
    "nwse_resize",
    "not_allowed",
    "none",
]


class CursorShape(BaseEnum):
    """The CursorShape enum specifies the suppported cursor shapes, following CSS cursor names."""

    default = None  #: The platform-dependent default cursor, typically an arrow.
    text = None  #: The text input I-beam cursor shape.
    crosshair = None  #:
    pointer = None  #: The pointing hand cursor shape.
    ew_resize = "ew-resize"  #: The horizontal resize/move arrow shape.
    ns_resize = "ns-resize"  #: The vertical resize/move arrow shape.
    nesw_resize = (
        "nesw-resize"  #: The top-left to bottom-right diagonal resize/move arrow shape.
    )
    nwse_resize = (
        "nwse-resize"  #: The top-right to bottom-left diagonal resize/move arrow shape.
    )
    not_allowed = "not-allowed"  #: The operation-not-allowed shape.
    none = "none"  #: The cursor is hidden.


EventTypeEnum = Literal[
    "*",
    "resize",
    "close",
    "pointer_down",
    "pointer_up",
    "pointer_move",
    "pointer_enter",
    "pointer_leave",
    "double_click",
    "wheel",
    "key_down",
    "key_up",
    "char",
    "before_draw",
    "animate",
]


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


UpdateModeEnum = Literal["manual", "ondemand", "continuous", "fastest"]


class UpdateMode(BaseEnum):
    """The UpdateMode enum specifies the different modes to schedule draws for the canvas."""

    manual = None  #: Draw events are never scheduled. Draws only happen when you ``canvas.force_draw()``, and maybe when the GUI system issues them (e.g. when resizing).
    ondemand = None  #: Draws are only scheduled when ``canvas.request_draw()`` is called when an update is needed. Safes your laptop battery. Honours ``min_fps`` and ``max_fps``.
    continuous = None  #: Continuously schedules draw events, honouring ``max_fps``. Calls to ``canvas.request_draw()`` have no effect.
    fastest = None  #: Continuously schedules draw events as fast as possible. Gives high FPS (and drains your battery).

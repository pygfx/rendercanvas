"""
The base classes.
"""

from __future__ import annotations

import sys
import weakref
from typing import TYPE_CHECKING

from ._enums import (
    EventTypeEnum,
    UpdateModeEnum,
    CursorShape,
    CursorShapeEnum,
)
from . import contexts
from ._size import SizeInfo
from ._events import EventEmitter
from ._loop import BaseLoop
from ._scheduler import Scheduler
from ._coreutils import logger, log_exception


if TYPE_CHECKING:
    from typing import Callable, Literal, Optional

    EventHandlerFunction = Callable[[dict], None]
    DrawFunction = Callable[[], None]


__all__ = ["BaseLoop", "BaseRenderCanvas", "WrapperRenderCanvas"]


# Notes on naming and prefixes:
#
# Since BaseRenderCanvas can be used as a mixin with classes in a GUI framework,
# we must avoid using generic names to avoid name clashes.
#
# * `.public_method`: Public API: usually at least two words, (except the close() method)
# * `._private_method`: Private methods for scheduler and subclasses.
# * `.__private_attr`: Private to exactly this class.
# * `._rc_method`: Methods that the subclass must implement.


class BaseCanvasGroup:
    """Represents a group of canvas objects from the same class, that share a loop."""

    def __init__(self, default_loop: BaseLoop):
        self._canvases = weakref.WeakSet()
        self._loop = None
        self.select_loop(default_loop)

    def _register_canvas(self, canvas, task):
        """Used by the canvas to register itself."""
        self._canvases.add(canvas)
        loop = self.get_loop()
        if loop is not None:
            loop._register_canvas_group(self)
            loop.add_task(task, name="scheduler-task")

    def select_loop(self, loop: BaseLoop) -> None:
        """Select the loop to use for this group of canvases."""
        if not (loop is None or isinstance(loop, BaseLoop)):
            raise TypeError("select_loop() requires a loop instance or None.")
        elif len(self._canvases):
            raise RuntimeError("Cannot select_loop() when live canvases exist.")
        elif loop is self._loop:
            pass
        else:
            if self._loop is not None:
                self._loop._unregister_canvas_group(self)
            self._loop = loop

    def get_loop(self) -> BaseLoop | None:
        """Get the currently associated loop (can be None for canvases that don't run a scheduler)."""
        return self._loop

    def get_canvases(self, *, close_closed=False) -> list[BaseRenderCanvas]:
        if close_closed:
            closed_canvases = [
                canvas for canvas in self._canvases if canvas.get_closed()
            ]
            for canvas in closed_canvases:
                canvas.close()
                self._canvases.discard(canvas)
            return self._canvases
        else:
            return [canvas for canvas in self._canvases if not canvas.get_closed()]


class BaseRenderCanvas:
    """The base canvas class.

    This base class defines a uniform canvas API so render systems can use code
    that is portable across multiple GUI libraries and canvas targets. The
    scheduling mechanics are generic, even though they run on different backend
    event systems.

    Arguments:
        size (tuple): the logical size (width, height) of the canvas.
        title (str): The title of the canvas. Can use '$backend' to show the RenderCanvas class name,
            '$fps' to show the fps, and '$ms' to show the frame-time.
        update_mode (UpdateMode): The mode for scheduling draws and events. Default 'ondemand'.
        min_fps (float): A minimal frames-per-second to use when the ``update_mode`` is 'ondemand'. The default is 0:
        max_fps (float): A maximal frames-per-second to use when the ``update_mode`` is 'ondemand'
            or 'continuous'. The default is 30, which is usually enough.
        vsync (bool): Whether to sync the draw with the monitor update. Helps
            against screen tearing, but limits the fps. Default True.
        present_method (str | None): Override the method to present the rendered result.
            Can be set to 'screen' or 'bitmap'. Default None, which means that the method is selected
            based on what the canvas and context support and prefer.

    """

    _rc_canvas_group = None
    """Class attribute that refers to the ``CanvasGroup`` instance to use for canvases of this class.
    It specifies what loop is used, and enables users to changing the used loop.
    """

    @classmethod
    def select_loop(cls, loop: BaseLoop) -> None:
        """Select the loop to run newly created canvases with.
        Can only be called when there are no live canvases of this class.
        """
        group = cls._rc_canvas_group
        if group is None:
            raise NotImplementedError(
                "The {cls.__name__} does not have a canvas group, thus no loop."
            )
        group.select_loop(loop)

    def __init__(
        self,
        *args,
        size: tuple[float, float] | None = (640, 480),
        title: str | None = "$backend",
        update_mode: UpdateModeEnum = "ondemand",
        min_fps: float = 0.0,
        max_fps: float = 30.0,
        vsync: bool = True,
        present_method: Literal["bitmap", "screen", None] = None,
        **kwargs,
    ):
        # Initialize superclass. Note that super() can be e.g. a QWidget, RemoteFrameBuffer, or object.
        # When object and erroring, we *must* have an invalid argument. Detect that case
        # so we can raise a more meaningful error message.
        try:
            super().__init__(*args, **kwargs)
        except TypeError as err:
            if sys.version_info >= (3, 11) and "takes exactly one argument" in str(err):
                msg = "Instantiating a RenderCanvas with invalid "
                if args and kwargs:
                    msg += f"args {args} and kwargs {kwargs}"
                elif args:
                    msg += f"args {args}"
                elif kwargs:
                    msg += f"kwargs {kwargs}"
                else:
                    msg += "input."
                err.add_note(msg)
            raise

        # If this is a wrapper, no need to initialize further
        if isinstance(self, WrapperRenderCanvas):
            return

        # The vsync is not-so-elegantly stored on the canvas, and picked up by wgpu's canvas contex.
        self._vsync = bool(vsync)

        # Handle custom present method
        if not (present_method is None or isinstance(present_method, str)):
            raise TypeError(
                f"The canvas present_method should be None or str, not {present_method!r}."
            )
        self._present_method = present_method
        self._present_to_screen: bool | None = None  # set in .get_context()

        # Variables and flags used internally
        self.__is_drawing = False
        self.__title_info = {
            "raw": "",
            "fps": "?",
            "ms": "?",
            "backend": self.__class__.__name__,
            "loop": self._rc_canvas_group.get_loop().__class__.__name__
            if (self._rc_canvas_group and self._rc_canvas_group.get_loop())
            else "no-loop",
        }
        self._size_info = SizeInfo()

        # Events and scheduler
        self._events = EventEmitter()
        self.__scheduler = None
        if self._rc_canvas_group is None:
            pass  # No scheduling, not even grouping
        elif self._rc_canvas_group.get_loop() is None:
            # Group, but no loop: no scheduling
            self._rc_canvas_group._register_canvas(self, None)
        else:
            self.__scheduler = Scheduler(
                self,
                self._events,
                min_fps=min_fps,
                max_fps=max_fps,
                update_mode=update_mode,
            )
            self._rc_canvas_group._register_canvas(self, self.__scheduler.get_task())

        # We cannot initialize the size and title now, because the subclass may not have done
        # the initialization to support this. So we require the subclass to call _final_canvas_init.
        self.__kwargs_for_later = dict(size=size, title=title)

    def _final_canvas_init(self):
        """Must be called by the subclasses at the end of their ``__init__``.

        This sets the canvas logical size and title, which must happen *after* the widget itself
        is initialized. (Doing this automatically can be done with a metaclass, but let's keep it simple.)
        """
        # Pop kwargs
        try:
            kwargs = self.__kwargs_for_later
        except AttributeError:
            return
        else:
            del self.__kwargs_for_later
        # Apply
        if not isinstance(self, WrapperRenderCanvas):
            size = kwargs["size"]
            if size is not None:
                self.set_logical_size(*size)  # type: ignore
            title = kwargs["title"]
            if title is not None:
                self.set_title(title)  # type: ignore

    def __del__(self):
        # On delete, we call the custom destroy method.
        try:
            self.close()
        except Exception:
            pass
        # Since this is sometimes used in a multiple inheritance, the
        # superclass may (or may not) have a __del__ method.
        try:
            super().__del__()  # type: ignore
        except Exception:
            pass

    _canvas_context = None  # set in get_context()

    def get_physical_size(self) -> tuple[int, int]:
        """Get the physical size of the canvas in integer pixels."""
        return self._size_info["physical_size"]

    def get_bitmap_context(self) -> contexts.BitmapContext:
        """Get the ``BitmapContext`` to render to this canvas."""
        return self.get_context("bitmap")

    def get_wgpu_context(self) -> contexts.WgpuContext:
        """Get the ``WgpuContext`` to render to this canvas."""
        return self.get_context("wgpu")

    def get_context(self, context_type: str | type) -> contexts.BaseContext:
        """Get a context object that can be used to render to this canvas.

        The context takes care of presenting the rendered result to the canvas.
        Different types of contexts are available:

        * Use "wgpu" to get a ``WgpuContext``
        * Use "bitmap" to get a ``BitmapContext``
        * Use a subclass of ``BaseContext`` to create an instance that is set up for this canvas.

        Later calls to this method, with the same context_type argument, will return
        the same context instance as was returned the first time the method was
        invoked. It is not possible to get a different context object once the first
        one has been created.
        """

        # Note that this method is analog to HtmlCanvas.getContext(), except with different context types.

        context_name = None
        context_class = None

        # Resolve the context class
        if isinstance(context_type, str):
            # Builtin contexts
            if context_type == "bitmap":
                context_class = contexts.BitmapContext
            elif context_type == "wgpu":
                context_class = contexts.WgpuContext
            else:
                raise TypeError(
                    f"The given context type is invalid: {context_type!r} is not 'bitmap' or 'wgpu'."
                )
        elif isinstance(context_type, type) and issubclass(
            context_type, contexts.BaseContext
        ):
            # Custom context
            context_class = context_type
        else:
            raise TypeError(
                "canvas.get_context(): context_type must be 'bitmap', 'wgpu', or a subclass of BaseContext."
            )

        # Get the name
        context_name = context_class.__name__

        # Is the context already set?
        if self._canvas_context is not None:
            ref_context_name = getattr(
                self._canvas_context,
                "_context_name",
                self._canvas_context.__class__.__name__,
            )
            if context_name == ref_context_name:
                return self._canvas_context
            else:
                raise RuntimeError(
                    f"Cannot get context for '{context_name}': a context of type '{ref_context_name}' is already set."
                )

        # Get available present methods that the canvas can chose from.
        present_methods = list(context_class.present_methods)
        assert all(m in ("bitmap", "screen") for m in present_methods)  # sanity check
        if self._present_method:
            if self._present_method not in present_methods:
                raise RuntimeError(
                    f"Explicitly requested present_method {self._present_method!r} is not available for {context_name}."
                )
            present_methods = [self._present_method]

        # Let the canvas select the method and provide the corresponding info object.
        # Take care not to hold onto this dict, it may contain objects that we don't want to unnecessarily reference.
        info = self._rc_get_present_info(present_methods)
        if info is None:
            method_message = f"Methods {set(present_methods)!r} are not supported."
            if len(present_methods) == 1:
                method_message = f"Method {present_methods[0]!r} is not supported."
            raise TypeError(
                f"Could not create {context_name!r} for {self.__class__.__name__!r}: {method_message}"
            )
        if info.get("method") not in present_methods:
            raise RuntimeError(
                f"Present info method field ({info.get('method')!r}) is not part of the available methods {set(present_methods)}."
            )
        self._present_to_screen = info["method"] == "screen"

        # Add some info
        present_info = {**info, "source": self.__class__.__name__, "vsync": self._vsync}

        # Create the context
        self._canvas_context = context_class(present_info)
        self._canvas_context._context_name = context_name
        self._canvas_context._rc_set_size_dict(self._size_info)
        return self._canvas_context

    # %% Events

    def add_event_handler(
        self, *args: EventTypeEnum | EventHandlerFunction, order: float = 0
    ) -> Callable:
        return self._events.add_handler(*args, order=order)

    def remove_event_handler(self, callback: EventHandlerFunction, *types: str) -> None:
        return self._events.remove_handler(callback, *types)

    def submit_event(self, event: dict) -> None:
        # Not strictly necessary for normal use-cases, but this allows
        # the ._event to be an implementation detail to subclasses, and it
        # allows users to e.g. emulate events in tests.
        return self._events.submit(event)

    add_event_handler.__doc__ = EventEmitter.add_handler.__doc__
    remove_event_handler.__doc__ = EventEmitter.remove_handler.__doc__
    submit_event.__doc__ = EventEmitter.submit.__doc__

    # %% Scheduling and drawing

    def __maybe_emit_resize_event(self):
        if self._size_info["changed"]:
            self._size_info["changed"] = False
            # Keep context up-to-date
            if self._canvas_context is not None:
                self._canvas_context._rc_set_size_dict(self._size_info)
            # Keep event listeners up-to-date
            lsize = self._size_info["logical_size"]
            self._events.emit(
                {
                    "event_type": "resize",
                    "width": lsize[0],
                    "height": lsize[1],
                    "pixel_ratio": self._size_info["total_pixel_ratio"],
                    # Would be nice to have more details. But as it is now, PyGfx errors if we add fields it does not know, so let's do later.
                    # "logical_size": self._size_info["logical_size"],
                    # "physical_size": self._size_info["physical_size"],
                }
            )

    def _process_events(self):
        """Process events and animations.

        Called from the scheduler.
        """

        # We don't want this to be called too often, because we want the
        # accumulative events to accumulate. Once per draw, and at max_fps
        # when there are no draws (in ondemand and manual mode).

        # Get events from the GUI into our event mechanism.
        self._rc_gui_poll()

        # If the canvas changed size, send event
        self.__maybe_emit_resize_event()

        # Flush our events, so downstream code can update stuff.
        # Maybe that downstream code request a new draw.
        self._events.flush()

        # TODO: implement later (this is a start but is not tested)
        # Schedule animation events until the lag is gone
        # step = self._animation_step
        # self._animation_time = self._animation_time or time.perf_counter()  # start now
        # animation_iters = 0
        # while self._animation_time > time.perf_counter() - step:
        #     self._animation_time += step
        #     self._events.submit({"event_type": "animate", "step": step, "catch_up": 0})
        #     # Do the animations. This costs time.
        #     self._events.flush()
        #     # Abort when we cannot keep up
        #     # todo: test this
        #     animation_iters += 1
        #     if animation_iters > 20:
        #         n = (time.perf_counter() - self._animation_time) // step
        #         self._animation_time += step * n
        #         self._events.submit(
        #             {"event_type": "animate", "step": step * n, "catch_up": n}
        #         )

    def _draw_frame(self):
        """The method to call to draw a frame.

        Cen be overriden by subclassing, or by passing a callable to request_draw().
        """
        pass

    def set_update_mode(
        self,
        update_mode: UpdateModeEnum,
        *,
        min_fps: Optional[float] = None,
        max_fps: Optional[float] = None,
    ) -> None:
        """Set the update mode for scheduling draws.

        Arguments:
            update_mode (UpdateMode): The mode for scheduling draws and events.
            min_fps (float): The minimum fps with update mode 'ondemand'.
            max_fps (float): The maximum fps with update mode 'ondemand' and 'continuous'.

        """
        if self.__scheduler is not None:
            self.__scheduler.set_update_mode(
                update_mode, min_fps=min_fps, max_fps=max_fps
            )

    def request_draw(self, draw_function: Optional[DrawFunction] = None) -> None:
        """Schedule a new draw event.

        This function does not perform a draw directly, but schedules a draw at
        a suitable moment in time. At that time the draw function is called, and
        the resulting rendered image is presented to the canvas.

        Only affects drawing with schedule-mode 'ondemand'.

        Arguments:
            draw_function (callable or None): The function to set as the new draw
                function. If not given or None, the last set draw function is used.

        """
        if draw_function is not None:
            self._draw_frame = draw_function
        if self.__scheduler is not None:
            self.__scheduler.request_draw()

        # -> Note that the draw func is likely to hold a ref to the canvas. By
        #   storing it here, the gc can detect this case, and its fine. However,
        #   this fails if we'd store _draw_frame on the scheduler!

    def force_draw(self) -> None:
        """Perform a draw right now.

        In most cases you want to use ``request_draw()``. If you find yourself using
        this, consider using a timer. Nevertheless, sometimes you just want to force
        a draw right now.
        """
        if self.__is_drawing:
            raise RuntimeError("Cannot force a draw while drawing.")
        if self._present_to_screen:
            self._rc_force_paint()  # -> _time_to_paint() -> _draw_and_present()
        else:
            self._draw_and_present(force_sync=True)
            self._rc_force_paint()  # May or may not work

    def _time_to_draw(self):
        """It's time to draw!

        To get here, ``_rc_request_draw()``  was probably called first:

            _rc_request_draw()  ->  ...  ->  _time_to_draw()

        The drawing happens asynchronously, and follows a different path for the different present methods.

        For the 'screen' method:

            _rc_request_paint()  ->  ...  ->  _time_to_paint()  ->  _draw_and_present()  ->  _finish_present()

        For the 'bitmap' method:

            _draw_and_present() ->  ...  ->   finish_present()  ->  _rc_request_paint()
        """

        # This is an good time to process events, it's the moment that's closest to the actual draw
        # as possible, but it's not in the native's paint-event (which is a bad moment to process events).
        # Doing it now - as opposed to right before _rc_request_draw() - ensures that the rendered frame
        # is up-to-date, which makes a huge difference for the perceived delay (e.g. for mouse movement)
        # when the FPS is low on remote backends.
        self._process_events()

        if self._present_to_screen:
            self._rc_request_paint()  # -> _time_to_paint() -> _draw_and_present()
        else:
            self._draw_and_present(force_sync=False)

    def _time_to_paint(self):
        """Callback for _rc_request_paint.

        This should be called inside the backend's native 'paint event' a.k.a. 'animation frame'.
        From a scheduling perspective, when this is called, a frame is 'consumed' by the backend.

        Errors are logged to the "rendercanvas" logger.
        """
        if self._present_to_screen:
            self._draw_and_present(force_sync=True)

    def _draw_and_present(self, *, force_sync: bool):
        """Draw the frame and init the presentation."""

        # Re-entrant drawing is problematic. Let's actively prevent it.
        if self.__is_drawing:
            return
        self.__is_drawing = True

        # Note that this method is responsible for notifying the scheduler for the draw getting canceled or done.
        # In other words, an early return should always be proceeded with a call to scheduler.on_cancel_draw(),
        # otherwise the drawing gets stuck. (The re-entrant logic is the one exception.)

        try:
            scheduler = self.__scheduler  # May be None
            context = self._canvas_context  # May be None

            # Let scheduler know that the draw is about to take place, resets the draw_requested flag.
            if scheduler is not None:
                scheduler.on_about_to_draw()

            # Check size
            w, h = self.get_physical_size()
            size_is_nill = not (w > 0 and h > 0)

            # Cancel the draw if the conditions aren't right
            if (
                size_is_nill
                or context is None
                or self._draw_frame is None
                or self._rc_get_closed()
            ):
                if scheduler is not None:
                    scheduler.on_cancel_draw()
                return

            # Make sure that the user-code is up-to-date with the current size before it draws.
            self.__maybe_emit_resize_event()

            # Emit before-draw
            self._events.emit({"event_type": "before_draw"})

            # Perform the user-defined drawing code. When this errors,
            # we should report the error and then continue, otherwise we crash.
            with log_exception("Draw error"):
                self._draw_frame()

            # Perform the presentation process. Might be async
            with log_exception("Present init error"):
                # Note: if vsync is used, this call may wait a little (happens down at the level of the driver or OS)

                if force_sync:
                    result = context._rc_present(force_sync=True)
                    assert result["method"] != "async"
                    self._finish_present(result)
                else:
                    result = context._rc_present()
                    if result["method"] == "async":
                        result["awaitable"].then(self._finish_present)
                    else:
                        self._finish_present(result)

        finally:
            self.__is_drawing = False

    def _finish_present(self, result):
        """Wrap up the presentation process."""

        with log_exception("Present finish error"):
            method = result.pop("method", "unknown")
            if method in ("skip", "screen"):
                pass  # nothing we need to do
            elif method == "fail":
                raise RuntimeError(result.get("message", "") or "present error")
            else:
                # Pass the result to the literal present method
                func = getattr(self, f"_rc_present_{method}")
                func(**result)
                # Now the backend must repaint to show the new image
                self._rc_request_paint()

        # Notify the scheduler
        if self.__scheduler is not None:
            frame_time = self.__scheduler.on_draw_done()

            # Maybe update title
            if frame_time is not None:
                self.__title_info["fps"] = f"{min(9999, 1 / frame_time):0.1f}"
                self.__title_info["ms"] = f"{min(9999, 1000 * frame_time):0.1f}"
                raw_title = self.__title_info["raw"]
                if "$fps" in raw_title or "$ms" in raw_title:
                    self.set_title(self.__title_info["raw"])

    def _set_visible(self, visible: bool):
        """Set whether the canvas is visible or not.

        This is meant for the backend to automatically enable/disable
        the rendering when the canvas is e.g. minimized or otherwise invisible.
        If not visible, frames are not rendered, but events are still processed.
        """
        if self.__scheduler is not None:
            self.__scheduler.set_enabled(visible)

    # %% Primary canvas management methods

    def get_logical_size(self) -> tuple[float, float]:
        """Get the logical size (width, height) of the canvas in float pixels.

        The logical size can be smaller than the physical size, e.g. on HiDPI
        monitors or when the user's system has the display-scale set to e.g. 125%.
        """
        return self._size_info["logical_size"]

    def get_pixel_ratio(self) -> float:
        """Get the float ratio between logical and physical pixels.

        The pixel ratio is typically 1.0 for normal screens and 2.0 for HiDPI
        screens, but fractional values are also possible if the system
        display-scale is set to e.g. 125%. An HiDPI screen can be assumed if the
        pixel ratio >= 2.0.
        """
        return self._size_info["total_pixel_ratio"]

    def close(self) -> None:
        """Close the canvas."""
        # Clear the draw-function, to avoid it holding onto e.g. wgpu objects.
        self._draw_frame = None  # type: ignore
        # Clear the canvas context too.
        try:
            self._canvas_context._rc_close()  # type: ignore
        except Exception:
            pass
        self._canvas_context = None
        # Clean events. Should already have happened in loop, but the loop may not be running.
        self._events.close()
        # Let the subclass clean up.
        self._rc_close()

    def get_closed(self) -> bool:
        """Get whether the window is closed."""
        return self._rc_get_closed()

    def is_closed(self):
        logger.warning(
            "canvas.is_closed() is deprecated, use canvas.get_closed() instead."
        )
        return self._rc_get_closed()

    # %% Secondary canvas management methods

    # These methods provide extra control over the canvas. Subclasses should
    # implement the methods they can, but these features are likely not critical.

    def set_logical_size(self, width: float, height: float) -> None:
        """Set the window size (in logical pixels).

        This changes the physical size of the canvas, such that the new logical
        size matches the given width and height. Since the physical size is
        integer (i.e. rounded), the re-calculated logical size may differ slightly
        from the given width and height (depending on the pixel ratio).
        """
        width, height = float(width), float(height)
        if width < 0 or height < 0:
            raise ValueError("Canvas width and height must not be negative")
        # Tell the backend to adjust the size. It will likely set the new physical size before the next draw.
        self._rc_set_logical_size(width, height)

    def set_title(self, title: str) -> None:
        """Set the window title.

        A few special placeholders are supported:

        * "$backend": the name of the backends's RenderCanvas subclass.
        * "$loop": the name of the used Loop subclass.
        * "$fps": the current frames per second, useful as an indication how smooth the rendering feels.
        * "$ms": the time between two rendered frames in milliseconds, useful for benchmarking.
        """
        self.__title_info["raw"] = title
        for k, v in self.__title_info.items():
            title = title.replace("$" + k, v)
        self._rc_set_title(title)

    def set_cursor(self, cursor: CursorShapeEnum) -> None:
        """Set the cursor shape for the mouse pointer.

        See :obj:`rendercanvas.CursorShape`:
        """
        if cursor is None:
            cursor = "default"
        if not isinstance(cursor, str):
            raise TypeError("Canvas cursor must be str.")
        cursor_normed = cursor.lower().replace("_", "-")
        if cursor_normed not in CursorShape:
            raise ValueError(
                f"Canvas cursor {cursor!r} not known, must be one of {CursorShape}"
            )
        self._rc_set_cursor(cursor_normed)

    # %% Methods for the subclass to implement

    def _rc_gui_poll(self):
        """Process native events."""
        pass

    def _rc_get_present_info(self, present_methods: list[str]) -> dict | None:
        """Select a present method and return corresponding info dict.

        This method is only called once, when the context is created. The
        subclass can use this moment to setup the internal state for the
        selected presentation method.

        The ``present_methods`` represents the supported methods of the
        canvas-context, in order of context-preference, possibly filtered by a
        user-specified method. A canvas backend must implement at least the
        "screen" or "bitmap" method.

        The returned dict must contain at least the key 'method', which must
        match one of the ``present_methods``. The remaining values represent
        information required by the canvas-context to perform the presentation,
        and optionally some (debug) meta data. The backend may optionally return
        None to indicate that none of the ``present_methods`` is supported.

        With method "screen", the context will render directly to a (virtual)
        surface. The dict should have a ``window`` field containing the window
        id. On Linux there should also be ``platform`` field to distinguish
        between "wayland" and "x11", and a ``display`` field for the display id.
        This information is used by wgpu to obtain the required surface id. For
        Pyodide the 'window' field should be the ``<canvas>`` object.

        With method "bitmap", the context will present the result as an image
        bitmap. For the ``WgpuContext``, the result will first be rendered to a
        texture, and then downloaded to RAM. The dict must have a field
        'formats': a list of supported image formats. Examples are "rgba-u8" and
        "i-u8". A canvas must support at least "rgba-u8". Note that srgb mapping
        is assumed to be handled by the canvas.
        """
        return None

    def _rc_request_draw(self):
        """Request the backend to call ``_time_to_draw()``.

        The backend must call ``_time_to_draw`` as soon as it's ready for the
        next frame. It is allowed to call it directly (rather than scheduling
        it). It can also be called later, but it must be called eventually,
        otherwise it will halt the rendering.

        This functionality allows the backend to throttle the frame rate. For
        instance, backends that implement 'remote' rendering can allow new
        frames based on the number of in-flight frames and downstream
        throughput.
        """
        self._time_to_draw()  # Simple default

    def _rc_request_paint(self):
        """Request the backend to do a paint, and call ``_time_to_paint()``.

        The backend must schedule ``_time_to_paint`` to be called as soon as
        possible, but (if applicable) it must be in the native animation frame,
        a.k.a. draw event. This function is analog to ``requestAnimationFrame``
        in JavaScript. In any case, inside ``_time_to_paint()`` a call like
        ``context.get_current_texture()`` should be allowed.

        When the present-method is 'screen', this method is called to initiate a
        draw. When the present-method is 'bitmap', it is called when the draw
        (and present) is completed, so the native system can repaint with the
        latest rendered frame.

        If the implementation of this method does nothing, it is equivalent to
        waiting for a forced draw or a draw invoked by the GUI system.
        """
        pass

    def _rc_force_paint(self):
        """Perform a synchronous paint.

        The backend should, if possible, invoke its native paint event right now (synchronously).
        The default implementation just calls ``_time_to_paint()``.
        """
        self._time_to_paint()

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        """Present the given image bitmap. Only used with present_method 'bitmap'.

        If a canvas supports special present methods, it will need to implement corresponding ``_rc_present_xx()`` methods.
        """
        raise NotImplementedError()

    def _rc_set_logical_size(self, width: float, height: float):
        """Set the logical size. May be ignored when it makes no sense.

        The default implementation does nothing.
        """
        pass

    def _rc_close(self):
        """Close the canvas.

        Note that ``BaseRenderCanvas`` implements the ``close()`` method, which is a
        rather common name; it may be necessary to re-implement that too.

        Backends should probably not mark the canvas as closed yet, but wait until the
        underlying system really closes the canvas. Otherwise the loop may end before a
        canvas gets properly cleaned up.

        Backends can emit a closed event, either in this method, or when the real close
        happens, but this is optional, since the loop detects canvases getting closed
        and sends the close event if this has not happened yet.
        """
        pass

    def _rc_get_closed(self) -> bool:
        """Get whether the canvas is closed."""
        return False

    def _rc_set_title(self, title: str):
        """Set the canvas title. May be ignored when it makes no sense.

        The default implementation does nothing.
        """
        pass

    def _rc_set_cursor(self, cursor: str):
        """Set the cursor shape. May be ignored.

        The default implementation does nothing.
        """
        pass


class WrapperRenderCanvas(BaseRenderCanvas):
    """A base render canvas for top-level windows that wrap a widget, as used in e.g. Qt and wx.

    This base class implements all the re-direction logic, so that the subclass does not have to.
    Subclasses should not implement any of the ``_rc_`` methods. Subclasses must instantiate the
    wrapped canvas and set it as ``_subwidget``.
    """

    _rc_canvas_group = None  # No grouping for these wrappers
    _subwidget: BaseRenderCanvas

    @classmethod
    def select_loop(cls, loop: BaseLoop) -> None:
        m = sys.modules[cls.__module__]
        return m.RenderWidget.select_loop(loop)

    def add_event_handler(
        self, *args: EventTypeEnum | EventHandlerFunction, order: float = 0
    ) -> Callable:
        return self._subwidget._events.add_handler(*args, order=order)

    def remove_event_handler(self, callback: EventHandlerFunction, *types: str) -> None:
        return self._subwidget._events.remove_handler(callback, *types)

    def submit_event(self, event: dict) -> None:
        return self._subwidget._events.submit(event)

    def get_context(self, context_type: str | type) -> object:
        return self._subwidget.get_context(context_type)

    def set_update_mode(
        self,
        update_mode: UpdateModeEnum,
        *,
        min_fps: Optional[float] = None,
        max_fps: Optional[float] = None,
    ) -> None:
        self._subwidget.set_update_mode(update_mode, min_fps=min_fps, max_fps=max_fps)

    def request_draw(self, draw_function: Optional[DrawFunction] = None) -> None:
        return self._subwidget.request_draw(draw_function)

    def force_draw(self) -> None:
        self._subwidget.force_draw()

    def get_physical_size(self) -> tuple[int, int]:
        return self._subwidget.get_physical_size()

    def get_logical_size(self) -> tuple[float, float]:
        return self._subwidget.get_logical_size()

    def get_pixel_ratio(self) -> float:
        return self._subwidget.get_pixel_ratio()

    def set_logical_size(self, width: float, height: float) -> None:
        self._subwidget.set_logical_size(width, height)

    def set_title(self, title: str) -> None:
        self._subwidget.set_title(title)

    def set_cursor(self, cursor: CursorShapeEnum) -> None:
        self._subwidget.set_cursor(cursor)

    def close(self) -> None:
        self._subwidget.close()

    def get_closed(self) -> bool:
        return self._subwidget.get_closed()

    def is_closed(self):
        return self._subwidget.is_closed()

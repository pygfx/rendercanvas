"""
The base classes.
"""

from __future__ import annotations

import sys
import weakref
import importlib
from typing import TYPE_CHECKING

from ._enums import (
    EventTypeEnum,
    UpdateModeEnum,
    CursorShape,
    CursorShapeEnum,
)
from ._events import EventEmitter
from ._loop import BaseLoop
from ._scheduler import Scheduler
from ._coreutils import logger, log_exception

if TYPE_CHECKING:
    from typing import Callable, List, Optional, Tuple

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

    def get_canvases(self) -> List[BaseRenderCanvas]:
        """Get a list of currently active (not-closed) canvases for this group."""
        return [canvas for canvas in self._canvases if not canvas.get_closed()]


class BaseRenderCanvas:
    """The base canvas class.

    This base class defines a uniform canvas API so render systems can use code
    that is portable accross multiple GUI libraries and canvas targets. The
    scheduling mechanics are generic, even though they run on different backend
    event systems.

    Arguments:
        size (tuple): the logical size (width, height) of the canvas.
        title (str): The title of the canvas. Can use '$backend' to show the RenderCanvas class name,
            and '$fps' to show the fps.
        update_mode (UpdateMode): The mode for scheduling draws and events. Default 'ondemand'.
        min_fps (float): A minimal frames-per-second to use when the ``update_mode`` is 'ondemand'. The default is 0:
        max_fps (float): A maximal frames-per-second to use when the ``update_mode`` is 'ondemand'
            or 'continuous'. The default is 30, which is usually enough.
        vsync (bool): Whether to sync the draw with the monitor update. Helps
            against screen tearing, but can reduce fps. Default True.
        present_method (str | None): Override the method to present the rendered result.
            Can be set to e.g. 'screen' or 'bitmap'. Default None (auto-select).

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
        size: Tuple[float, float] = (640, 480),
        title: str = "$backend",
        update_mode: UpdateModeEnum = "ondemand",
        min_fps: float = 0.0,
        max_fps: float = 30.0,
        vsync: bool = True,
        present_method: Optional[str] = None,
        **kwargs,
    ):
        # Initialize superclass. Note that super() can be e.g. a QWidget, RemoteFrameBuffer, or object.
        super().__init__(*args, **kwargs)

        # If this is a wrapper, no need to initialize furher
        if isinstance(self, WrapperRenderCanvas):
            return

        # The vsync is not-so-elegantly strored on the canvas, and picked up by wgou's canvas contex.
        self._vsync = bool(vsync)

        # Variables and flags used internally
        self.__is_drawing = False
        self.__title_info = {
            "raw": "",
            "fps": "?",
            "backend": self.__class__.__name__,
            "loop": self._rc_canvas_group.get_loop().__class__.__name__
            if (self._rc_canvas_group and self._rc_canvas_group.get_loop())
            else "no-loop",
        }
        self.__size_info = {
            "physical_size": (0, 0),
            "native_pixel_ratio": 1.0,
            "canvas_pixel_ratio": 1.0,
            "total_pixel_ratio": 1.0,
            "logical_size": (0.0, 0.0),
        }
        self.__need_size_event = False

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
            self.set_logical_size(*kwargs["size"])  # type: ignore
            self.set_title(kwargs["title"])  # type: ignore

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

    # %% Implement WgpuCanvasInterface

    _canvas_context = None  # set in get_context()

    def get_physical_size(self) -> Tuple[int, int]:
        """Get the physical size of the canvas in integer pixels."""
        return self.__size_info["physical_size"]

    def get_context(self, context_type: str) -> object:
        """Get a context object that can be used to render to this canvas.

        The context takes care of presenting the rendered result to the canvas.
        Different types of contexts are available:

        * "wgpu": get a ``WgpuCanvasContext`` provided by the ``wgpu`` library.
        * "bitmap": get a ``BitmapRenderingContext`` provided by the ``rendercanvas`` library.
        * "another.module": other libraries may provide contexts too. We've only listed the ones we know of.
        * "your.module:ContextClass": Explicit name.

        Later calls to this method, with the same context_type argument, will return
        the same context instance as was returned the first time the method was
        invoked. It is not possible to get a different context object once the first
        one has been created.
        """

        # Note that this method is analog to HtmlCanvas.getContext(), except
        # the context_type is different, since contexts are provided by other projects.

        if not isinstance(context_type, str):
            raise TypeError("context_type must be str.")

        # Resolve the context type name
        known_types = {
            "wgpu": "wgpu",
            "bitmap": "rendercanvas.utils.bitmaprenderingcontext",
        }
        resolved_context_type = known_types.get(context_type, context_type)

        # Is the context already set?
        if self._canvas_context is not None:
            if resolved_context_type == self._canvas_context._context_type:
                return self._canvas_context
            else:
                raise RuntimeError(
                    f"Cannot get context for '{context_type}': a context of type '{self._canvas_context._context_type}' is already set."
                )

        # Load module
        module_name, _, class_name = resolved_context_type.partition(":")
        try:
            module = importlib.import_module(module_name)
        except ImportError as err:
            raise ValueError(
                f"Cannot get context for '{context_type}': {err}. Known valid values are {set(known_types)}"
            ) from None

        # Obtain factory to produce context
        factory_name = class_name or "rendercanvas_context_hook"
        try:
            factory_func = getattr(module, factory_name)
        except AttributeError:
            raise ValueError(
                f"Cannot get context for '{context_type}': could not find `{factory_name}` in '{module.__name__}'"
            ) from None

        # Create the context
        context = factory_func(self, self._rc_get_present_methods())

        # Quick checks to make sure the context has the correct API
        if not (hasattr(context, "canvas") and context.canvas is self):
            raise RuntimeError(
                "The context does not have a canvas attribute that refers to this canvas."
            )
        if not (hasattr(context, "present") and callable(context.present)):
            raise RuntimeError("The context does not have a present method.")

        # Done
        self._canvas_context = context
        self._canvas_context._context_type = resolved_context_type
        return self._canvas_context

    # %% Events

    def _set_size_info(self, physical_size: Tuple[int, int], pixel_ratio: float):
        """Must be called by subclasses when their size changes.

        Backends must *not* submit a "resize" event; the base class takes care of that, because
        it requires some more attention than the other events.

        The subclass must call this when the actual viewport has changed. So not in ``_rc_set_logical_size()``,
        but e.g. when the underlying GUI layer fires a resize event, and maybe on init.

        The given pixel-ratio represents the 'native' pixel ratio. The canvas'
        zoom factor is multiplied with it to obtain the final pixel-ratio for
        this canvas.
        """
        self.__size_info["physical_size"] = int(physical_size[0]), int(physical_size[1])
        self.__size_info["native_pixel_ratio"] = float(pixel_ratio)
        self.__resolve_total_pixel_ratio_and_logical_size()

    def __resolve_total_pixel_ratio_and_logical_size(self):
        physical_size = self.__size_info["physical_size"]
        native_pixel_ratio = self.__size_info["native_pixel_ratio"]
        canvas_pixel_ratio = self.__size_info["canvas_pixel_ratio"]

        total_pixel_ratio = native_pixel_ratio * canvas_pixel_ratio
        logical_size = (
            physical_size[0] / total_pixel_ratio,
            physical_size[1] / total_pixel_ratio,
        )

        self.__size_info["total_pixel_ratio"] = total_pixel_ratio
        self.__size_info["logical_size"] = logical_size
        self.__need_size_event = True

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
        if self.__need_size_event:
            self.__need_size_event = False
            lsize = self.__size_info["logical_size"]
            self._events.emit(
                {
                    "event_type": "resize",
                    "width": lsize[0],
                    "height": lsize[1],
                    "pixel_ratio": self.__size_info["total_pixel_ratio"],
                    # Would be nice to have more details. But as it is now, PyGfx errors if we add fields it does not know, so let's do later.
                    # "logical_size": self.__size_info["logical_size"],
                    # "physical_size": self.__size_info["physical_size"],
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
        the resulting rendered image is presented to screen.

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
        self._rc_force_draw()

    def _draw_frame_and_present(self):
        """Draw the frame and present the result.

        Errors are logged to the "rendercanvas" logger. Should be called by the
        subclass at its draw event.
        """

        # Re-entrent drawing is problematic. Let's actively prevent it.
        if self.__is_drawing:
            return
        self.__is_drawing = True

        try:
            # This method is called from the GUI layer. It can be called from a
            # "draw event" that we requested, or as part of a forced draw.

            # Cannot draw to a closed canvas.
            if self._rc_get_closed():
                return

            # Note: could check whether the known physical size is > 0.
            # But we also consider it the responsiblity of the backend to not
            # draw if the size is zero. GUI toolkits like Qt do this correctly.
            # I might get back on this once we also draw outside of the draw-event ...

            # Make sure that the user-code is up-to-date with the current size before it draws.
            self.__maybe_emit_resize_event()

            # Emit before-draw
            self._events.emit({"event_type": "before_draw"})

            # Notify the scheduler
            if self.__scheduler is not None:
                fps = self.__scheduler.on_draw()

                # Maybe update title
                if fps is not None:
                    self.__title_info["fps"] = f"{fps:0.1f}"
                    if "$fps" in self.__title_info["raw"]:
                        self.set_title(self.__title_info["raw"])

            # Perform the user-defined drawing code. When this errors,
            # we should report the error and then continue, otherwise we crash.
            with log_exception("Draw error"):
                self._draw_frame()
            with log_exception("Present error"):
                # Note: we use canvas._canvas_context, so that if the draw_frame is a stub we also dont trigger creating a context.
                # Note: if vsync is used, this call may wait a little (happens down at the level of the driver or OS)
                context = self._canvas_context
                if context:
                    result = context.present()
                    method = result.pop("method")
                    if method in ("skip", "screen"):
                        pass  # nothing we need to do
                    elif method == "fail":
                        raise RuntimeError(result.get("message", "") or "present error")
                    else:
                        # Pass the result to the literal present method
                        func = getattr(self, f"_rc_present_{method}")
                        func(**result)

        finally:
            self.__is_drawing = False

    # %% Primary canvas management methods

    def get_logical_size(self) -> Tuple[float, float]:
        """Get the logical size (width, height) in float pixels.

        The logical size can be smaller than the physical size, e.g. on HiDPI
        monitors or when the user's system has the display-scale set to e.g. 125%.
        """
        return self.__size_info["logical_size"]

    def get_pixel_ratio(self) -> float:
        """Get the float ratio between logical and physical pixels.

        The pixel ratio is typically 1.0 for normal screens and 2.0 for HiDPI
        screens, but fractional values are also possible if the system
        display-scale is set to e.g. 125%. An HiDPI screen can be assumed if the
        pixel ratio >= 2.0. On MacOS (with a Retina screen) the pixel ratio is
        always 2.0.
        """
        return self.__size_info["total_pixel_ratio"]

    def close(self) -> None:
        """Close the canvas."""
        # Clear the draw-function, to avoid it holding onto e.g. wgpu objects.
        self._draw_frame = None  # type: ignore
        # Clear the canvas context too.
        if hasattr(self._canvas_context, "_release"):
            # ContextInterface (and GPUCanvasContext) has _release()
            try:
                self._canvas_context._release()  # type: ignore
            except Exception:
                pass
        self._canvas_context = None
        # Clean events. Should already have happened in loop, but the loop may not be running.
        self._events._release()
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
        self._rc_set_logical_size(width, height)

    def set_title(self, title: str) -> None:
        """Set the window title.

        The words "$backend", "$loop", and "$fps" can be used as variables that
        are filled in with the corresponding values.
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

    def _rc_get_present_methods(self):
        """Get info on the present methods supported by this canvas.

        Must return a small dict, used by the canvas-context to determine
        how the rendered result will be presented to the canvas.
        This method is only called once, when the context is created.

        Each supported method is represented by a field in the dict. The value
        is another dict with information specific to that present method.
        A canvas backend must implement at least either "screen" or "bitmap".

        With method "screen", the context will render directly to a surface
        representing the region on the screen. The sub-dict should have a ``window``
        field containing the window id. On Linux there should also be ``platform``
        field to distinguish between "wayland" and "x11", and a ``display`` field
        for the display id. This information is used by wgpu to obtain the required
        surface id.

        With method "bitmap", the context will present the result as an image
        bitmap. On GPU-based contexts, the result will first be rendered to an
        offscreen texture, and then downloaded to RAM. The sub-dict must have a
        field 'formats': a list of supported image formats. Examples are "rgba-u8"
        and "i-u8". A canvas must support at least "rgba-u8". Note that srgb mapping
        is assumed to be handled by the canvas.
        """
        raise NotImplementedError()

    def _rc_request_draw(self):
        """Request the GUI layer to perform a draw.

        Like requestAnimationFrame in JS. The draw must be performed
        by calling ``_draw_frame_and_present()``. It's the responsibility
        for the canvas subclass to make sure that a draw is made as
        soon as possible.

        The default implementation does nothing, which is equivalent to waiting
        for a forced draw or a draw invoked by the GUI system.
        """
        pass

    def _rc_force_draw(self):
        """Perform a synchronous draw.

        When it returns, the draw must have been done.
        The default implementation just calls ``_draw_frame_and_present()``.
        """
        self._draw_frame_and_present()

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        """Present the given image bitmap. Only used with present_method 'bitmap'.

        If a canvas supports special present methods, it will need to implement corresponding ``_rc_present_xx()`` methods.
        """
        raise NotImplementedError()

    def _rc_set_logical_size(self, width: float, height: float):
        """Set the logical size. May be ignired when it makes no sense.

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

    def get_context(self, context_type: str) -> object:
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

    def get_physical_size(self) -> Tuple[int, int]:
        return self._subwidget.get_physical_size()

    def get_logical_size(self) -> Tuple[float, float]:
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

import sys

from ._events import EventEmitter, EventType  # noqa: F401
from ._loop import Scheduler, BaseLoop, BaseTimer  # noqa: F401
from ._gui_utils import log_exception


# Notes on naming and prefixes:
#
# Since BaseRenderCanvas can be used as a mixin with classes in a GUI framework,
# we must avoid using generic names to avoid name clashes.
#
# * `.public_method`: Public API: usually at least two words, (except the close() method)
# * `._private_method`: Private methods for scheduler and subclasses.
# * `.__private_attr`: Private to exactly this class.
# * `._rc_method`: Methods that the subclass must implement.


class BaseRenderCanvas:
    """The base canvas class.

    This class provides a uniform canvas API so render systems can use
    code that is portable accross multiple GUI libraries and canvas targets.

    Arguments:
        size (tuple): the logical size (width, height) of the canvas.
        title (str): The title of the canvas.
        update_mode (EventType): The mode for scheduling draws and events. Default 'ondemand'.
        min_fps (float): A minimal frames-per-second to use when the ``update_mode`` is 'ondemand'.
            The default is 1: even without draws requested, it still draws every second.
        max_fps (float): A maximal frames-per-second to use when the ``update_mode`` is 'ondemand' or 'continuous'.
            The default is 30, which is usually enough.
        vsync (bool): Whether to sync the draw with the monitor update.  Helps
            against screen tearing, but can reduce fps. Default True.
        present_method (str | None): The method to present the rendered image.
            Can be set to 'screen' or 'image'. Default None (auto-select).

    """

    #
    __canvas_kwargs = dict(
        size=(640, 480),
        title="$backend",
        update_mode="ondemand",
        min_fps=1.0,
        max_fps=30.0,
        vsync=True,
        present_method=None,
    )

    def __init__(self, *args, **kwargs):
        # Extract canvas kwargs
        canvas_kwargs = {}
        for key, default in BaseRenderCanvas.__canvas_kwargs.items():
            val = kwargs.pop(key, default)
            if val is None:
                val = default
            canvas_kwargs[key] = val

        # Initialize superclass. Note that super() can be e.g. a QWidget, RemoteFrameBuffer, or object.
        super().__init__(*args, **kwargs)

        # If this is a wrapper, it should pass the canvas kwargs to the subwidget.
        if isinstance(self, WrapperRenderCanvas):
            self._rc_init(**canvas_kwargs)
            self.__events = self._subwidget.__events
            return

        # The vsync is not-so-elegantly strored on the canvas, and picked up by wgou's canvas contex.
        self._vsync = bool(canvas_kwargs["vsync"])

        # Variables and flags used internally
        self.__is_drawing = False
        self.__title_info = {
            "raw": "",
            "fps": "?",
            "backend": self.__class__.__name__,
        }

        # Events and scheduler
        self.__events = EventEmitter()
        self.__scheduler = None
        loop = self._rc_get_loop()
        if loop is not None:
            self.__scheduler = Scheduler(
                self,
                self.__events,
                self._rc_get_loop(),
                min_fps=canvas_kwargs["min_fps"],
                max_fps=canvas_kwargs["max_fps"],
                mode=canvas_kwargs["update_mode"],
            )

        # Initialze the canvas subclass
        self._rc_init(**canvas_kwargs)

        # Finalize the initialization
        self.set_logical_size(*canvas_kwargs["size"])
        self.set_title(canvas_kwargs["title"])

    def __del__(self):
        # On delete, we call the custom close method.
        try:
            self.close()
        except Exception:
            pass
        # Since this is sometimes used in a multiple inheritance, the
        # superclass may (or may not) have a __del__ method.
        try:
            super().__del__()
        except Exception:
            pass

    # %% Implement WgpuCanvasInterface

    _canvas_context = None  # set in get_context()

    def get_present_info(self):
        """Get information about the surface to render to.

        It must return a small dict, used by the canvas-context to determine
        how the rendered result should be presented to the canvas. There are
        two possible methods.

        If the ``method`` field is "screen", the context will render directly
        to a surface representing the region on the screen. The dict should
        have a ``window`` field containing the window id. On Linux there should
        also be ``platform`` field to distinguish between "wayland" and "x11",
        and a ``display`` field for the display id. This information is used
        by wgpu to obtain the required surface id.

        When the ``method`` field is "image", the context will render to a
        texture, download the result to RAM, and call ``canvas.present_image()``
        with the image data. Additional info (like format) is passed as kwargs.
        This method enables various types of canvases (including remote ones),
        but note that it has a performance penalty compared to rendering
        directly to the screen.

        The dict can further contain fields ``formats`` and ``alpha_modes`` to
        define the canvas capabilities. For the "image" method, the default
        formats is ``["rgba8unorm-srgb", "rgba8unorm"]``, and the default
        alpha_modes is ``["opaque"]``.
        """
        return self._rc_get_present_info()

    def get_physical_size(self):
        """Get the physical size of the canvas in integer pixels."""
        return self._rc_get_physical_size()

    def get_context(self, kind="webgpu"):
        """Get the ``GPUCanvasContext`` object corresponding to this canvas.

        The context is used to obtain a texture to render to, and to
        present that texture to the canvas. This class provides a
        default implementation to get the appropriate context.

        The ``kind`` argument is a remnant from the WebGPU spec and
        must always be "webgpu".
        """
        # Note that this function is analog to HtmlCanvas.getContext(), except
        # here the only valid arg is 'webgpu', which is also made the default.
        assert kind == "webgpu"
        if self._canvas_context is None:
            backend_module = ""
            if "wgpu" in sys.modules:
                backend_module = sys.modules["wgpu"].gpu.__module__
            if backend_module in ("", "wgpu._classes"):
                raise RuntimeError(
                    "A backend must be selected (e.g. with wgpu.gpu.request_adapter()) before canvas.get_context() can be called."
                )
            CanvasContext = sys.modules[backend_module].GPUCanvasContext  # noqa: N806
            self._canvas_context = CanvasContext(self)
        return self._canvas_context

    def present_image(self, image, **kwargs):
        """Consume the final rendered image.

        This is called when using the "image" method, see ``get_present_info()``.
        Canvases that don't support offscreen rendering don't need to implement
        this method.
        """
        self._rc_present_image(image, **kwargs)

    # %% Events

    def add_event_handler(self, *args, **kwargs):
        return self.__events.add_handler(*args, **kwargs)

    def remove_event_handler(self, *args, **kwargs):
        return self.__events.remove_handler(*args, **kwargs)

    def submit_event(self, event):
        # Not strictly necessary for normal use-cases, but this allows
        # the ._event to be an implementation detail to subclasses, and it
        # allows users to e.g. emulate events in tests.
        return self.__events.submit(event)

    add_event_handler.__doc__ = EventEmitter.add_handler.__doc__
    remove_event_handler.__doc__ = EventEmitter.remove_handler.__doc__
    submit_event.__doc__ = EventEmitter.submit.__doc__

    # %% Scheduling and drawing

    def _process_events(self):
        """Process events and animations. Called from the scheduler."""

        # We don't want this to be called too often, because we want the
        # accumulative events to accumulate. Once per draw, and at max_fps
        # when there are no draws (in ondemand and manual mode).

        # Get events from the GUI into our event mechanism.
        loop = self._rc_get_loop()
        if loop:
            loop._rc_gui_poll()

        # Flush our events, so downstream code can update stuff.
        # Maybe that downstream code request a new draw.
        self.__events.flush()

        # TODO: implement later (this is a start but is not tested)
        # Schedule animation events until the lag is gone
        # step = self._animation_step
        # self._animation_time = self._animation_time or time.perf_counter()  # start now
        # animation_iters = 0
        # while self._animation_time > time.perf_counter() - step:
        #     self._animation_time += step
        #     self.__events.submit({"event_type": "animate", "step": step, "catch_up": 0})
        #     # Do the animations. This costs time.
        #     self.__events.flush()
        #     # Abort when we cannot keep up
        #     # todo: test this
        #     animation_iters += 1
        #     if animation_iters > 20:
        #         n = (time.perf_counter() - self._animation_time) // step
        #         self._animation_time += step * n
        #         self.__events.submit(
        #             {"event_type": "animate", "step": step * n, "catch_up": n}
        #         )

    def _draw_frame(self):
        """The method to call to draw a frame.

        Cen be overriden by subclassing, or by passing a callable to request_draw().
        """
        pass

    def request_draw(self, draw_function=None):
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

    def force_draw(self):
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
            if self._rc_is_closed():
                return

            # Process special events
            # Note that we must not process normal events here, since these can do stuff
            # with the canvas (resize/close/etc) and most GUI systems don't like that.
            self.__events.emit({"event_type": "before_draw"})

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
                    context.present()

        finally:
            self.__is_drawing = False

    # %% Primary canvas management methods

    def get_logical_size(self):
        """Get the logical size (width, height) in float pixels."""
        return self._rc_get_logical_size()

    def get_pixel_ratio(self):
        """Get the float ratio between logical and physical pixels."""
        return self._rc_get_pixel_ratio()

    def close(self):
        """Close the canvas."""
        self._rc_close()

    def is_closed(self):
        """Get whether the window is closed."""
        return self._rc_is_closed()

    # %% Secondary canvas management methods

    # These methods provide extra control over the canvas. Subclasses should
    # implement the methods they can, but these features are likely not critical.

    def set_logical_size(self, width, height):
        """Set the window size (in logical pixels)."""
        width, height = float(width), float(height)
        if width < 0 or height < 0:
            raise ValueError("Canvas width and height must not be negative")
        self._rc_set_logical_size(width, height)

    def set_title(self, title):
        """Set the window title."""
        self.__title_info["raw"] = title
        for k, v in self.__title_info.items():
            title = title.replace("$" + k, v)
        self._rc_set_title(title)

    # %% Methods for the subclass to implement

    def _rc_init(self, *, present_method):
        """Method to initialize the canvas.

        This method is called near the end of the initialization
        process, but before setting things like size and title.
        """
        pass

    def _rc_get_loop(self):
        """Get the loop instance for this backend.

        Must return the global loop instance (a BaseLoop subclass) for the canvas subclass,
        or None for a canvas without scheduled draws.
        """
        return None

    def _rc_get_present_info(self):
        """Get present info. See the corresponding public method."""
        raise NotImplementedError()

    def _rc_request_draw(self):
        """Request the GUI layer to perform a draw.

        Like requestAnimationFrame in JS. The draw must be performed
        by calling _draw_frame_and_present(). It's the responsibility
        for the canvas subclass to make sure that a draw is made as
        soon as possible.

        Canvases that have a limit on how fast they can 'consume' frames, like
        remote frame buffers, do good to call self._process_events() when the
        draw had to wait a little. That way the user interaction will lag as
        little as possible.

        The default implementation does nothing, which is equivalent to waiting
        for a forced draw or a draw invoked by the GUI system.
        """
        pass

    def _rc_force_draw(self):
        """Perform a synchronous draw.

        When it returns, the draw must have been done.
        The default implementation just calls _draw_frame_and_present().
        """
        self._draw_frame_and_present()

    def _rc_present_image(self, image, **kwargs):
        """Present the given image. Only used with present_method 'image'."""
        raise NotImplementedError()

    def _rc_get_physical_size(self):
        """Get the physical size (with, height) in integer pixels."""
        raise NotImplementedError()

    def _rc_get_logical_size(self):
        """Get the logical size (with, height) in float pixels."""
        raise NotImplementedError()

    def _rc_get_pixel_ratio(self):
        """Get ratio between physical and logical size."""
        raise NotImplementedError()

    def _rc_set_logical_size(self, width, height):
        """Set the logical size. May be ignired when it makes no sense.

        The default implementation does nothing.
        """
        pass

    def _rc_close(self):
        """Close the canvas.

        Note that ``BaseRenderCanvas`` implements the ``close()`` method, which
        is a rather common name; it may be necessary to re-implement that too.
        """
        raise NotImplementedError()

    def _rc_is_closed(self):
        """Get whether the canvas is closed."""
        raise NotImplementedError()

    def _rc_set_title(self):
        """Set the canvas title. May be ignored when it makes no sense.

        The default implementation does nothing.
        """
        pass


class WrapperRenderCanvas(BaseRenderCanvas):
    """A base render canvas for top-level windows that wrap a widget, as used in e.g. Qt and wx.

    This base class implements all the re-direction logic, so that the subclass does not have to.
    Wrapper classes should not implement any of the ``_rc_`` methods.
    """

    # Must implement

    def get_context(self, *args, **kwargs):
        return self._subwidget.get_context(*args, **kwargs)

    # So these should not be necessary

    def get_present_info(self):
        raise NotImplementedError()

    def present_image(self, image, **kwargs):
        raise NotImplementedError()

    # More redirection

    def request_draw(self, *args, **kwargs):
        return self._subwidget.request_draw(*args, **kwargs)

    def force_draw(self):
        self._subwidget.force_draw()

    def get_physical_size(self):
        return self._subwidget.get_physical_size()

    def get_logical_size(self):
        return self._subwidget.get_logical_size()

    def get_pixel_ratio(self):
        return self._subwidget.get_pixel_ratio()

    def set_logical_size(self, width, height):
        self._subwidget.set_logical_size(width, height)

    def set_title(self, *args):
        self._subwidget.set_title(*args)

    def close(self):
        self._subwidget.close()

    def is_closed(self):
        return self._subwidget.is_closed()

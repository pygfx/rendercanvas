"""
A stub backend for documentation purposes.
"""

__all__ = ["RenderCanvas", "StubLoop", "StubRenderCanvas", "loop"]

from .base import BaseCanvasGroup, BaseLoop, BaseRenderCanvas, WrapperRenderCanvas


class StubLoop(BaseLoop):
    """
    The ``Loop`` represents the event-loop that drives the rendering and events.

    Some backends will provide a corresponding loop (like qt and wx). Other backends may use
    existing loops (like glfw and jupyter). And then there are loop-backends that only implement
    a loop (e.g. asyncio or trio).

    Backends must subclass ``BaseLoop`` and implement a set of methods prefixed with ``_rc_``.
    """

    def _rc_init(self):
        # Put the loop in a ready state.
        #
        # Called when the first canvas is created to run in this loop. This is when we
        # know pretty sure that this loop is going to be used, so time to start the
        # engines. Note that in interactive settings, this method can be called again, after the
        # loop has stopped, to restart it.
        #
        # * Import any dependencies.
        # * If this loop supports some kind of interactive mode, activate it!
        # * Optionally call ``_mark_as_interactive()``.
        # * Make sure its ok if this is called a second time, after a run.
        # * Returns None.
        raise NotImplementedError()

    def _rc_run(self):
        # Start running the event-loop.
        #
        # * Start the event-loop.
        # * The loop object must also work when the native loop is started
        #   in the GUI-native way (i.e. this method may not be called).
        # * If the backend is in interactive mode (i.e. there already is
        #   an active native loop) this may return directly.
        # * Returns None.
        raise NotImplementedError()

    async def _rc_run_async(self):
        # Start running the event-loop in an async task.
        #
        # This only applies to loop backends that represent an async framework such as Asyncio or Trio.
        # Other backends can ``raise NotImplementedError()``.
        raise NotImplementedError()

    def _rc_stop(self):
        # Clean up the loop, going to the off-state.
        #
        # * Stop the running event-loop, if applicable.
        # * Be ready for another call to ``_rc_init()`` in case the loop is reused.
        # * Returns None.
        raise NotImplementedError()

    def _rc_call_soon(self, callback):
        # Method to schedule a callback.
        #
        # Depending on the backend, this can sometimes use a faster/easier path than ``_rc_call_soon_threadsafe``.
        #
        # * The callback should be fired as soon as possible, but in a new event-loop iteration (i.e. not *now*).
        # * The callbacks should be fired in the same order as they are scheduled (by calling this method).
        # * Don't catch errors from the callback; the base class deals with that.
        # * Returns None.
        raise NotImplementedError()

    def _rc_call_soon_threadsafe(self, callback):
        # Method to schedule a callback in the loop's thread.
        #
        # Must be thread-safe; this may be called from a different thread.
        raise NotImplementedError()

    def _rc_call_later(self, delay, callback):
        # Method to call a callback in delay number of seconds.
        #
        # It's optional for backends to implement this method; the default implementation uses
        # ``call_later_from_thread`` and then ``_rc_call_soon_threadsafe``. When overloading this
        # method, keep in mind the notorious inaccurate timers on Windows!
        #
        # * The callback should be fired in delay seconds.
        # * Multiple callbacks scheduled in quick succession with the same delay, should fire in the order they are scheduled.
        # * Don't catch errors from the callback; the base class deals with that.
        # * There's no need to check whether ``delay <= 0``; the base class deals with that.
        # * Returns None.
        super()._rc_call_later(delay, callback)  # accurate method based on threading


loop = StubLoop()


class StubCanvasGroup(BaseCanvasGroup):
    """
    The ``CanvasGroup`` represents a group of canvas objects from the same class, that share a loop.

    The initial/default loop is passed when the ``CanvasGroup`` is instantiated.

    Backends can subclass ``BaseCanvasGroup`` and set an instance at their ``RenderCanvas._rc_canvas_group``.
    It can also be omitted for canvases that don't need to run in a loop. Note that this class is only
    for internal use, mainly to connect canvases to a loop; it is not public API.

    The subclassing is only really done so the group has a distinguishable name. Though we may add ``_rc_`` methods
    to this class in the future.
    """


class StubRenderCanvas(BaseRenderCanvas):
    """
    The ``RenderCanvas`` represents the canvas to render to.

    Backends must subclass ``BaseRenderCanvas`` and implement a set of methods
    prefixed with ``_rc_``.

    Backends must call ``self._final_canvas_init()`` at the end of its
    ``__init__()``. This will set the canvas' logical size and title.

    Backends must call ``self._size_info.set_physical_size(width, height, native_pixel_ratio)``
    whenever the size or pixel ratio changes. It must be
    called when the actual viewport has changed, so typically not in
    ``_rc_set_logical_size()``, but e.g. when the underlying GUI layer fires a
    resize event. Setting the size implicitly requests a new draw.

    Backends must also call ``self.submit_event()``, if applicable, to produce
    events for mouse and keyboard. Backends must *not* submit "resize" or
    "close" events; the base class takes care of that. See the event spec for
    more details.

    Backends must make sure that all closing flows (e.g. a user pressing the cross)
    lead to ``close()`` being called.
    """

    # Note that the methods below don't have docstrings, but Sphinx recovers the docstrings from the base class.

    _rc_canvas_group = StubCanvasGroup(loop)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # backend-specific init
        self._final_canvas_init()  # <-- Backends must call this near the end of their init

    def _rc_gui_poll(self):
        # Process native events.
        #
        # This method is called by the base class before each draw to move
        # GUI events into the rendercanvas event system.
        #
        # In some cases one can naturally assume that the 'native' backend is running
        # and events are already processed. E.g. when in a notebook-like env.
        #
        # In cases where the backend comes with its own event loop that already processes
        # events, ``_rc_gui_poll``  only need to do a poll if the current loop is
        # *not* the backend's own loop. E.g. qt and wx.
        raise NotImplementedError()

    def _rc_get_present_info(self, present_methods):
        # Select a present method and return corresponding info dict.
        #
        # This method is only called once, when the context is created. The
        # subclass can use this moment to setup the internal state for the
        # selected presentation method.
        #
        # The ``present_methods`` represents the supported methods of the
        # canvas-context, in order of context-preference, possibly filtered by a
        # user-specified method. A canvas backend must implement at least the
        # "screen" or "bitmap" method.
        #
        # The returned dict must contain at least the key 'method', which must
        # match one of the ``present_methods``. The remaining values represent
        # information required by the canvas-context to perform the presentation,
        # and optionally some (debug) meta data. The backend may optionally return
        # None to indicate that none of the ``present_methods`` is supported.
        #
        # With method "screen", the context will render directly to a (virtual)
        # surface. The dict should have a ``window`` field containing the window
        # id. On Linux there should also be ``platform`` field to distinguish
        # between "wayland" and "x11", and a ``display`` field for the display id.
        # This information is used by wgpu to obtain the required surface id. For
        # Pyodide the 'window' field should be the ``<canvas>`` object.
        #
        # With method "bitmap", the context will present the result as an image
        # bitmap. For the ``WgpuContext``, the result will first be rendered to a
        # texture, and then downloaded to RAM. The dict must have a field
        # 'formats': a list of supported image formats. Examples are "rgba-u8" and
        # "i-u8". A canvas must support at least "rgba-u8". Note that srgb mapping
        # is assumed to be handled by the canvas.
        return None

    def _rc_request_draw(self):
        # Request the backend to call ``_time_to_draw()``.
        #
        # The backend must call ``_time_to_draw`` as soon as it's ready for the
        # next frame. It is allowed to call it directly (rather than scheduling
        # it). It can also be called later, but it must be called eventually,
        # otherwise it will halt the rendering.
        #
        # This functionality allows the backend to throttle the frame rate. For
        # instance, backends that implement 'remote' rendering can allow new
        # frames based on the number of in-flight frames and downstream
        # throughput.
        #
        #  Backends that render on the current machine should simply call
        #  ``_time_to_draw()`` directly.
        self._time_to_draw()

    def _rc_request_paint(self):
        # Request the backend to do a paint, and call ``_time_to_paint()``.
        #
        # The backend must schedule ``_time_to_paint`` to be called as soon as
        # possible, but (if applicable) it must be in the native animation frame,
        # a.k.a. draw event. This function is analog to ``requestAnimationFrame``
        # in JavaScript. In any case, inside ``_time_to_paint()`` a call like
        # ``context.get_current_texture()`` should be allowed.
        #
        # When the present-method is 'screen', this method is called to initiate a
        # draw. When the present-method is 'bitmap', it is called when the draw
        # (and present) is completed, so the native system can repaint with the
        # latest rendered frame.
        #
        # If the implementation of this method does nothing, it is equivalent to
        # waiting for a forced draw or a draw invoked by the GUI system.
        pass

    def _rc_force_paint(self):
        # Perform a synchronous paint.
        #
        # The backend should, if possible, invoke its native paint event right now (synchronously).
        # The default implementation just calls ``_time_to_paint()``.
        self._time_to_paint()

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        # Present the given image bitmap. Only used with present_method 'bitmap'.
        #
        # If a canvas supports special present methods, it will need to implement corresponding ``_rc_present_xx()`` methods.
        raise NotImplementedError()

    def _rc_set_logical_size(self, width, height):
        # Set the size of the canvas in logical pixels.
        #
        # May be ignored when it makes no sense.
        # The default implementation does nothing.
        pass

    def _rc_close(self):
        # Close the canvas.
        #
        # This is the place to delete the native widget. It is not necessary to
        # emit a close event, because the base class handles that.
        #
        # In a backend, all flows that lead to a close must call ``.close()``, so
        # that ``BaseRenderCanvas`` has a clear place to handle closing. It calls
        # ``_rc_close()`` from there. The base class will call this method exactly once.
        #
        # Note that if this is the last canvas to close, the loop is stopped immediately,
        # and some backends need some explicit polling in this case. Also see wx and glfw backends.
        #
        # Note that if this backend class inherits both the native class and BaseRenderCanvas,
        # and the native class has a ``close()`` method, it is overridden by BaseRenderCanvas.
        pass

    def _rc_set_title(self, title):
        # Set the canvas title.
        #
        # May be ignored when it makes no sense.
        # The default implementation does nothing.
        pass

    def _rc_set_cursor(self, cursor):
        # Set the cursor shape.
        #
        # May be ignored when it makes no sense.
        # The default implementation does nothing.
        pass


class ToplevelRenderCanvas(WrapperRenderCanvas):
    """
    Some backends require a toplevel wrapper. These can inherit from ``WrapperRenderCanvas``.
    These have to instantiate the wrapped canvas and set it as ``_subwidget``. Implementations
    are typically very small.
    """

    def __init__(self, parent=None, **kwargs):
        super().__init__(parent)

        self._subwidget = StubRenderCanvas(self, **kwargs)


# Make available under a common name
RenderCanvas = StubRenderCanvas
loop = StubLoop()

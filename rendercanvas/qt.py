"""
Support for rendering in a Qt widget. Provides a widget subclass that
can be used as a standalone window or in a larger GUI.
"""

__all__ = ["QRenderCanvas", "QRenderWidget", "QtLoop", "RenderCanvas", "loop"]

import sys
import ctypes
import weakref
import importlib


from .base import WrapperRenderCanvas, BaseCanvasGroup, BaseRenderCanvas, BaseLoop
from ._coreutils import (
    logger,
    SYSTEM_IS_WAYLAND,
    get_alt_x11_display,
    get_alt_wayland_display,
    select_qt_lib,
)


# Select GUI toolkit
libname, already_had_app_on_import = select_qt_lib()
if libname:
    QtCore = importlib.import_module(".QtCore", libname)
    QtGui = importlib.import_module(".QtGui", libname)
    QtWidgets = importlib.import_module(".QtWidgets", libname)
    # Uncomment the line below to try QtOpenGLWidgets.QOpenGLWidget instead of QWidget
    # QtOpenGLWidgets = importlib.import_module(".QtOpenGLWidgets", libname)
    if libname.startswith("PyQt"):
        # PyQt5 or PyQt6
        WA_InputMethodEnabled = QtCore.Qt.WidgetAttribute.WA_InputMethodEnabled
        KeyboardModifiers = QtCore.Qt.KeyboardModifier
        WA_PaintOnScreen = QtCore.Qt.WidgetAttribute.WA_PaintOnScreen
        WA_DeleteOnClose = QtCore.Qt.WidgetAttribute.WA_DeleteOnClose
        PreciseTimer = QtCore.Qt.TimerType.PreciseTimer
        FocusPolicy = QtCore.Qt.FocusPolicy
        CursorShape = QtCore.Qt.CursorShape
        WinIdChange = QtCore.QEvent.Type.WinIdChange
        Signal = QtCore.pyqtSignal
        Slot = QtCore.pyqtSlot
        Keys = QtCore.Qt.Key
        is_pyside = False
    else:
        # Pyside2 or PySide6
        WA_InputMethodEnabled = QtCore.Qt.WA_InputMethodEnabled
        KeyboardModifiers = QtCore.Qt
        WA_PaintOnScreen = QtCore.Qt.WA_PaintOnScreen
        WA_DeleteOnClose = QtCore.Qt.WA_DeleteOnClose
        PreciseTimer = QtCore.Qt.PreciseTimer
        FocusPolicy = QtCore.Qt
        CursorShape = QtCore.Qt
        WinIdChange = QtCore.QEvent.WinIdChange
        Signal = QtCore.Signal
        Slot = QtCore.Slot
        Keys = QtCore.Qt
        is_pyside = True

else:
    raise ImportError(
        "Before importing rendercanvas.qt, import one of PySide6/PySide2/PyQt6/PyQt5 to select a Qt toolkit."
    )


def check_qt_libname(expected_libname):
    """Little helper for the qt backends that represent a specific qt lib."""
    if expected_libname != libname:
        raise RuntimeError(
            f"Failed to load rendercanvas.qt with {expected_libname}, because rendercanvas.qt is already loaded with {libname}."
        )


# Get version
if libname.startswith("PySide"):
    qt_version_info = QtCore.__version_info__
else:
    try:
        qt_version_info = tuple(int(i) for i in QtCore.QT_VERSION_STR.split(".")[:3])
    except Exception:  # Failsafe
        qt_version_info = (0, 0, 0)


BUTTON_MAP = {
    QtCore.Qt.MouseButton.LeftButton: 1,  # == MOUSE_BUTTON_LEFT
    QtCore.Qt.MouseButton.RightButton: 2,  # == MOUSE_BUTTON_RIGHT
    QtCore.Qt.MouseButton.MiddleButton: 3,  # == MOUSE_BUTTON_MIDDLE
    QtCore.Qt.MouseButton.BackButton: 4,
    QtCore.Qt.MouseButton.ForwardButton: 5,
    QtCore.Qt.MouseButton.TaskButton: 6,
    QtCore.Qt.MouseButton.ExtraButton4: 7,
    QtCore.Qt.MouseButton.ExtraButton5: 8,
}

MODIFIERS_MAP = {
    KeyboardModifiers.ShiftModifier: "Shift",
    KeyboardModifiers.ControlModifier: "Control",
    KeyboardModifiers.AltModifier: "Alt",
    KeyboardModifiers.MetaModifier: "Meta",
}

KEY_MAP = {
    int(Keys.Key_Down): "ArrowDown",
    int(Keys.Key_Up): "ArrowUp",
    int(Keys.Key_Left): "ArrowLeft",
    int(Keys.Key_Right): "ArrowRight",
    int(Keys.Key_Backspace): "Backspace",
    int(Keys.Key_CapsLock): "CapsLock",
    int(Keys.Key_Delete): "Delete",
    int(Keys.Key_End): "End",
    int(Keys.Key_Enter): "Enter",
    int(Keys.Key_Escape): "Escape",
    int(Keys.Key_F1): "F1",
    int(Keys.Key_F2): "F2",
    int(Keys.Key_F3): "F3",
    int(Keys.Key_F4): "F4",
    int(Keys.Key_F5): "F5",
    int(Keys.Key_F6): "F6",
    int(Keys.Key_F7): "F7",
    int(Keys.Key_F8): "F8",
    int(Keys.Key_F9): "F9",
    int(Keys.Key_F10): "F10",
    int(Keys.Key_F11): "F11",
    int(Keys.Key_F12): "F12",
    int(Keys.Key_Home): "Home",
    int(Keys.Key_Insert): "Insert",
    int(Keys.Key_Alt): "Alt",
    int(Keys.Key_Control): "Control",
    int(Keys.Key_Shift): "Shift",
    int(Keys.Key_Meta): "Meta",  # meta maps to control in QT on macOS, and vice-versa
    int(Keys.Key_NumLock): "NumLock",
    int(Keys.Key_PageDown): "PageDown",
    int(Keys.Key_PageUp): "PageUp",
    int(Keys.Key_Pause): "Pause",
    int(Keys.Key_ScrollLock): "ScrollLock",
    int(Keys.Key_Tab): "Tab",
}

CURSOR_MAP = {
    "default": CursorShape.ArrowCursor,
    "text": CursorShape.IBeamCursor,
    "crosshair": CursorShape.CrossCursor,
    "pointer": CursorShape.PointingHandCursor,
    "ew-resize": CursorShape.SizeHorCursor,
    "ns-resize": CursorShape.SizeVerCursor,
    "nesw-resize": CursorShape.SizeBDiagCursor,
    "nwse-resize": CursorShape.SizeFDiagCursor,
    "not-allowed": CursorShape.ForbiddenCursor,
    "none": CursorShape.BlankCursor,
}


BITMAP_FORMAT_MAP = {
    "rgba-u8": QtGui.QImage.Format.Format_RGBA8888,
    "rgb-u8": QtGui.QImage.Format.Format_RGB888,
    "i-u8": QtGui.QImage.Format.Format_Grayscale8,
    "i-u16": QtGui.QImage.Format.Format_Grayscale16,
}


def enable_hidpi():
    """Enable high-res displays."""
    set_dpi_aware = qt_version_info < (6, 4)  # Pyside
    if set_dpi_aware:
        try:
            # See https://github.com/pyzo/pyzo/pull/700 why we seem to need both
            # See https://github.com/pygfx/pygfx/issues/368 for high Qt versions
            ctypes.windll.shcore.SetProcessDpiAwareness(1)  # global dpi aware
            ctypes.windll.shcore.SetProcessDpiAwareness(2)  # per-monitor dpi aware
        except Exception:
            pass  # fail on non-windows
    try:
        # https://doc.qt.io/qtforpython-6/faq/porting_from2.html#class-function-deprecations
        # > High DPI is by default enabled in Qt 6 and cannot be turned off.
        dpi_scaling_not_deprecated = qt_version_info[0] < 6
        if dpi_scaling_not_deprecated:
            QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling, True)
    except Exception:
        pass  # fail on older Qt's


# If you import this module, you want to render in a way that does not suck
# on high-res monitors. So we apply the minimal configuration to make this so.
# Most apps probably should also set AA_UseHighDpiPixmaps, but it's not
# needed, so not our responsibility (some users may NOT want it set).
enable_hidpi()

_show_image_method_warning = (
    "Qt falling back to offscreen rendering, which is less performant."
)


class CallerHelper(QtCore.QObject):
    """Little helper for _rc_call_soon_threadsafe"""

    call = Signal(object)

    def __init__(self):
        super().__init__()
        self.call.connect(lambda f: f())


class QtLoop(BaseLoop):
    _app = None
    _we_run_the_loop = False

    def _rc_init(self):
        if self._app is None:
            self._app = QtWidgets.QApplication.instance()
            if self._app is None:
                self._app = QtWidgets.QApplication([])
        # We do detect when the canvas-widget is closed, and also when *our* toplevel wrapper is closed,
        # but when embedded in an application, it seems hard/impossible to detect the canvas being closed
        # when the app closes. So we explicitly detect the app-closing instead.
        # Note that we should not use app.setQuitOnLastWindowClosed(False), because we (may) rely on the
        # application's closing mechanic.
        loop_ref = weakref.ref(self)
        self._app.aboutToQuit.connect(
            lambda: (loop := loop_ref()) and loop.stop(force=True)
        )
        if already_had_app_on_import:
            self._mark_as_interactive()
        self._caller = CallerHelper()

    def _rc_run(self):
        # Note: we could detect if asyncio is running (interactive session) and whether
        # we can use QtAsyncio. However, there's no point because that's up for the
        # end-user to decide.

        # Note: its possible, and perfectly ok, if the application is started from user
        # code. This works fine because the application object is global. This means
        # though, that we cannot assume anything based on whether this method is called
        # or not.

        if already_had_app_on_import:
            return

        self._we_run_the_loop = True
        try:
            app = self._app
            app.exec() if hasattr(app, "exec") else app.exec_()
        finally:
            self._we_run_the_loop = False

    async def _rc_run_async(self):
        raise NotImplementedError()

    def _rc_stop(self):
        # Note: is only called when we're inside _rc_run
        if self._we_run_the_loop:
            self._app.quit()

    def _rc_add_task(self, async_func, name):
        # we use the async adapter with call_later
        return super()._rc_add_task(async_func, name)

    def _rc_call_later(self, delay, callback):
        if delay <= 0:
            QtCore.QTimer.singleShot(0, callback)
            # or self._caller.call.emit(callback)
        else:
            QtCore.QTimer.singleShot(int(max(delay * 1000, 1)), callback)

    def _rc_call_soon_threadsafe(self, callback):
        # Because this goes through a signal/slot, it's thread-safe
        self._caller.call.emit(callback)


loop = QtLoop()


class QtCanvasGroup(BaseCanvasGroup):
    pass


class QRenderWidget(BaseRenderCanvas, QtWidgets.QWidget):
    """A QWidget representing a render canvas that can be embedded in a Qt application."""

    _rc_canvas_group = QtCanvasGroup(loop)

    def __init__(self, *args, present_method=None, **kwargs):
        super().__init__(*args, **kwargs)

        # Determine present method
        self._last_winid = None
        self._surface_ids = None
        if not present_method:
            self._present_to_screen = True
            if SYSTEM_IS_WAYLAND:
                # Trying to render to screen on Wayland segfaults. This might be because
                # the "display" is not the real display id. We can tell Qt to use
                # XWayland, so we can use the X11 path. This worked at some point,
                # but later this resulted in a Rust panic. So, until this is sorted
                # out, we fall back to rendering via an image.
                self._present_to_screen = False
        elif present_method == "screen":
            self._present_to_screen = True
        elif present_method == "bitmap":
            global _show_image_method_warning

            _show_image_method_warning = None
            self._present_to_screen = False
        else:
            raise ValueError(f"Invalid present_method {present_method}")

        self._is_closed = False

        self.setAutoFillBackground(False)
        self.setAttribute(WA_DeleteOnClose, True)
        self.setAttribute(WA_InputMethodEnabled, True)
        self.setMouseTracking(True)
        self.setFocusPolicy(FocusPolicy.StrongFocus)

        # Set size, title, etc.
        self._final_canvas_init()

    def event(self, event):
        if self._present_to_screen:
            if event.type() == WinIdChange and self._last_winid is not None:
                winid = int(self.winId())
                if winid != self._last_winid:
                    logger.warning(f"WinId changed from {self._last_winid} {winid}.")
                    self._last_winid = winid
        return super().event(event)

    def _get_surface_ids(self):
        if sys.platform.startswith("win") or sys.platform.startswith("darwin"):
            return {
                "window": int(self.winId()),
            }
        elif sys.platform.startswith("linux"):
            if False:
                # We fall back to XWayland, see _coreutils.py
                return {
                    "platform": "wayland",
                    "window": int(self.winId()),
                    "display": int(get_alt_wayland_display()),
                }
            else:
                return {
                    "platform": "x11",
                    "window": int(self.winId()),
                    "display": int(get_alt_x11_display()),
                }
        else:
            logger.warning(f"Cannot get Qt surface info on {sys.platform}.")
            return None

    # %% Qt methods

    def paintEngine(self):  # noqa: N802 - this is a Qt method
        # https://doc.qt.io/qt-5/qt.html#WidgetAttribute-enum  WA_PaintOnScreen
        if self._present_to_screen:
            return None
        else:
            return super().paintEngine()

    def paintEvent(self, event):  # noqa: N802 - this is a Qt method
        self._draw_frame_and_present()

    def update(self):
        # Bypass Qt's mechanics and request a draw so that the scheduling mechanics work as intended.
        # Eventually this will call _request_draw().
        self.request_draw()

    # %% Methods to implement RenderCanvas

    def _rc_gui_poll(self):
        if isinstance(self._rc_canvas_group.get_loop(), QtLoop):
            # If the Qt event loop is running, qt events are already processed, and calling processEvents() will cause recursive repaints.
            pass
        else:
            # Running from another loop. Not recommended, but it could work.
            loop._app.sendPostedEvents()
            loop._app.processEvents()

    def _rc_get_present_methods(self):
        global _show_image_method_warning

        if self._present_to_screen and self._surface_ids is None:
            self._surface_ids = self._get_surface_ids()
            if self._surface_ids is None:
                self._present_to_screen = False

        methods = {}
        if self._present_to_screen:
            methods["screen"] = self._surface_ids
            # Now is a good time to set WA_PaintOnScreen. Note that it implies WA_NativeWindow.
            self.setAttribute(WA_PaintOnScreen, self._present_to_screen)
        else:
            if _show_image_method_warning:
                logger.warning(_show_image_method_warning)
                _show_image_method_warning = None
            methods["bitmap"] = {"formats": list(BITMAP_FORMAT_MAP.keys())}
        return methods

    def _rc_request_draw(self):
        # Ask Qt to do a paint event
        QtWidgets.QWidget.update(self)

        # When running on another loop, schedule processing events asap
        loop = self._rc_canvas_group.get_loop()
        if not isinstance(loop, QtLoop):
            loop.call_soon(self._rc_gui_poll)

    def _rc_force_draw(self):
        # Call the paintEvent right now.
        # This works on all platforms I tested, except on MacOS when drawing with the 'image' method.
        # Not sure why this is. It be made to work by calling processEvents() but that has all sorts
        # of nasty side-effects (e.g. the scheduler timer keeps ticking, invoking other draws, etc.).
        self.repaint()

    def _rc_present_bitmap(self, *, data, format, **kwargs):
        # Notes on performance:
        #
        # In the early stage of https://github.com/pygfx/rendercanvas/pull/138,
        # with a single copy-buffer, running the cube example on my M1, with
        # bitmap-present, I get about 75 FPS.
        #
        # AK: I tried to make this a QLabel and update a QPixmap by doing
        # self._pixmap.convertFromImage(qImage), but this is much slower.
        #
        # AK: I tried to maintain a self._qimage, so that it maybe gets bound
        # internally to a texture, but that even makes it slightly slower.
        #
        # AK: I tried inheriting from QOpenGLWidget, because I saw a blog post
        # (https://doc.qt.io/archives/qt-5.15/qtopengl-2dpainting-example.html)
        # that says it will make the painter hardware accelerated.
        # Interestingly, the content is drawn different to screen, as if the
        # rect args to drawImage are interpreted differently (or wrong), which
        # suggests that the painter *does* take a different path. Also, it can
        # be observed that the CPU usage is less that with QWidget. However, the
        # performance does not significantly increase (in my tests)
        #
        # If I understand things correctly, Qt uses composition on the CPU, so
        # there is an inherent limit to the performance. Rendering with GL likely
        # includes downloading the rendered image for composition.
        #
        # Also see https://github.com/pygfx/rendercanvas/pull/139

        width, height = data.shape[1], data.shape[0]  # width, height

        # Wrap the data in a QImage (no copy)
        qtformat = BITMAP_FORMAT_MAP[format]
        bytes_per_line = data.strides[0]
        image = QtGui.QImage(data, width, height, bytes_per_line, qtformat)

        # Prep drawImage rects
        rect1 = QtCore.QRect(0, 0, width, height)
        rect2 = self.rect()

        # Paint the image. Nearest neighbor interpolation, like the other backends.
        painter = QtGui.QPainter(self)
        painter.setRenderHints(painter.RenderHint.Antialiasing, False)
        painter.setRenderHints(painter.RenderHint.SmoothPixmapTransform, False)
        painter.drawImage(rect2, image, rect1)
        painter.end()

    def _rc_set_logical_size(self, width, height):
        width, height = int(width), int(height)
        parent = self.parent()
        if isinstance(parent, QRenderCanvas):
            parent.resize(width, height)
        else:
            self.resize(width, height)  # See comment on pixel ratio

    def _rc_close(self):
        if self._is_closed:
            return
        parent = self.parent()
        if isinstance(parent, QRenderCanvas):
            QtWidgets.QWidget.close(parent)
        else:
            QtWidgets.QWidget.close(self)

    def _rc_get_closed(self):
        return self._is_closed

    def _rc_set_title(self, title):
        # A QWidgets title can actually be shown when the widget is shown in a dock.
        # But the application should probably determine that title, not us.
        parent = self.parent()
        if isinstance(parent, QRenderCanvas):
            parent.setWindowTitle(title)

    def _rc_set_cursor(self, cursor):
        cursor_flag = CURSOR_MAP.get(cursor)
        if cursor_flag is None:
            self.unsetCursor()
        else:
            self.setCursor(cursor_flag)

    # %% Turn Qt events into rendercanvas events

    def _key_event(self, event_type, event):
        modifiers = tuple(
            MODIFIERS_MAP[mod]
            for mod in MODIFIERS_MAP.keys()
            if mod & event.modifiers()
        )

        ev = {
            "event_type": event_type,
            "key": KEY_MAP.get(event.key(), event.text()),
            "modifiers": modifiers,
        }

        if not event.isAutoRepeat():
            self.submit_event(ev)

    def _char_input_event(self, char_str):
        ev = {
            "event_type": "char",
            "data": char_str,
            "char_str": char_str,  # compat, remove few months from nov '25
            "modifiers": None,
        }
        self.submit_event(ev)

    def keyPressEvent(self, event):  # noqa: N802
        self._key_event("key_down", event)
        self._char_input_event(event.text())

    def keyReleaseEvent(self, event):  # noqa: N802
        self._key_event("key_up", event)

    def inputMethodEvent(self, event):  # noqa: N802
        commit_string = event.commitString()
        if commit_string:
            self._char_input_event(commit_string)

    def _mouse_event(self, event_type, event, touches=True):
        button = BUTTON_MAP.get(event.button(), 0)
        buttons = tuple(
            BUTTON_MAP[button]
            for button in BUTTON_MAP.keys()
            if button & event.buttons()
        )

        # For Qt on macOS Control and Meta are switched
        modifiers = tuple(
            MODIFIERS_MAP[mod]
            for mod in MODIFIERS_MAP.keys()
            if mod & event.modifiers()
        )

        ev = {
            "event_type": event_type,
            "x": event.pos().x(),
            "y": event.pos().y(),
            "button": button,
            "buttons": buttons,
            "modifiers": modifiers,
        }
        if touches:
            ev.update(
                {
                    "ntouches": 0,
                    "touches": {},  # TODO: Qt touch events
                }
            )

        self.submit_event(ev)

    def mousePressEvent(self, event):  # noqa: N802
        self._mouse_event("pointer_down", event)

    def mouseMoveEvent(self, event):  # noqa: N802
        self._mouse_event("pointer_move", event)

    def mouseReleaseEvent(self, event):  # noqa: N802
        self._mouse_event("pointer_up", event)

    def enterEvent(self, event):  # noqa: N802
        ev = {"event_type": "pointer_enter"}
        self.submit_event(ev)

    def leaveEvent(self, event):  # noqa: N802
        ev = {"event_type": "pointer_leave"}
        self.submit_event(ev)

    def mouseDoubleClickEvent(self, event):  # noqa: N802
        super().mouseDoubleClickEvent(event)
        self._mouse_event("double_click", event, touches=False)

    def wheelEvent(self, event):  # noqa: N802
        # For Qt on macOS Control and Meta are switched
        modifiers = tuple(
            MODIFIERS_MAP[mod]
            for mod in MODIFIERS_MAP.keys()
            if mod & event.modifiers()
        )
        buttons = tuple(
            BUTTON_MAP[button]
            for button in BUTTON_MAP.keys()
            if button & event.buttons()
        )

        ev = {
            "event_type": "wheel",
            "dx": -event.angleDelta().x(),
            "dy": -event.angleDelta().y(),
            "x": event.position().x(),
            "y": event.position().y(),
            "buttons": buttons,
            "modifiers": modifiers,
        }
        self.submit_event(ev)

    def resizeEvent(self, event):  # noqa: N802
        # Logical size
        lsize = float(self.width()), float(self.height())

        # * On Win10 + PyQt5 the ratio is a whole number (175% becomes 2).
        # * On Win10 + PyQt6 the ratio is correct (non-integer).
        ratio = self.devicePixelRatioF()

        # When the ratio is not integer (qt6), we need to somehow make it integer.
        # It turns out that we need to round it (Qt does that itself internally),
        # but also add a small offset. Tested on Win10 with several different OS
        # scales. Would be nice if we could ask Qt for the exact physical size, but
        # we can't. Not an issue on qt5, because ratio is always integer then.
        pwidth = round(lsize[0] * ratio + 0.01)
        pheight = round(lsize[1] * ratio + 0.01)
        self._size_info.set_physical_size(pwidth, pheight, ratio)
        # self.update() / self.request_draw() is implicit

    def closeEvent(self, event):  # noqa: N802
        # Happens e.g. when closing the widget from within an app that dynamically created and closes canvases.
        super().closeEvent(event)
        self._is_closed = True


class QRenderCanvas(WrapperRenderCanvas, QtWidgets.QWidget):
    """A toplevel Qt widget providing a render canvas."""

    # Most of this is proxying stuff to the inner widget.
    # We cannot use a toplevel widget directly, otherwise the window
    # size can be set to subpixel (logical) values, without being able to
    # detect this. See https://github.com/pygfx/wgpu-py/pull/68

    def __init__(self, parent=None, **kwargs):
        # There needs to be an application before any widget is created.
        loop._rc_init()
        # Any kwargs that we want to pass to *this* class, must be explicitly
        # specified in the signature. The rest goes to the subwidget.
        super().__init__(parent)

        self._subwidget = QRenderWidget(self, **kwargs)

        self.setAttribute(WA_DeleteOnClose, True)
        self.setMouseTracking(True)

        # Note: At some point we called `self._subwidget.winId()` here. For some
        # reason this was needed to "activate" the canvas. Otherwise the viz was
        # not shown if no canvas was provided to request_adapter(). Removed
        # later because could not reproduce.

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.setLayout(layout)
        layout.addWidget(self._subwidget)

        self.show()
        self._final_canvas_init()

    # Qt methods

    def update(self):
        self._subwidget.request_draw()
        super().update()

    def closeEvent(self, event):  # noqa: N802
        self._subwidget.closeEvent(event)


# Make available under a name that is the same for all gui backends
RenderWidget = QRenderWidget
RenderCanvas = QRenderCanvas

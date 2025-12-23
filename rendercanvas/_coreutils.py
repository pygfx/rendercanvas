"""
Core utilities that are loaded into the root namespace or used internally.
"""

import os
import re
import sys
import time
import queue
import weakref
import logging
import threading
import ctypes.util
from contextlib import contextmanager
from collections import namedtuple


# %% Constants


IS_WIN = sys.platform.startswith("win")  # Note that IS_WIN is false on Pyodide


# %% Logging


logger = logging.getLogger("rendercanvas")
logger.setLevel(logging.WARNING)


err_hashes = {}  # hash -> [short-message, count, next-time]

_re_wgpu_ob = re.compile(r"`<[a-z|A-Z]+-\([0-9]+, [0-9]+, [a-z|A-Z]+\)>`")


def error_message_hash(message):
    # Remove wgpu object representations, because they contain id's that may change at each draw.
    # E.g. `<CommandBuffer- (12, 4, Metal)>`
    message = _re_wgpu_ob.sub("WGPU_OBJECT", message)
    return hash(message)


@contextmanager
def log_exception(kind):
    """Context manager to log any exceptions, but only log a one-liner
    for subsequent occurrences of the same error to avoid spamming by
    repeating errors in e.g. a draw function or event callback.
    """
    try:
        yield
    except Exception as err:
        # Store exc info for postmortem debugging
        exc_info = list(sys.exc_info())
        exc_info[2] = exc_info[2].tb_next  # type: ignore | skip *this* function
        sys.last_type, sys.last_value, sys.last_traceback = exc_info
        # Show traceback, or a one-line summary
        msg = str(err)
        msgh = error_message_hash(msg)
        if msgh not in err_hashes:
            # Prepare a short variant of the message for later use
            short_msg = kind + ": " + msg.split("\n")[0].strip()
            short_msg = short_msg if len(short_msg) <= 70 else short_msg[:69] + "…"
            err_hashes[msgh] = [short_msg, 1, 0]
            # Provide the exception, so the default logger prints a stacktrace.
            # IDE's can get the exception from the root logger for PM debugging.
            logger.error(kind, exc_info=err)
        else:
            # We've seen this message before, return a one-liner instead.
            short_count_tm = err_hashes[msgh]
            short, count, tm = short_count_tm
            short_count_tm[1] = count = count + 1
            # Show the message now?
            show_message = False
            cur_time = time.perf_counter()
            if count <= 5:
                show_message = True
            else:
                if cur_time > tm:
                    show_message = True
            # Log the messages and schedule when to show it next.
            # Next message is after 1-3 seconds (3 when count reaches 300).
            if show_message:
                short_count_tm[2] = cur_time + min(max(count / 100, 1), 3)
                logger.error(f"{short} ({count})")


# %% Weak bindings


def weakbind(method):
    """Replace a bound method with a callable object that stores the `self` using a weakref."""
    ref = weakref.ref(method.__self__)
    class_func = method.__func__
    del method

    def proxy(*args, **kwargs):
        self = ref()
        if self is not None:
            return class_func(self, *args, **kwargs)

    proxy.__name__ = class_func.__name__
    return proxy


# %% Helper for scheduling call-laters


class CallLaterThread(threading.Thread):
    """An object that can be used to do "call later" from a dedicated thread.

    This is helpful to implement a call-later mechanism on some backends, and
    serves as an alternative timeout mechanism in Windows (to overcome its
    notorious 15.6ms ticks).

    Windows historically uses ticks that go at 64 ticks per second, i.e. 15.625
    ms each. Other platforms are "tickless" and (in theory) have microsecond
    resolution.

    Care is taken to realize precise timing, in the order of 1 ms. Nevertheless,
    on OS's other than Windows, the native timers are more accurate than this
    threaded approach. I suspect that this is related to the GIL; two threads
    cannot run at the same time.
    """

    Item = namedtuple("Item", ["time", "index", "callback", "args"])

    def __init__(self):
        super().__init__()
        self._queue = queue.SimpleQueue()
        self._count = 0
        self.daemon = True  # don't let this thread prevent shutdown
        self.start()

    def call_later_from_thread(self, delay, callback, *args):
        """In delay seconds, call the callback from the scheduling thread."""
        self._count += 1
        item = CallLaterThread.Item(
            time.perf_counter() + float(delay), self._count, callback, args
        )
        self._queue.put(item)

    def run(self):
        perf_counter = time.perf_counter
        Empty = queue.Empty  # noqa: N806
        q = self._queue
        priority = []
        is_win = IS_WIN

        wait_until = None
        timestep = 0.001  # for doing small sleeps
        leeway = timestep / 2  # a little offset so waiting exactly right on average
        leeway += 0.0005  # extra offset to account for GIL etc. (0.5ms seems ok)

        while True:
            # == Wait for input

            if wait_until is None:
                # Nothing to do but wait
                new_item = q.get(True, None)
            else:
                # We wait for the queue with a timeout. But because the timeout is not very precise,
                # we wait shorter, and then go in a loop with some hard sleeps.
                # Windows has 15.6 ms resolution ticks. But also on other OSes,
                # it benefits precision to do the last bit with hard sleeps.
                offset = 0.016 if is_win else timestep
                try:
                    new_item = q.get(True, max(0, wait_until - perf_counter() - offset))
                except Empty:
                    new_item = None
                    while perf_counter() < wait_until:
                        time.sleep(timestep)
                        try:
                            new_item = q.get_nowait()
                            break
                        except Empty:
                            pass

            # Put it in our priority queue
            if new_item is not None:
                priority.append(new_item)
                priority.sort(reverse=True)

            del new_item

            # == Process items until we have to wait

            item = None
            while True:
                # Get item that is up next
                try:
                    item = priority.pop(-1)
                except IndexError:
                    wait_until = None
                    break

                # If it's not yet time for the item, put it back, and go wait
                item_time_threshold = item.time - leeway
                if perf_counter() < item_time_threshold:
                    priority.append(item)
                    wait_until = item_time_threshold
                    break

                # Otherwise, handle the callback
                try:
                    item.callback(*item.args)
                except Exception as err:
                    # This is not an exception from the callback, but from *scheduling* the callback.
                    # So this very likely means that the main loop cannot schedule, e.g. because it was
                    # closed in the mean time. We detect the cases that we know of and warn for others.
                    msg = str(err)
                    if "loop is closed" in msg or "run() has exited" in msg:
                        pass  # asyncio and trio, respectively
                    else:
                        logger.warning(f"Error in CallLaterThread callback: {msg}")

            del item


_call_later_thread = None


def call_later_from_thread(delay: float, callback: object, *args: object):
    """Utility that calls a callback after a specified delay, from a separate thread.

    The caller is responsible for the given callback to be thread-safe.
    There is one global thread that handles all callbacks. This thread is spawned the first time
    that this function is called.

    Note that this function should only be used in environments where threading is available.
    E.g. on Pyodide this will raise ``RuntimeError: can't start new thread``.
    """
    global _call_later_thread
    if _call_later_thread is None:
        _call_later_thread = CallLaterThread()
    return _call_later_thread.call_later_from_thread(delay, callback, *args)


# %% lib support


QT_MODULE_NAMES = ["PySide6", "PyQt6", "PySide2", "PyQt5"]


def select_qt_lib():
    """Select the qt lib to use, used by qt.py"""
    # Check the override. This env var is meant for internal use only.
    # Otherwise check imported libs.

    libname = os.getenv("_RENDERCANVAS_QT_LIB")
    if libname:
        return libname, qt_lib_has_app(libname)
    else:
        return get_imported_qt_lib()


def get_imported_qt_lib():
    """Get the name of the currently imported qt lib.

    Returns (name, has_application). The name is None when no qt lib is currently imported.
    """

    # Get all imported qt libs
    imported_libs = []
    for libname in QT_MODULE_NAMES:
        qtlib = sys.modules.get(libname, None)
        if qtlib is not None:
            imported_libs.append(libname)

    # Get which of these have an application object
    imported_libs_with_app = [
        libname for libname in imported_libs if qt_lib_has_app(libname)
    ]

    # Return findings
    if imported_libs_with_app:
        return imported_libs_with_app[0], True
    elif imported_libs:
        return imported_libs[0], False
    else:
        return None, False


def qt_lib_has_app(libname):
    QtWidgets = sys.modules.get(libname + ".QtWidgets", None)  # noqa: N806
    if QtWidgets:
        app = QtWidgets.QApplication.instance()
        return app is not None


def asyncio_is_running():
    """Get whether there is currently a running asyncio loop."""
    asyncio = sys.modules.get("asyncio", None)
    if asyncio is None:
        return False
    try:
        loop = asyncio.get_running_loop()
    except Exception:
        loop = None
    return loop is not None


# %% Async generators


# Taken from trio._util.py
def name_asyncgen(agen) -> str:
    """Return the fully-qualified name of the async generator function
    that produced the async generator iterator *agen*.
    """
    if not hasattr(agen, "ag_code"):  # pragma: no cover
        return repr(agen)
    try:
        module = agen.ag_frame.f_globals["__name__"]
    except (AttributeError, KeyError):
        module = f"<{agen.ag_code.co_filename}>"
    try:
        qualname = agen.__qualname__
    except AttributeError:
        qualname = agen.ag_code.co_name
    return f"{module}.{qualname}"


def close_agen(agen):
    """Try to sync-close an async generator."""
    closer = agen.aclose()
    try:
        # If the next thing is a yield, this will raise RuntimeError which we allow to propagate
        closer.send(None)
    except StopIteration:
        pass
    else:
        # If the next thing is an await, we get here.
        # Give a nicer error than the default "async generator ignored GeneratorExit"
        agen_name = name_asyncgen(agen)
        logger.warning(
            f"Async generator {agen_name!r} awaited something during finalization, "
            "so we could not clean it up. Wrap it in 'async with aclosing(...):'",
        )


# %% Linux window managers


SYSTEM_IS_WAYLAND = "wayland" in os.getenv("XDG_SESSION_TYPE", "").lower()

if sys.platform.startswith("linux") and SYSTEM_IS_WAYLAND:
    # Force glfw to use X11. Note that this does not work if glfw is already imported.
    if "glfw" not in sys.modules:
        os.environ["PYGLFW_LIBRARY_VARIANT"] = "x11"
    # Force Qt to use X11. Qt is more flexible - it ok if e.g. PySide6 is already imported.
    os.environ["QT_QPA_PLATFORM"] = "xcb"
    # Force wx to use X11, probably.
    os.environ["GDK_BACKEND"] = "x11"


_x11_display = None


def get_alt_x11_display():
    """Get (the pointer to) a process-global x11 display instance."""
    # Ideally we'd get the real display object used by the backend.
    # But this is not always possible. In that case, using an alt display
    # object can be used.
    global _x11_display
    assert sys.platform.startswith("linux")
    if _x11_display is None:
        x11 = ctypes.CDLL(ctypes.util.find_library("X11"))
        x11.XOpenDisplay.restype = ctypes.c_void_p
        _x11_display = x11.XOpenDisplay(None)
    return _x11_display


_wayland_display = None


def get_alt_wayland_display():
    """Get (the pointer to) a process-global Wayland display instance."""
    # Ideally we'd get the real display object used by the backend.
    # This creates a global object, similar to what we do for X11.
    # Unfortunately, this segfaults, so it looks like the real display object
    # is needed? Leaving this here for reference.
    global _wayland_display
    assert sys.platform.startswith("linux")
    if _wayland_display is None:
        wl = ctypes.CDLL(ctypes.util.find_library("wayland-client"))
        wl.wl_display_connect.restype = ctypes.c_void_p
        _wayland_display = wl.wl_display_connect(None)
    return _wayland_display

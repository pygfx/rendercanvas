import os
import re
import sys
import logging
import subprocess
from io import StringIO

import wgpu


class LogCaptureHandler(logging.StreamHandler):
    _ANSI_ESCAPE_SEQ = re.compile(r"\x1b\[[\d;]+m")

    def __init__(self):
        super().__init__(StringIO())
        self.records = []

    def emit(self, record):
        record.msg = self._ANSI_ESCAPE_SEQ.sub("", record.msg)
        self.records.append(record)
        super().emit(record)

    def reset(self):
        self.records = []
        self.stream = StringIO()

    @property
    def text(self):
        f = logging.Formatter()
        return "\n".join(f.format(r) for r in self.records)


def run_tests(scope):
    """Run all test functions in the given scope."""
    caplog = LogCaptureHandler()
    for func in list(scope.values()):
        if callable(func) and func.__name__.startswith("test_"):
            params = [
                mark.args
                for mark in getattr(func, "pytestmark", [])
                if mark.name == "parametrize"
            ]
            nargs = func.__code__.co_argcount
            argnames = [func.__code__.co_varnames[i] for i in range(nargs)]
            if not argnames:
                print(f"Running {func.__name__} ...")
                func()
            elif nargs == 1 and len(params) == 1:
                for arg in params[0][1]:
                    print(f"Running {func.__name__} with {arg}...")
                    func(arg)
            elif argnames == ["caplog"]:
                print(f"Running {func.__name__} ...")
                logging.root.addHandler(caplog)
                caplog.reset()
                func(caplog)
                logging.root.removeHandler(caplog)
            else:
                print(f"SKIPPING {func.__name__} because it needs args")
    print("Done")


def get_default_adapter_summary():
    """Get description of adapter, or None when no adapter is available."""
    try:
        adapter = wgpu.gpu.request_adapter_sync()
    except RuntimeError:
        return None  # lib not available, or no adapter on this system
    return adapter.summary


def _determine_can_use_glfw():
    code = "import glfw;exit(0) if glfw.init() else exit(1)"
    try:
        subprocess.check_output([sys.executable, "-c", code])
    except Exception:
        return False
    else:
        return True


adapter_summary = get_default_adapter_summary()
can_use_wgpu_lib = bool(adapter_summary)

can_use_glfw = _determine_can_use_glfw()
is_ci = bool(os.getenv("CI"))
is_pypy = sys.implementation.name == "pypy"

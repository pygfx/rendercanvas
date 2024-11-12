# ruff: noqa: E402, F403

import os

ref_libname = "PySide6"
os.environ["_RENDERCANVAS_QT_LIB"] = ref_libname

from .qt import check_qt_libname
from .qt import *

check_qt_libname(ref_libname)

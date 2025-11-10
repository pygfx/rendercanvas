"""
A context provides an API to provide a rendered image, and implements a
mechanism to present that image for display. The concept of a context is heavily
inspired by the canvas and its contexts in the browser.

In ``rendercanvas``, there are two types of contexts: the *bitmap* context
exposes an API that takes image bitmaps in RAM, and the *wgpu* context exposes
an API that provides image textures on the GPU to render to.

The presentation of the rendered image is handled by a sub-system, e.g. display
directly to screen, pass as bitmap to a GUI toolkit, send bitmap to a remote
client, etc. Each such subsystem is handled by a dedicated subclasses of
``BitmapContext`` and ``WgpuContext``. Users only need to be aware of the base
classes.
"""

from .basecontext import *  # noqa: F403
from .bitmapcontext import *  # noqa: F403
from .wgpucontext import *  # noqa: F403

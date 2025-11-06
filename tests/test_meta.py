"""
Test some meta stuff.
"""

import sys
import subprocess
from testutils import run_tests

import rendercanvas
import pytest


CODE = """
import sys
ignore_names = set(sys.modules)
ignore_names |= set(sys.stdlib_module_names)
ignore_names.discard("asyncio")
import MODULE_NAME
module_names = [n for n in sys.modules if n.split(".")[0] not in ignore_names]
module_names = [n for n in module_names if not n.startswith("_")]
print(', '.join(module_names))
"""


def get_loaded_modules(module_name, depth=1):
    """Get what deps are loaded for a given module.

    Import the given module in a subprocess and return a set of
    module names that were imported as a result.

    The given depth indicates the module level (i.e. depth=1 will only
    yield 'X.Y' but not 'X.Y.Z').
    """

    code = (
        "; ".join(CODE.strip().splitlines()).strip().replace("MODULE_NAME", module_name)
    )

    p = subprocess.run([sys.executable, "-c", code], capture_output=True)
    assert not p.stderr, p.stderr.decode()
    loaded_modules = set(name.strip() for name in p.stdout.decode().split(","))

    # Filter by depth
    filtered_modules = set()
    if not depth:
        filtered_modules = set(loaded_modules)
    else:
        for m in loaded_modules:
            parts = m.split(".")
            m = ".".join(parts[:depth])
            filtered_modules.add(m)

    return filtered_modules


# %%


def test_version_is_there():
    assert rendercanvas.__version__
    assert rendercanvas.version_info


def test_namespace():
    # Yes
    assert "BaseRenderCanvas" in dir(rendercanvas)
    assert "BaseLoop" in dir(rendercanvas)
    assert "EventType" in dir(rendercanvas)

    # No
    assert "WrapperRenderCanvas" not in dir(rendercanvas)
    assert "BaseCanvasGroup" not in dir(rendercanvas)
    assert "Scheduler" not in dir(rendercanvas)


@pytest.mark.skipif(sys.version_info < (3, 10), reason="Need py310+")
def test_deps_plain_import():
    modules = get_loaded_modules("rendercanvas", 1)
    assert modules == {"rendercanvas", "sniffio"}
    # Note, no wgpu


@pytest.mark.skipif(sys.version_info < (3, 10), reason="Need py310+")
def test_deps_asyncio():
    # I like it that asyncio is only imported when actually being used.
    # Since its the default loop for some backends, it must lazy-import.
    # We can do this safely because asyncio is std.
    modules = get_loaded_modules("rendercanvas.asyncio", 1)
    assert "asyncio" not in modules

    # Check that we can indeed see an asyncio import (asyncio being std)
    modules = get_loaded_modules("sys, asyncio", 1)
    assert "asyncio" in modules


@pytest.mark.skipif(sys.version_info < (3, 10), reason="Need py310+")
def test_deps_trio():
    # For trio, I like that if the trio module is loaded, trio is imported, fail early.
    modules = get_loaded_modules("rendercanvas.trio", 1)
    assert "trio" in modules


if __name__ == "__main__":
    run_tests(globals())

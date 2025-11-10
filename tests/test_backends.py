"""
Test basic validity of the backends.

* Test that each backend module has the expected names in its namespace.
* Test that the classes (canvas, loop) implement the correct _rx_xx methods.
"""

import os
import ast

import rendercanvas
from testutils import run_tests


# %% Helper


def get_ref_rc_methods(what):
    """Get the reference rc-methods from the respective Python objects."""
    cls = getattr(rendercanvas, "Base" + what)
    rc_methods = set()
    for name in cls.__dict__:
        if name.startswith("_rc_"):
            rc_methods.add(name)
    return rc_methods


class Module:
    """Represent a module ast."""

    def __init__(self, name):
        self.name = name

        self.filename = os.path.abspath(
            os.path.join(rendercanvas.__file__, "..", self.name + ".py")
        )
        with open(self.filename, "rb") as f:
            self.source = f.read().decode()

        self.names = self.get_namespace()

    def get_namespace(self):
        module = ast.parse(self.source)

        names = {}
        for statement in module.body:
            if isinstance(statement, ast.ClassDef):
                names[statement.name] = statement
            elif isinstance(statement, ast.Assign):
                if isinstance(statement.targets[0], ast.Name):
                    name = statement.targets[0].id
                    if (
                        isinstance(statement.value, ast.Name)
                        and statement.value.id in names
                    ):
                        names[name] = names[statement.value.id]
                    else:
                        names[name] = statement
        return names

    def get_bases(self, class_def):
        bases = []
        for base in class_def.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(f"{base.value.id}.{base.attr}")
            else:
                bases.append("unknown")
        return bases

    def get_rc_methods(self, class_def):
        rc_methods = set()
        for statement in class_def.body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if statement.name.startswith("_rc_"):
                    rc_methods.add(statement.name)
            # We also have a few attrs, we just use the method-logic here
            if isinstance(statement, ast.Assign):
                if isinstance(statement.targets[0], ast.Name):
                    name = statement.targets[0].id
                    if name.startswith("_rc_"):
                        rc_methods.add(name)
        return rc_methods

    def check_rc_methods(self, rc_methods, ref_rc_methods):
        too_little = ref_rc_methods - rc_methods
        too_many = rc_methods - ref_rc_methods
        assert not too_little, too_little
        assert not too_many, too_many
        print("        all _rc_  methods ok")

    def get_canvas_class(self):
        # Check that base names are there
        assert "RenderCanvas" in self.names

        # Check canvas

        canvas_class = self.names["RenderCanvas"]
        canvas_bases = self.get_bases(canvas_class)
        print(f"    {canvas_class.name}: {', '.join(canvas_bases)}")

        if "WrapperRenderCanvas" in canvas_bases:
            assert "RenderWidget" in self.names
            canvas_class = self.names["RenderWidget"]
            canvas_bases = self.get_bases(canvas_class)
            print(f"    {canvas_class.name}: {', '.join(canvas_bases)}")

        return canvas_class

    def check_canvas(self, canvas_class):
        rc_methods = self.get_rc_methods(canvas_class)
        self.check_rc_methods(rc_methods, canvas_rc_methods)

    def get_loop_class(self):
        assert "loop" in self.names

        loop_statement = self.names["loop"]
        assert isinstance(loop_statement, ast.Assign)
        loop_class = self.names[loop_statement.value.func.id]
        loop_bases = self.get_bases(loop_class)
        print(f"    loop -> {loop_class.name}: {', '.join(loop_bases)}")
        return loop_class

    def check_loop(self, loop_class):
        rc_methods = self.get_rc_methods(loop_class)
        self.check_rc_methods(rc_methods, loop_rc_methods)


canvas_rc_methods = get_ref_rc_methods("RenderCanvas")
loop_rc_methods = get_ref_rc_methods("Loop")


# %% Meta tests


def test_meta():
    # Test that all backends are represented in the test.
    all_test_names = set(name for name in globals() if name.startswith("test_"))

    dirname = os.path.abspath(os.path.join(rendercanvas.__file__, ".."))
    all_modules = set(name for name in os.listdir(dirname) if name.endswith(".py"))

    for fname in all_modules:
        if fname.startswith("_"):
            continue
        module_name = fname.split(".")[0]
        test_func_name = f"test_{module_name}_module"
        assert test_func_name in all_test_names, (
            f"Test missing for {module_name} module"
        )


def test_ref_rc_methods():
    # Test basic validity of the reference rc method lists
    print("    RenderCanvas")
    for x in canvas_rc_methods:
        print(f"        {x}")
    print("    Loop")
    for x in loop_rc_methods:
        print(f"        {x}")

    assert len(canvas_rc_methods) >= 10
    assert len(loop_rc_methods) >= 3


# %% Test modules that are not really backends


def test_base_module():
    # This tests the base classes. This is basically an extra check
    # that the method names extracted via the ast match the reference names.
    # If this fails on the name matching, something bad has happened.

    m = Module("base")

    canvas_class = m.names["BaseRenderCanvas"]
    m.check_canvas(canvas_class)

    m = Module("_loop")

    loop_class = m.names["BaseLoop"]
    m.check_loop(loop_class)


def test_auto_module():
    m = Module("auto")
    assert "RenderCanvas" in m.names
    assert "loop" in m.names


# %% Test modules that only provide a loop


def test_raw_module():
    m = Module("raw")

    assert "loop" in m.names
    assert m.names["loop"]
    loop_class = m.names["RawLoop"]
    m.check_loop(loop_class)
    assert loop_class.name == "RawLoop"


def test_asyncio_module():
    m = Module("asyncio")

    assert "loop" in m.names
    assert m.names["loop"]
    loop_class = m.names["AsyncioLoop"]
    m.check_loop(loop_class)
    assert loop_class.name == "AsyncioLoop"


def test_trio_module():
    m = Module("trio")

    assert "loop" in m.names
    assert m.names["loop"]
    loop_class = m.names["TrioLoop"]
    m.check_loop(loop_class)
    assert loop_class.name == "TrioLoop"


# %% Test the backend modules


def test_stub_module():
    m = Module("stub")

    canvas_class = m.get_canvas_class()
    m.check_canvas(canvas_class)
    assert canvas_class.name == "StubRenderCanvas"

    loop_class = m.get_loop_class()
    m.check_loop(loop_class)
    assert loop_class.name == "StubLoop"


def test_glfw_module():
    m = Module("glfw")

    canvas_class = m.get_canvas_class()
    m.check_canvas(canvas_class)
    assert canvas_class.name == "GlfwRenderCanvas"

    # Loop is imported from asyncio
    assert m.names["loop"]


def test_pyodide_module():
    m = Module("pyodide")

    canvas_class = m.get_canvas_class()
    m.check_canvas(canvas_class)
    assert canvas_class.name == "PyodideRenderCanvas"


def test_jupyter_module():
    m = Module("jupyter")

    canvas_class = m.get_canvas_class()
    m.check_canvas(canvas_class)
    assert canvas_class.name == "JupyterRenderCanvas"


def test_offscreen_module():
    m = Module("offscreen")

    canvas_class = m.get_canvas_class()
    m.check_canvas(canvas_class)
    assert canvas_class.name == "OffscreenRenderCanvas"


def test_qt_module():
    m = Module("qt")

    canvas_class = m.get_canvas_class()
    m.check_canvas(canvas_class)
    assert canvas_class.name == "QRenderWidget"

    loop_class = m.get_loop_class()
    m.check_loop(loop_class)
    assert loop_class.name == "QtLoop"


def test_pyside6_module():
    m = Module("pyside6")
    assert "from .qt import *" in m.source


def test_pyside2_module():
    m = Module("pyside2")
    assert "from .qt import *" in m.source


def test_pyqt6_module():
    m = Module("pyqt6")
    assert "from .qt import *" in m.source


def test_pyqt5_module():
    m = Module("pyqt5")
    assert "from .qt import *" in m.source


def test_wx_module():
    m = Module("wx")

    canvas_class = m.get_canvas_class()
    m.check_canvas(canvas_class)
    assert canvas_class.name == "WxRenderWidget"

    loop_class = m.get_loop_class()
    m.check_loop(loop_class)
    assert loop_class.name == "WxLoop"


if __name__ == "__main__":
    run_tests(globals())

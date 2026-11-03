"""
The _rc_xx methods are documented in the base classes.
But when copying stub.py to create a new backend, its convenient to have the docs there too.
This test checks that stub.py is up-to-date.
To update, just run the test and commit the changes.
"""

from pathlib import Path

from rendercanvas.base import (
    BaseCanvasGroup,
    BaseLoop,
    BaseRenderCanvas,
    WrapperRenderCanvas,
)

STUB_BACKEND_FILE = Path(__file__).absolute().parents[1] / "rendercanvas" / "stub.py"

BASE_CLASSES = {
    cls.__name__: cls
    for cls in (BaseCanvasGroup, BaseLoop, BaseRenderCanvas, WrapperRenderCanvas)
}


def test_that_stub_backend_comments_are_up_to_date():
    wrote = copy_stub_backend_comments()
    assert not wrote, (
        "The comments in stub.py are not up-to-date, run test_stubs.py and commit the resulting changes."
    )


def copy_stub_backend_comments() -> bool:
    code1 = STUB_BACKEND_FILE.read_text(encoding="utf-8")
    code2 = _copy_docstrings_as_comments(code1)

    if code1 != code2:
        STUB_BACKEND_FILE.write_text(code2, encoding="utf-8")
        return True
    else:
        return False


def _copy_docstrings_as_comments(code: str) -> str:
    lines = code.splitlines(keepends=True)
    new_lines = []
    current_base_class = None

    i = -1
    while i < len(lines) - 1:
        i += 1
        line = lines[i]
        new_lines.append(line)
        if line.startswith("class "):
            class_name = line.split("(")[1].split(")")[0]
            current_base_class = BASE_CLASSES.get(class_name, None)
        if line.lstrip().startswith("def _rc_"):
            method_name = line.strip().split(" ")[1].split("(")[0]
            method = getattr(current_base_class, method_name, None)
            le = line[len(line.rstrip()) :].strip(" ")
            if method:
                for docline in method.__doc__.splitlines():
                    new_lines.append(f"        # {docline}".rstrip() + le)
            i += 1
            while lines[i].lstrip().startswith("#"):
                i += 1
            i -= 1

    return "".join(new_lines)


if __name__ == "__main__":
    wrote = copy_stub_backend_comments()
    if wrote:
        print("Updated stub.py comments")
    else:
        print("stub.py is up to date")

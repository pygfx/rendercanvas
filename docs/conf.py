# Configuration file for the Sphinx documentation builder.
#
# This file only contains a selection of the most common options. For a full
# list see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Path setup --------------------------------------------------------------

# If extensions (or modules to document with autodoc) are in another directory,
# add these directories to sys.path here. If the directory is relative to the
# documentation root, use os.path.abspath to make it absolute, like shown here.

import os
import sys
import shutil

import flit

ROOT_DIR = os.path.abspath(os.path.join(__file__, "..", ".."))
sys.path.insert(0, ROOT_DIR)

os.environ["RENDERCANVAS_FORCE_OFFSCREEN"] = "true"


# Load wgpu so autodoc can query docstrings
import rendercanvas  # noqa: E402
import rendercanvas.stub  # noqa: E402 - we use the stub backend to generate docs
import rendercanvas._context  # noqa: E402 - we use the ContextInterface to generate docs
import rendercanvas.utils.bitmappresentadapter  # noqa: E402

# -- Project information -----------------------------------------------------

project = "rendercanvas"
copyright = "2020-2025, Almar Klein, Korijn van Golen"
author = "Almar Klein, Korijn van Golen"
release = rendercanvas.__version__


# -- General configuration ---------------------------------------------------

# Add any Sphinx extension module names here, as strings. They can be
# extensions coming with Sphinx (named 'sphinx.ext.*') or your custom
# ones.
extensions = [
    "sphinx_rtd_theme",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx_gallery.gen_gallery",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "numpy": ("https://numpy.org/doc/stable", None),
    "wgpu": ("https://wgpu-py.readthedocs.io/en/stable", None),
}

# Add any paths that contain templates here, relative to this directory.
templates_path = ["_templates"]

# List of patterns, relative to source directory, that match files and
# directories to ignore when looking for source files.
# This pattern also affects html_static_path and html_extra_path.
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

master_doc = "index"


# -- Build wheel so Pyodide examples can use exactly this version of rendercanvas -----------------------------------------------------

short_version = ".".join(str(i) for i in rendercanvas.version_info[:3])
wheel_name = f"rendercanvas-{short_version}-py3-none-any.whl"

# Build the wheel
toml_filename = os.path.join(ROOT_DIR, "pyproject.toml")
flit.main(["-f", toml_filename, "build", "--no-use-vcs", "--format", "wheel"])
wheel_filename = os.path.join(ROOT_DIR, "dist", wheel_name)
assert os.path.isfile(wheel_filename), f"{wheel_name} does not exist"

# Copy into static
print("Copy wheel to static dir")
shutil.copy(
    wheel_filename,
    os.path.join(ROOT_DIR, "docs", "static", wheel_name),
)


# -- Sphinx Gallery -----------------------------------------------------

iframe_placeholde_rst = """
.. only:: html

    Interactive example
    ===================

    This uses Pyodide. If this does not work, your browser may not have sufficient support for wasm/pyodide/wgpu (check your browser dev console).

    .. raw:: html

        <iframe src="pyodide.html#example.py"></iframe>
"""

python_files = {}


def add_pyodide_to_examples(app):
    if app.builder.name != "html":
        return

    gallery_dir = os.path.join(ROOT_DIR, "docs", "gallery")

    for fname in os.listdir(gallery_dir):
        filename = os.path.join(gallery_dir, fname)
        if not fname.endswith(".py"):
            continue
        with open(filename, "rb") as f:
            py = f.read().decode()
        if fname in ["drag.py", "noise.py", "snake.py"]:
            # todo: later we detect by using a special comment in the py file
            print("Adding Pyodide example to", fname)
            fname_rst = fname.replace(".py", ".rst")
            # Update rst file
            rst = iframe_placeholde_rst.replace("example.py", fname)
            with open(os.path.join(gallery_dir, fname_rst), "ab") as f:
                f.write(rst.encode())
            python_files[fname] = py


def add_files_to_run_pyodide_examples(app, exception):
    if app.builder.name != "html":
        return

    gallery_build_dir = os.path.join(app.outdir, "gallery")

    # Write html file that can load pyodide examples
    with open(
        os.path.join(ROOT_DIR, "docs", "static", "_pyodide_iframe.html"), "rb"
    ) as f:
        html = f.read().decode()
    html = html.replace('"rendercanvas"', f'"../_static/{wheel_name}"')
    with open(os.path.join(gallery_build_dir, "pyodide.html"), "wb") as f:
        f.write(html.encode())

    # Write the python files
    for fname, py in python_files.items():
        print("Writing", fname)
        with open(os.path.join(gallery_build_dir, fname), "wb") as f:
            f.write(py.encode())


# Suppress "cannot cache unpickable configuration value" for sphinx_gallery_conf
# See https://github.com/sphinx-doc/sphinx/issues/12300
suppress_warnings = ["config.cache"]

# The gallery conf. See https://sphinx-gallery.github.io/stable/configuration.html
sphinx_gallery_conf = {
    "gallery_dirs": "gallery",
    "backreferences_dir": "gallery/backreferences",
    "doc_module": ("rendercanvas",),
    # "image_scrapers": (),
    "remove_config_comments": True,
    "examples_dirs": "../examples/",
    "ignore_pattern": r"serve_browser_examples\.py",
}

# -- Options for HTML output -------------------------------------------------

# The theme to use for HTML and HTML Help pages.  See the documentation for
# a list of builtin themes.

html_theme = "sphinx_rtd_theme"

# Add any paths that contain custom static files (such as style sheets) here,
# relative to this directory. They are copied after the builtin static files,
# so a file named "default.css" will overwrite the builtin "default.css".
html_static_path = ["static"]
html_css_files = ["custom.css"]


def setup(app):
    app.connect("builder-inited", add_pyodide_to_examples)
    app.connect("build-finished", add_files_to_run_pyodide_examples)

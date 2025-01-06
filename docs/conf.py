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


ROOT_DIR = os.path.abspath(os.path.join(__file__, "..", ".."))
sys.path.insert(0, ROOT_DIR)

os.environ["RENDERCANVAS_FORCE_OFFSCREEN"] = "true"


# Load wglibu so autodoc can query docstrings
import rendercanvas  # noqa: E402
import rendercanvas.stub  # noqa: E402 - we use the stub backend to generate doccs
import rendercanvas._context  # noqa: E402 - we use the ContexInterface to generate doccs
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
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.intersphinx",
    "sphinx_rtd_theme",
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


# -- Sphinx Gallery -----------------------------------------------------

# Suppress "cannot cache unpickable configuration value" for sphinx_gallery_conf
# See https://github.com/sphinx-doc/sphinx/issues/12300
suppress_warnings = ["config.cache"]

# The gallery conf. See https://sphinx-gallery.github.io/stable/configuration.html
sphinx_gallery_conf = {
    "gallery_dirs": "gallery",
    "backreferences_dir": "gallery/backreferences",
    "doc_module": ("rendercanvas",),
    # "image_scrapers": (),,
    "remove_config_comments": True,
    "examples_dirs": "../examples/",
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

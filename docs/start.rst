Installation
============

Install with pip
----------------

You can install ``rendercanvas`` via pip.
Python 3.9 or higher is required. Pypy is supported.

.. code-block:: bash

    pip install rendercanvas


Since most users will want to render something to screen, we recommend installing GLFW as well:

.. code-block:: bash

    pip install rendercanvas glfw


GUI libraries
-------------

Multiple GUI backends are supported, see :doc:`the GUI API <gui>` for details:

* `glfw <https://github.com/FlorianRhiem/pyGLFW>`_: a lightweight GUI for the desktop
* `jupyter_rfb <https://jupyter-rfb.readthedocs.io>`_: only needed if you plan on using Jupyter
* qt (PySide6, PyQt6, PySide2, PyQt5)
* wx

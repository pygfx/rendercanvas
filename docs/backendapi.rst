How backends work
=================

This page documents what's needed to implement a backend for ``rendercanvas``. The purpose of this documentation is
to help maintain current and new backends. Making this internal API clear helps understanding how the backend-system works.
Also see https://github.com/pygfx/rendercanvas/blob/main/rendercanvas/stub.py.

.. note::

    It is possible to create a custom backend (outside of the ``rendercanvas`` package). However, we consider this API an internal detail that may change
    with each version without warning.


.. autoclass:: rendercanvas.stub.StubCanvasGroup
    :members:
    :private-members:
    :member-order: bysource


.. autoclass:: rendercanvas.stub.StubRenderCanvas
    :members:
    :private-members:
    :member-order: bysource


.. autoclass:: rendercanvas.base.WrapperRenderCanvas


.. autoclass:: rendercanvas.stub.StubLoop
    :members:
    :private-members:
    :member-order: bysource

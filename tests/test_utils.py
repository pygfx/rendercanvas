import os
import gc
import time

import rendercanvas
from testutils import run_tests, is_pypy


def test_weakbind():
    weakbind = rendercanvas._coreutils.weakbind

    xx = []

    class Foo:
        def bar(self):
            xx.append(1)

    f1 = Foo()
    f2 = Foo()

    b1 = f1.bar
    b2 = weakbind(f2.bar)

    assert len(xx) == 0
    b1()
    assert len(xx) == 1
    b2()
    assert len(xx) == 2

    del f1
    del f2

    if is_pypy:
        gc.collect()

    assert len(xx) == 2
    b1()
    assert len(xx) == 3  # f1 still exists
    b2()
    assert len(xx) == 3  # f2 is gone!


def test_call_later_thread():
    leeway = 0.05 if os.getenv("CI") else 0

    t = rendercanvas._coreutils.CallLaterThread()

    results = []

    # Call now
    t.call_later_from_thread(0, results.append, 5)

    time.sleep(0.01)
    assert results == [5]

    # Call later
    t.call_later_from_thread(0.5, results.append, 5)

    time.sleep(0.1)
    assert results == [5]

    time.sleep(0.5)
    assert results == [5, 5]

    # Call multiple at same time
    results.clear()
    t.call_later_from_thread(0, results.append, 1)
    t.call_later_from_thread(0, results.append, 2)
    t.call_later_from_thread(0, results.append, 3)
    t.call_later_from_thread(0.1, results.append, 4)
    t.call_later_from_thread(0.1, results.append, 5)
    t.call_later_from_thread(0.1, results.append, 6)

    time.sleep(0.11 + leeway)
    assert results == [1, 2, 3, 4, 5, 6]

    # Out of order

    def set(x):
        results.append((x, time.perf_counter()))

    results.clear()
    t.call_later_from_thread(0.9, set, 1)
    t.call_later_from_thread(0.8, set, 2)
    t.call_later_from_thread(0.41, set, 3)
    t.call_later_from_thread(0.40, set, 4)
    t.call_later_from_thread(0.11, set, 5)
    t.call_later_from_thread(0.10, set, 6)

    now = time.perf_counter()
    time.sleep(1.1 + leeway)

    indices = [r[0] for r in results]
    times = [r[1] - now for r in results]

    assert indices == [6, 5, 4, 3, 2, 1]
    assert times[1] - times[0] < 0.04 + leeway
    assert times[2] - times[3] < 0.04 + leeway


if __name__ == "__main__":
    run_tests(globals())

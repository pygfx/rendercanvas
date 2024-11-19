"""
Some tests for the base loop and asyncio loop.
"""

import threading

from rendercanvas.asyncio import AsyncioLoop
from testutils import run_tests


def run_loop_briefly():
    loop = AsyncioLoop()
    loop.call_later(0.1, print, "hi from loop!")
    loop.call_later(0.2, loop.stop)
    loop.run()


def test_loop_main():
    run_loop_briefly()


def test_loop_threaded():
    t = threading.Thread(target=run_loop_briefly)
    t.start()
    t.join()


if __name__ == "__main__":
    run_tests(globals())

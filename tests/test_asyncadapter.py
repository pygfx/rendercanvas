"""
Test the functionality of the asyncadapter with the bare minimum boilderplate.
Using asyncio to drive the loop with call_later; the actual async
happens via asyncadapter.Task.
"""

import time

import asyncio
from rendercanvas.utils import asyncadapter


def test_sleep():
    times = []

    async def coro():
        times.append(time.perf_counter())
        await asyncadapter.sleep(0.05)
        times.append(time.perf_counter())
        await asyncadapter.sleep(0.1)
        times.append(time.perf_counter())

    task = asyncadapter.Task(loop.call_later, coro(), "test")
    loop = asyncio.new_event_loop()


    loop.call_later(0.25, loop.stop)
    loop.run_forever()

    sleep_time1 = times[1] - times[0]
    sleep_time2 = times[2] - times[1]
    assert 0.04 < sleep_time1 < 0.6
    assert 0.09 < sleep_time2 < 0.12


def test_event():
    event1 = asyncadapter.Event()
    event2 = asyncadapter.Event()

    times = []

    async def coro1():
        await asyncadapter.sleep(0.05)
        event1.set()
        await asyncadapter.sleep(0.1)
        event2.set()

    async def coro2():
        times.append(time.perf_counter())
        await event1.wait()
        times.append(time.perf_counter())
        await event2.wait()
        times.append(time.perf_counter())

    loop = asyncio.new_event_loop()

    task1 = asyncadapter.Task(loop.call_later, coro1(), "test")
    task2 = asyncadapter.Task(loop.call_later, coro2(), "test")

    loop.call_later(0.25, loop.stop)
    loop.run_forever()

    sleep_time1 = times[1] - times[0]
    sleep_time2 = times[2] - times[1]
    assert 0.04 < sleep_time1 < 0.6
    assert 0.09 < sleep_time2 < 0.12


if __name__ == "__main__":
    test_sleep()
    test_event()

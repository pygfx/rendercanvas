"""
A micro async framework that only support ``sleep()`` and ``Event``. Behaves well with ``sniffio``.
Intended for internal use, but is fully standalone.
"""

import logging

from sniffio import thread_local as sniffio_thread_local


logger = logging.getLogger("asyncadapter")


class Sleeper:
    def __init__(self, delay):
        self.delay = delay

    def __await__(self):
        # This most be a generator, but it is unspecified what must be yielded; this
        # is framework-specific. So we use our own little protocol.
        yield {"wait_method": "sleep", "delay": self.delay}


async def sleep(delay):
    """Async sleep for delay seconds."""
    await Sleeper(delay)


class Event:
    """Event object similar to asyncio.Event and Trio.Event."""

    def __init__(self):
        self._is_set = False
        self._tasks = []

    async def wait(self):
        if self._is_set:
            return
        else:
            return self  # triggers __await__

    def __await__(self):
        return {"wait_method": "event", "event": self}

    def _add_task(self, task):
        self._tasks.append(task)

    def set(self):
        self._is_set = True
        for task in self._tasks:
            task.call_step_later(0)
        self._tasks = []


class CancelledError(BaseException):
    """Exception raised when a task is cancelled."""

    pass


class Task:
    """Representation of task, exectuting a co-routine."""

    def __init__(self, call_later_func, coro, name):
        self._call_later = call_later_func
        self._done_callbacks = []
        self.coro = coro
        self.name = name
        self.cancelled = False
        self.call_step_later(0)

    def add_done_callback(self, callback):
        self._done_callbacks.append(callback)

    def _close(self):
        self.loop = None
        self.coro = None
        for callback in self._done_callbacks:
            try:
                callback(self)
            except Exception:
                pass
        self._done_callbacks.clear()

    def call_step_later(self, delay):
        self._call_later(delay, self.step)

    def cancel(self):
        self.cancelled = True

    def step(self):
        if self.coro is None:
            return

        result = None
        stop = False

        old_name, sniffio_thread_local.name = sniffio_thread_local.name, __name__
        try:
            if self.cancelled:
                stop = True
                self.coro.throw(CancelledError())  # falls through if not caught
                self.coro.close()  # raises GeneratorExit
            else:
                result = self.coro.send(None)
        except CancelledError:
            stop = True
        except StopIteration:
            stop = True
        except Exception as err:
            # This should not happen, because the loop catches and logs all errors. But just in case.
            logger.error(f"Error in task: {err}")
            stop = True
        finally:
            sniffio_thread_local.name = old_name

        # Clean up to help gc
        if stop:
            return self._close()

        error = None
        if not (isinstance(result, dict) and result.get("wait_method", None)):
            error = f"Incompatible awaitable result {result!r}. Maybe you used asyncio or trio (this does not run on either)?"
        else:
            wait_method = result["wait_method"]
            if wait_method == "sleep":
                self.call_step_later(result["delay"])
            elif wait_method == "event":
                result["event"]._add_task(self)
            else:
                error = f"Unknown wait_method {wait_method!r}."

        if error:
            logger.error(
                f"Incompatible awaitable result {result!r}. Maybe you used asyncio or trio (this does not run on either)?"
            )
            self.cancel()
            self.call_step_later(0)

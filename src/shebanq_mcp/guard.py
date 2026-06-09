"""Concurrency- and timeout-bounded execution of Emdros queries.

A public single-container deploy must survive a valid-but-expensive MQL query.
Each query runs in a worker process so a synchronous Emdros C call can be
hard-killed on timeout. On overrun we send SIGTERM, wait a short grace, then
SIGKILL — escalation matters because a process pinned in C may ignore SIGTERM.
A semaphore caps how many run at once (bounding memory).
"""
import multiprocessing
import queue as _queue
import threading

from .runner import RunResult, run_query

_TERM_GRACE_SECONDS = 2.0


class QueryTimeout(Exception):
    """Raised when a query exceeds the configured wall-clock budget."""


def _default_target(mql, db_path, features, q):
    """Run a query in the worker process; ship the result over the queue."""
    try:
        res = run_query(mql, db_path, features)
        q.put(("ok", res))
    except Exception as exc:  # noqa: BLE001 - report any failure to the parent
        q.put(("err", repr(exc)))


class QueryGuard:
    """Runs each query in a worker process with a concurrency cap + hard timeout."""

    def __init__(self, db_path, max_concurrent=4, timeout_seconds=15,
                 target=_default_target):
        self._db_path = db_path
        self._timeout = timeout_seconds
        self._target = target
        self._sem = threading.Semaphore(max_concurrent)
        self._ctx = multiprocessing.get_context("spawn")

    def _kill(self, proc):
        proc.terminate()                       # SIGTERM
        proc.join(timeout=_TERM_GRACE_SECONDS)
        if proc.is_alive():
            proc.kill()                        # SIGKILL
            proc.join()

    def run(self, mql, features=None) -> RunResult:
        with self._sem:
            q = self._ctx.Queue()
            proc = self._ctx.Process(
                target=self._target,
                args=(mql, self._db_path, features or [], q),
            )
            proc.start()
            try:
                status, payload = q.get(timeout=self._timeout)
            except _queue.Empty:
                self._kill(proc)
                raise QueryTimeout(
                    f"query exceeded {self._timeout}s and was terminated"
                )
            proc.join()
            if status == "err":
                raise RuntimeError(payload)
            return payload

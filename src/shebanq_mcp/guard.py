"""Concurrency- and timeout-bounded execution of Emdros queries.

A public single-container deploy must survive a valid-but-expensive MQL query.
Each query runs in a worker process so a synchronous Emdros C call can be
hard-killed on timeout. On overrun we send SIGTERM, wait a short grace, then
SIGKILL — escalation matters because a process pinned in C may ignore SIGTERM.
A semaphore caps how many run at once (bounding memory). A worker that dies
without reporting is surfaced promptly as WorkerCrashed, and when the cap is
saturated past a bounded wait the caller gets ServerBusy instead of queueing
forever.
"""
import multiprocessing
import os
import queue as _queue
import threading
import time

from .runner import RunResult, run_query

_TERM_GRACE_SECONDS = 2.0


class QueryTimeout(Exception):
    """Raised when a query exceeds the configured wall-clock budget."""


class WorkerCrashed(Exception):
    """Raised when the worker process dies without reporting a result."""


class ServerBusy(Exception):
    """Raised when the concurrency cap is saturated and the wait budget is exhausted."""


def _default_target(mql, db_path, features, q):
    """Run a query in the worker process; ship the result over the queue.

    The result cap is read from MAX_RESULTS (inherited by the spawned worker)
    so the harvest stops at the limit even for a query matching huge sets."""
    try:
        raw = os.environ.get("MAX_RESULTS", "100")
        limit = int(raw) if raw else None
        res = run_query(mql, db_path, features, limit=limit)
        q.put(("ok", res))
    except Exception as exc:  # noqa: BLE001 - report any failure to the parent
        q.put(("err", repr(exc)))


class QueryGuard:
    """Runs each query in a worker process with a concurrency cap + hard timeout."""

    def __init__(self, db_path, max_concurrent=4, timeout_seconds=15,
                 busy_timeout_seconds=10, target=_default_target,
                 mp_context="spawn"):
        self._db_path = db_path
        self._timeout = timeout_seconds
        self._busy_timeout = busy_timeout_seconds
        self._target = target
        self._sem = threading.Semaphore(max_concurrent)
        # "spawn" is the safe default (Emdros). TF passes "fork" where
        # available so workers inherit the warm corpus copy-on-write instead
        # of reloading it per query.
        self._ctx = multiprocessing.get_context(mp_context)

    def _kill(self, proc):
        proc.terminate()                       # SIGTERM
        proc.join(timeout=_TERM_GRACE_SECONDS)
        if proc.is_alive():
            proc.kill()                        # SIGKILL
            proc.join()

    def run(self, mql, features=None) -> RunResult:
        if not self._sem.acquire(timeout=self._busy_timeout):
            raise ServerBusy(
                "too many concurrent queries; try again shortly"
            )
        try:
            q = self._ctx.Queue()
            proc = self._ctx.Process(
                target=self._target,
                args=(mql, self._db_path, features or [], q),
                daemon=True,
            )
            proc.start()
            deadline = time.monotonic() + self._timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._kill(proc)
                    raise QueryTimeout(
                        f"query exceeded {self._timeout}s and was terminated"
                    )
                try:
                    status, payload = q.get(timeout=min(0.1, remaining))
                    break
                except _queue.Empty:
                    if not proc.is_alive():
                        # Crashed without reporting (e.g. a segfault in the
                        # C layer). Drain once more first: the worker may have
                        # put its result and exited between our get and here.
                        proc.join()
                        try:
                            status, payload = q.get_nowait()
                            break
                        except _queue.Empty:
                            raise WorkerCrashed(
                                "query worker died unexpectedly "
                                f"(exit code {proc.exitcode})"
                            )
            proc.join(timeout=_TERM_GRACE_SECONDS)
            if proc.is_alive():
                self._kill(proc)
            if status == "err":
                raise RuntimeError(payload)
            return payload
        finally:
            self._sem.release()

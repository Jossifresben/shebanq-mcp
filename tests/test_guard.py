import threading
import time

import pytest

from shebanq_mcp.guard import QueryGuard, QueryTimeout, ServerBusy, WorkerCrashed
from shebanq_mcp.runner import RunResult
from tests import guard_targets


def test_guard_returns_result_on_success():
    guard = QueryGuard("unused.db", max_concurrent=2,
                       timeout_seconds=5, target=guard_targets.fast)
    result = guard.run("SELECT ... GO", features=["sp"])
    assert isinstance(result, RunResult)
    assert result.count == 3


def test_guard_raises_on_timeout():
    guard = QueryGuard("unused.db", max_concurrent=2,
                       timeout_seconds=0.5, target=guard_targets.slow)
    with pytest.raises(QueryTimeout):
        guard.run("SELECT ... GO")


def test_guard_propagates_worker_error():
    guard = QueryGuard("unused.db", max_concurrent=2,
                       timeout_seconds=5, target=guard_targets.boom)
    with pytest.raises(RuntimeError) as exc:
        guard.run("SELECT ... GO")
    assert "deliberate failure" in str(exc.value)


def test_guard_sigkills_a_sigterm_ignoring_worker():
    # Worker ignores SIGTERM and would sleep 30s; the guard must SIGKILL it and
    # return promptly, not hang for 30s.
    guard = QueryGuard("unused.db", max_concurrent=2,
                       timeout_seconds=0.5, target=guard_targets.stubborn)
    start = time.monotonic()
    with pytest.raises(QueryTimeout):
        guard.run("SELECT ... GO")
    assert time.monotonic() - start < 8.0


def test_guard_caps_concurrency():
    guard = QueryGuard("unused.db", max_concurrent=1,
                       timeout_seconds=10, target=guard_targets.slow)
    start = time.monotonic()
    threads = [threading.Thread(target=guard.run, args=("SELECT ... GO",))
               for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # Two 3s queries serialized by a cap of 1 => >= ~6s.
    assert time.monotonic() - start >= 5.0


def test_guard_detects_crashed_worker_promptly():
    guard = QueryGuard("unused.db", max_concurrent=2,
                       timeout_seconds=10, target=guard_targets.crash)
    start = time.monotonic()
    with pytest.raises(WorkerCrashed):
        guard.run("SELECT ... GO")
    # Must detect the crash quickly, not wait out the 10s budget.
    assert time.monotonic() - start < 5.0


def test_guard_raises_busy_when_saturated():
    guard = QueryGuard("unused.db", max_concurrent=1, timeout_seconds=10,
                       busy_timeout_seconds=0.2, target=guard_targets.slow)
    t = threading.Thread(target=guard.run, args=("SELECT ... GO",))
    t.start()
    time.sleep(0.5)  # let the slow worker occupy the only slot
    with pytest.raises(ServerBusy):
        guard.run("SELECT ... GO")
    t.join()

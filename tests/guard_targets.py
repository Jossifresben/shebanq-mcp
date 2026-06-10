"""Worker targets for QueryGuard tests. Top-level so multiprocessing spawn can
import them by qualified name."""
import signal
import time

from shebanq_mcp.runner import RunResult


def fast(mql, db_path, features, q):
    q.put(("ok", RunResult(count=3, matches=[])))


def slow(mql, db_path, features, q):
    time.sleep(3)
    q.put(("ok", RunResult(count=0, matches=[])))


def boom(mql, db_path, features, q):
    q.put(("err", "deliberate failure"))


def crash(mql, db_path, features, q):
    import os
    os._exit(1)  # die without reporting, like a segfault would


def stubborn(mql, db_path, features, q):
    # Ignore SIGTERM, then sleep long. Only SIGKILL can stop this — it proves
    # the guard escalates terminate() -> kill().
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    time.sleep(30)
    q.put(("ok", RunResult(count=0, matches=[])))

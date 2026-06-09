from shebanq_mcp import server
from shebanq_mcp.runner import RunResult


def test_run_pipeline_uses_executor_seam(monkeypatch):
    seen = {}

    def fake_executor(mql, features):
        seen["mql"] = mql
        seen["features"] = features
        return RunResult(count=2, matches=[])

    monkeypatch.setattr(server, "_executor", fake_executor)
    out = server.handle_run_mql(
        "SELECT ALL OBJECTS WHERE [word vs=nif GET sp, gloss] GO"
    )
    assert out["result_count"] == 2
    assert seen["features"] == ["sp", "gloss"]


def test_resolve_transport_defaults_to_stdio(monkeypatch):
    monkeypatch.delenv("MCP_TRANSPORT", raising=False)
    assert server._resolve_transport() == "stdio"


def test_resolve_transport_http(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    assert server._resolve_transport() == "streamable-http"


def test_resolve_transport_unknown_raises(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "carrier-pigeon")
    try:
        server._resolve_transport()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "carrier-pigeon" in str(exc)


def test_install_guard_swaps_executor():
    server._executor = server._default_executor
    try:
        server._install_guard(max_concurrent=2, timeout_seconds=3)
        assert server._executor is not server._default_executor
    finally:
        server._executor = server._default_executor


def test_startup_selftest_sets_ready_on_success():
    from shebanq_mcp.runner import RunResult
    server._ready = False
    ok = server._run_startup_selftest(query_fn=lambda: RunResult(count=48, matches=[]))
    assert ok is True and server._ready is True
    assert server._health_payload()["status"] == "ok"


def test_startup_selftest_marks_unready_on_failure():
    server._ready = True

    def boom():
        raise RuntimeError("no db")

    ok = server._run_startup_selftest(query_fn=boom)
    assert ok is False and server._ready is False
    assert server._health_payload()["status"] != "ok"

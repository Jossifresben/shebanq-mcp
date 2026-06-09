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

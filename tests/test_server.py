from shebanq_mcp import server


def test_get_features_extracts_clause_in_order():
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>' GET sp, vs, gloss] GO"
    assert server._get_features(mql) == ["sp", "vs", "gloss"]


def test_get_features_empty_when_no_get_clause():
    mql = "SELECT ALL OBJECTS WHERE [word vs=nif] GO"
    assert server._get_features(mql) == []


def test_lookup_feature_returns_table():
    out = server.handle_lookup_feature("vs")
    assert out["gloss"] == "verbal stem"
    assert out["values"]["nif"] == "Niphal"


def test_lookup_feature_unknown_returns_error_field():
    out = server.handle_lookup_feature("bogus")
    assert out["error"]


def test_run_mql_rejects_invalid_before_running(monkeypatch):
    called = {"ran": False}

    def _should_not_run(*a, **k):
        called["ran"] = True

    monkeypatch.setattr(server, "run_query", _should_not_run)
    out = server.handle_run_mql("SELECT ALL OBJECTS WHERE [word vs='niphal'] GO")
    assert out["error"]
    assert "niphal" in " ".join(out["validation_errors"])
    assert called["ran"] is False


def test_run_mql_valid_runs_and_formats(monkeypatch):
    from shebanq_mcp.runner import RunResult

    def _fake_run(mql, db_path, features=None, limit=None):
        return RunResult(count=1, matches=[
            {"id_d": 1, "monad": 5, "gloss": "create",
             "book": "Genesis", "chapter": 1, "verse": 1}
        ])

    monkeypatch.setattr(server, "run_query", _fake_run)
    out = server.handle_run_mql("SELECT ALL OBJECTS WHERE [word vs=nif] GO")
    assert out["mql"].startswith("SELECT")
    assert out["result_count"] == 1
    assert out["results"][0]["reference"] == "Genesis 1:1"


class _FakeTranslator:
    def __init__(self, mql):
        self._mql = mql

    def translate(self, question, ref):
        return self._mql


def test_search_bhsa_translates_then_runs(monkeypatch):
    from shebanq_mcp.runner import RunResult

    monkeypatch.setattr(
        server, "_translator",
        _FakeTranslator("SELECT ALL OBJECTS WHERE [word vs=nif] GO"),
    )
    monkeypatch.setattr(
        server, "run_query",
        lambda mql, db_path, features=None, limit=None: RunResult(count=0, matches=[]),
    )
    out = server.handle_search_bhsa("all niphal verbs")
    assert out["mql"].startswith("SELECT")
    assert out["result_count"] == 0
    assert out["results"] == []


def test_search_bhsa_without_translator_returns_concise_primer(monkeypatch):
    monkeypatch.setattr(server, "_translator", None)
    out = server.handle_search_bhsa("all niphal verbs")
    assert out["question"] == "all niphal verbs"
    assert "UNQUOTED" in out["guidance"]
    assert "lookup_feature" in out["hint"]
    assert "run_mql" in out["next"]
    assert "error" not in out
    # Concise: it must NOT dump the full 237-constant reference.
    assert len(out["guidance"]) < 600


def test_run_pipeline_flags_truncation_from_capped_result(monkeypatch):
    # The cap lives in the executor/runner (harvest stops at the limit).
    # _run_pipeline reports the true total and flags that fewer rows came back.
    from shebanq_mcp.runner import RunResult
    capped = [{"id_d": i} for i in range(3)]   # executor already capped to 3
    monkeypatch.setattr(server, "_executor",
                        lambda mql, features: RunResult(count=10, matches=capped))
    out = server.handle_run_mql("SELECT ALL OBJECTS WHERE [word sp=verb] GO")
    assert out["result_count"] == 10          # honest total
    assert len(out["results"]) == 3           # only the harvested rows
    assert out["results_truncated"] is True
    assert out["results_shown"] == 3


def test_default_executor_passes_result_limit(monkeypatch):
    # The deploy path must hand the cap down to run_query, not slice afterward.
    from shebanq_mcp.runner import RunResult
    captured = {}

    def fake_run_query(mql, db_path, features, limit=None):
        captured["limit"] = limit
        return RunResult(count=0, matches=[])

    monkeypatch.setattr(server, "run_query", fake_run_query)
    monkeypatch.setattr(server, "_RESULT_LIMIT", 42)
    server._default_executor("SELECT ALL OBJECTS WHERE [word] GO", [])
    assert captured["limit"] == 42


def test_run_pipeline_no_truncation_flag_under_cap(monkeypatch):
    from shebanq_mcp.runner import RunResult
    monkeypatch.setattr(server, "_RESULT_LIMIT", 100)
    matches = [{"id_d": i} for i in range(2)]
    monkeypatch.setattr(server, "_executor",
                        lambda mql, features: RunResult(count=2, matches=matches))
    out = server.handle_run_mql("SELECT ALL OBJECTS WHERE [word vs=nif] GO")
    assert out["result_count"] == 2
    assert len(out["results"]) == 2
    assert "results_truncated" not in out

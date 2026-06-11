import pytest

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


def test_run_pipeline_wraps_executor_errors(monkeypatch):
    def boom(mql, features):
        raise RuntimeError("Emdros error: typecheck failed")
    monkeypatch.setattr(server, "_executor", boom)
    out = server.handle_run_mql("SELECT ALL OBJECTS WHERE [word sp=verb] GO")
    assert "error" in out
    assert "typecheck failed" in out["error"]
    assert out["mql"].startswith("SELECT")


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


def test_startup_selftest_sets_ready_on_success(monkeypatch):
    monkeypatch.setattr(server, "_ready", False)
    ok = server._run_startup_selftest(query_fn=lambda: RunResult(count=48, matches=[]))
    assert ok is True and server._ready is True
    assert server._health_payload()["status"] == "ok"


def test_startup_selftest_marks_unready_on_failure(monkeypatch):
    monkeypatch.setattr(server, "_ready", True)

    def boom():
        raise RuntimeError("no db")

    ok = server._run_startup_selftest(query_fn=boom)
    assert ok is False and server._ready is False
    assert server._health_payload()["status"] != "ok"


def test_main_rejects_nonpositive_guard_config(monkeypatch):
    monkeypatch.setenv("MCP_TRANSPORT", "http")
    monkeypatch.setenv("MAX_CONCURRENT_QUERIES", "0")
    with pytest.raises(SystemExit):
        server.main()


def test_mql_prompt_text_includes_full_reference_and_question():
    text = server._mql_prompt_text("all niphal verbs")
    assert "UNQUOTED" in text
    assert "all niphal verbs" in text
    assert "run_mql" in text
    # The prompt carries the full reference (much larger than the primer).
    assert len(text) > 600


def test_http_security_disabled_by_default(monkeypatch):
    # Public deploy behind a proxy host: FastMCP's default DNS-rebinding guard
    # only trusts localhost and 421s everything else. Default to disabled.
    monkeypatch.delenv("MCP_ALLOWED_HOSTS", raising=False)
    server._configure_http_security()
    ts = server.mcp.settings.transport_security
    assert ts.enable_dns_rebinding_protection is False


def test_http_security_strict_allowlist_from_env(monkeypatch):
    monkeypatch.setenv("MCP_ALLOWED_HOSTS",
                       "shebanq-mcp.onrender.com, example.com")
    server._configure_http_security()
    ts = server.mcp.settings.transport_security
    assert ts.enable_dns_rebinding_protection is True
    assert "shebanq-mcp.onrender.com" in ts.allowed_hosts
    assert "example.com" in ts.allowed_hosts


def test_web_api_enabled_parses_truthy(monkeypatch):
    for v in ("on", "1", "true", "YES"):
        monkeypatch.setenv("WEB_API", v)
        assert server._web_api_enabled() is True
    for v in ("", "off", "0", "false"):
        monkeypatch.setenv("WEB_API", v)
        assert server._web_api_enabled() is False


def test_handle_ask_passes_through_a_real_result(monkeypatch):
    from shebanq_mcp.runner import RunResult
    monkeypatch.setattr(server, "_translator", object())  # non-None
    monkeypatch.setattr(
        server, "handle_search_bhsa",
        lambda q: {"question": q, "mql": "SELECT ... GO",
                   "result_count": 2, "results": []},
    )
    out = server.handle_ask("niphal verbs")
    assert out["mql"].startswith("SELECT")
    assert "degraded" not in out


def test_handle_ask_degrades_when_translation_raises(monkeypatch):
    def boom(q):
        raise RuntimeError("anthropic: spend limit reached")
    monkeypatch.setattr(server, "handle_search_bhsa", boom)
    out = server.handle_ask("niphal verbs")
    assert out["degraded"] is True
    assert "UNQUOTED" in out["guidance"]
    assert "mql" not in out


def test_handle_ask_degrades_when_no_mql(monkeypatch):
    # translator-free path returns a primer (no 'mql') -> treat as degraded
    monkeypatch.setattr(server, "handle_search_bhsa",
                        lambda q: {"question": q, "guidance": "x"})
    out = server.handle_ask("niphal verbs")
    assert out["degraded"] is True


def test_handle_translate_returns_mql_without_running(monkeypatch):
    class _T:
        def translate(self, q, ref):
            return "SELECT ALL OBJECTS WHERE [word sp=verb] GO"
    monkeypatch.setattr(server, "_translator", _T())
    ran = {"x": False}
    monkeypatch.setattr(server, "_executor",
                        lambda *a, **k: ran.__setitem__("x", True))
    out = server.handle_translate("all verbs")
    assert out["mql"].startswith("SELECT")
    assert "result_count" not in out and "results" not in out
    assert "degraded" not in out
    assert ran["x"] is False          # translate must NOT run the query


def test_handle_translate_degrades_without_translator(monkeypatch):
    monkeypatch.setattr(server, "_translator", None)
    out = server.handle_translate("x")
    assert out["degraded"] is True and "mql" not in out


def test_handle_translate_degrades_when_translate_raises(monkeypatch):
    class _Boom:
        def translate(self, q, ref):
            raise RuntimeError("spend cap reached")
    monkeypatch.setattr(server, "_translator", _Boom())
    out = server.handle_translate("x")
    assert out["degraded"] is True


def test_wrap_in_verse_wraps_a_flat_word_query():
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO"
    wrapped = server._wrap_in_verse(mql)
    assert wrapped == ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
                       "[word lex='BR>[' GET g_word_utf8, gloss]] GO")


def test_wrap_in_verse_leaves_unmatched_query_unchanged():
    weird = "GET OBJECTS HAVING MONADS IN {1-3} GO"
    assert server._wrap_in_verse(weird) == weird


def test_handle_translate_with_references_wraps(monkeypatch):
    class _T:
        def translate(self, q, ref):
            return "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO"
    monkeypatch.setattr(server, "_translator", _T())
    out = server.handle_translate("bara", references=True)
    assert out["mql"].startswith("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse")
    assert "degraded" not in out


def test_handle_translate_without_references_stays_flat(monkeypatch):
    class _T:
        def translate(self, q, ref):
            return "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO"
    monkeypatch.setattr(server, "_translator", _T())
    out = server.handle_translate("bara", references=False)
    assert "[verse" not in out["mql"]


def test_handle_translate_references_default_false(monkeypatch):
    class _T:
        def translate(self, q, ref):
            return "SELECT ALL OBJECTS WHERE [word sp=verb GET g_word_utf8, gloss] GO"
    monkeypatch.setattr(server, "_translator", _T())
    assert "[verse" not in server.handle_translate("verbs")["mql"]


def test_handle_translate_returns_both_forms_from_one_translation(monkeypatch):
    # One translation, both forms returned, so toggling the reference checkbox
    # never re-translates (and never silently changes which query the user runs).
    calls = {"n": 0}

    class _T:
        def translate(self, q, ref):
            calls["n"] += 1
            return "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO"
    monkeypatch.setattr(server, "_translator", _T())
    out = server.handle_translate("bara", references=True)
    assert calls["n"] == 1
    assert "[verse" not in out["mql_flat"]
    assert out["mql_ref"].startswith("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse")
    # The two forms are the same core query: unwrapping the ref form == the flat form.
    assert server._unwrap_verse(out["mql_ref"]) == out["mql_flat"]
    # `mql` mirrors the requested flag for back-compat.
    assert out["mql"] == out["mql_ref"]
    assert server.handle_translate("bara", references=False)["mql"] == out["mql_flat"]


def test_wrap_in_verse_is_idempotent():
    nested = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
              "[word lex='BR>[' GET g_word_utf8, gloss]] GO")
    assert server._wrap_in_verse(nested) == nested


def test_handle_translate_unwraps_llm_added_verse_wrapper(monkeypatch):
    # The LLM sometimes verse-wraps on its own; with references=False the
    # wrapper must come OFF, not merely not be added.
    class _T:
        def translate(self, q, ref):
            return ("SELECT ALL OBJECTS WHERE\n"
                    "  [verse GET book, chapter, verse\n"
                    "    [clause\n"
                    "      [phrase function=Pred\n"
                    "        [word sp=verb AND vt=wayq AND lex='DBR[' GET g_word_utf8, gloss]\n"
                    "      ]\n"
                    "      ..\n"
                    "      [phrase function=Cmpl\n"
                    "        [word sp=prep AND lex='<M' GET g_word_utf8, gloss]\n"
                    "      ]\n"
                    "    ]\n"
                    "  ]\n"
                    "GO")
    monkeypatch.setattr(server, "_translator", _T())
    out = server.handle_translate("how often does 'it spoke with' occur",
                                  references=False)
    assert "[verse" not in out["mql"]
    assert "[clause" in out["mql"] and "function=Cmpl" in out["mql"]
    assert out["mql"].rstrip().endswith("GO")


def test_unwrap_verse_leaves_conditioned_verse_block_alone():
    # A verse block with its own conditions is query semantics, not a
    # reference wrapper; references=False must not strip it.
    mql = "SELECT ALL OBJECTS WHERE [verse book=Genesis [word sp=verb]] GO"
    assert server._unwrap_verse(mql) == mql


def test_wrap_then_unwrap_round_trips():
    flat = "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO"
    assert server._unwrap_verse(server._wrap_in_verse(flat)) == flat


def test_search_bhsa_throttles_translation(monkeypatch):
    import shebanq_mcp.server as server
    from shebanq_mcp.web import RateLimiter
    calls = {"n": 0}

    class _T:
        def translate(self, q, ref):
            calls["n"] += 1
            return "SELECT ALL OBJECTS WHERE [word sp=verb] GO"

    monkeypatch.setattr(server, "_translator", _T())
    monkeypatch.setattr(server, "_executor",
                        lambda *a, **k: type("R", (), {"count": 1, "matches": []})())
    monkeypatch.setattr(server, "_TRANSLATE_LIMITER", RateLimiter(1))   # 1/min
    a = server.handle_search_bhsa("verbs")     # allowed -> translates
    b = server.handle_search_bhsa("verbs")     # throttled -> no translate
    assert "mql" in a or "result_count" in a
    assert b.get("error") and "rate" in b["error"].lower()
    assert calls["n"] == 1


def test_search_bhsa_degrades_on_translate_error(monkeypatch):
    import shebanq_mcp.server as server
    from shebanq_mcp.web import RateLimiter

    class _Boom:
        def translate(self, q, ref):
            raise RuntimeError("spend cap reached")

    monkeypatch.setattr(server, "_translator", _Boom())
    monkeypatch.setattr(server, "_TRANSLATE_LIMITER", RateLimiter(100))
    out = server.handle_search_bhsa("verbs")
    assert out.get("error") and "run_mql" in out["error"]
    assert "result_count" not in out

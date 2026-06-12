"""Tool wiring tests with stubbed executors and translators. No TF or Emdros
data needed: the executor seam is swapped exactly the way test_server.py does
for the MQL path."""
import pytest

from shebanq_mcp import server
from shebanq_mcp.runner import RunResult


GOOD_TEMPLATE = "word sp=verb"
GOOD_MQL = "SELECT ALL OBJECTS WHERE [word sp=verb] GO"


class StubTranslator:
    def __init__(self, out):
        self._out = out

    def translate(self, question, ref):
        return self._out


@pytest.fixture
def stub_engines(monkeypatch):
    rows = [{"id_d": 11, "book": "Genesis", "chapter": "1", "verse": "1",
             "text": "ברא", "gloss": "create", "sp": "verb"}]
    monkeypatch.setattr(server, "_tf_executor",
                        lambda template, features: RunResult(1, list(rows)))
    monkeypatch.setattr(server, "_executor",
                        lambda mql, features: RunResult(1, list(rows)))
    monkeypatch.setattr(server, "_translator", StubTranslator(GOOD_MQL))
    return rows


def test_run_tf_happy_path(stub_engines):
    out = server.handle_run_tf(GOOD_TEMPLATE)
    assert out["tf_template"] == GOOD_TEMPLATE
    assert out["result_count"] == 1
    assert out["results"][0]["reference"] == "Genesis 1:1"


def test_run_tf_validation_failure():
    out = server.handle_run_tf("wibble sp=verb")
    assert out["error"] == "TF template failed validation"
    assert out["validation_errors"]


def test_run_tf_engine_error(monkeypatch):
    def boom(template, features):
        raise RuntimeError("TF exploded")
    monkeypatch.setattr(server, "_tf_executor", boom)
    out = server.handle_run_tf(GOOD_TEMPLATE)
    assert out["error"] == "TF exploded"


def test_search_bhsa_returns_mql_and_derived_tf(stub_engines, monkeypatch):
    monkeypatch.setattr(server, "_RESULT_ENGINE", "tf")
    out = server.handle_search_bhsa("all verbs")
    assert out["mql"] == GOOD_MQL
    assert out["tf"] == {"template": "word sp=verb", "notes": []}
    assert out["engine"] == "tf"
    assert out["result_count"] == 1


def test_search_bhsa_emdros_engine(stub_engines, monkeypatch):
    monkeypatch.setattr(server, "_RESULT_ENGINE", "emdros")
    out = server.handle_search_bhsa("all verbs")
    assert out["mql"] == GOOD_MQL
    assert out["tf"] == {"template": "word sp=verb", "notes": []}
    assert out["engine"] == "emdros"
    assert out["result_count"] == 1


# test_search_bhsa_tf_translation_failure_degrades: removed; the TF translator
# no longer exists (derivation cannot fail with an API error). The unconvertible
# MQL case is covered by test_search_bhsa_tf_error_on_unconvertible_mql.


# test_search_bhsa_invalid_tf_artifact_marked: removed; derivation only emits
# valid grammar (pinned by converter tests), so tf_validation_errors cannot
# appear. Unconvertible cases are covered by test_search_bhsa_tf_error_on_unconvertible_mql.


def test_search_bhsa_translation_free_mode(monkeypatch):
    monkeypatch.setattr(server, "_translator", None)
    out = server.handle_search_bhsa("all verbs")
    assert "next" in out                          # existing guidance payload


def test_handle_ask_degrades_on_invalid_mql_artifact(stub_engines, monkeypatch):
    # sp='verb' is a quoted enum: fails validation -> mql_validation_errors present
    monkeypatch.setattr(server, "_translator", StubTranslator("SELECT ALL OBJECTS WHERE [word sp='verb'] GO"))
    monkeypatch.setattr(server, "_RESULT_ENGINE", "tf")
    out = server.handle_ask("all verbs")
    assert out.get("degraded") is True            # no invalid-MQL-next-to-results


def test_search_bhsa_falls_back_to_emdros_when_derivation_refuses(stub_engines, monkeypatch):
    focus_mql = "SELECT ALL OBJECTS WHERE [word FOCUS sp=verb] GO"
    monkeypatch.setattr(server, "_translator", StubTranslator(focus_mql))
    monkeypatch.setattr(server, "_RESULT_ENGINE", "tf")
    out = server.handle_search_bhsa("all verbs")
    assert "cannot be converted" in out["tf"]["error"]
    assert out["engine"] == "emdros"              # fallback fired
    assert out["result_count"] == 1


def test_search_bhsa_invalid_mql_early_returns(stub_engines, monkeypatch):
    monkeypatch.setattr(server, "_translator", StubTranslator("DROP DATABASE x"))
    monkeypatch.setattr(server, "_RESULT_ENGINE", "emdros")
    out = server.handle_search_bhsa("all verbs")
    assert out["mql_validation_errors"]
    assert out["error"] == "the generated MQL failed validation"
    assert "result_count" not in out
    assert "tf" not in out


def test_to_citable_mql_happy_path():
    out = server.handle_to_citable_mql("word sp=verb vs=nif")
    assert out["mql"] == "SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif] GO"
    assert "SHEBANQ" in out["next"]


def test_to_citable_mql_refusal():
    out = server.handle_to_citable_mql("word lex~BR")
    assert "cannot be converted" in out["error"]
    assert "mql" not in out


def test_to_tf_template_happy_path():
    out = server.handle_to_tf_template(
        "SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif] GO")
    assert out["tf_template"] == "word sp=verb vs=nif"
    assert out["mql"].startswith("SELECT")
    assert "run_tf" in out["next"]


def test_to_tf_template_get_note():
    out = server.handle_to_tf_template(
        "SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
        "[word sp=verb]] GO")
    assert out["tf_template"] == "verse\n  word sp=verb"
    assert out["notes"] == ["GET clauses dropped; Text-Fabric results "
                            "expose all features."]


def test_to_tf_template_refusal():
    out = server.handle_to_tf_template(
        "SELECT ALL OBJECTS WHERE [word sp=verb OR sp=subs] GO")
    assert "cannot be converted" in out["error"]
    assert "tf_template" not in out


def test_handle_convert_both_directions():
    a = server.handle_convert("word sp=verb")
    assert a["direction"] == "tf_to_mql" and a["output"].startswith("SELECT")
    b = server.handle_convert("SELECT ALL OBJECTS WHERE [word sp=verb] GO")
    assert b["direction"] == "mql_to_tf" and b["output"] == "word sp=verb"


class CountingTranslator:
    """A stub that counts calls -- proves derive-not-generate."""

    def __init__(self, out):
        self._out = out
        self.calls = 0

    def translate(self, question, ref):
        self.calls += 1
        return self._out


def test_search_bhsa_derives_tf_with_one_model_call(stub_engines, monkeypatch):
    counting = CountingTranslator(GOOD_MQL)
    monkeypatch.setattr(server, "_translator", counting)
    monkeypatch.setattr(server, "_RESULT_ENGINE", "emdros")
    out = server.handle_search_bhsa("all verbs")
    assert counting.calls == 1                      # exactly one LLM call
    assert out["tf"] == {"template": "word sp=verb", "notes": []}
    assert out["result_count"] == 1


def test_search_bhsa_tf_error_on_unconvertible_mql(stub_engines, monkeypatch):
    focus_mql = "SELECT ALL OBJECTS WHERE [word FOCUS sp=verb] GO"
    monkeypatch.setattr(server, "_translator", StubTranslator(focus_mql))
    monkeypatch.setattr(server, "_RESULT_ENGINE", "emdros")
    out = server.handle_search_bhsa("all verbs")
    assert "cannot be converted" in out["tf"]["error"]
    assert "template" not in out["tf"]
    assert out["result_count"] == 1                 # MQL flow unaffected


def test_translate_derives_both_forms(monkeypatch):
    monkeypatch.setattr(server, "_translator", StubTranslator(GOOD_MQL))
    out = server.handle_translate("all verbs", references=True)
    assert out["tf_flat"] == {"template": "word sp=verb", "notes": []}
    # wrap-then-derive: the ref form's template starts at the verse level
    assert out["tf_ref"]["template"].startswith("verse")
    assert out["tf_ref"]["notes"] == [
        "GET clauses dropped; Text-Fabric results expose all features."]


def test_translate_tf_error_rides_along(monkeypatch):
    focus_mql = "SELECT ALL OBJECTS WHERE [word FOCUS sp=verb] GO"
    monkeypatch.setattr(server, "_translator", StubTranslator(focus_mql))
    out = server.handle_translate("all verbs")
    assert out["mql"]                               # MQL path unaffected
    assert "cannot be converted" in out["tf_flat"]["error"]

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
    monkeypatch.setattr(server, "_tf_translator", StubTranslator(GOOD_TEMPLATE))
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


def test_search_bhsa_dual_emit(stub_engines, monkeypatch):
    monkeypatch.setattr(server, "_RESULT_ENGINE", "tf")
    out = server.handle_search_bhsa("all verbs")
    assert out["mql"] == GOOD_MQL
    assert out["tf_template"] == GOOD_TEMPLATE
    assert out["engine"] == "tf"
    assert out["result_count"] == 1


def test_search_bhsa_emdros_engine(stub_engines, monkeypatch):
    monkeypatch.setattr(server, "_RESULT_ENGINE", "emdros")
    out = server.handle_search_bhsa("all verbs")
    assert out["mql"] == GOOD_MQL
    assert out["tf_template"] == GOOD_TEMPLATE
    assert out["engine"] == "emdros"
    assert out["result_count"] == 1


def test_search_bhsa_tf_translation_failure_degrades(stub_engines, monkeypatch):
    class Boom:
        def translate(self, question, ref):
            raise RuntimeError("api down")
    monkeypatch.setattr(server, "_tf_translator", Boom())
    monkeypatch.setattr(server, "_RESULT_ENGINE", "emdros")
    out = server.handle_search_bhsa("all verbs")
    assert out["mql"] == GOOD_MQL                 # MQL artifact survives
    assert "tf_template" not in out
    assert out["tf_error"]
    assert out["result_count"] == 1               # results still flow


def test_search_bhsa_invalid_tf_artifact_marked(stub_engines, monkeypatch):
    monkeypatch.setattr(server, "_tf_translator", StubTranslator("wibble x=1"))
    monkeypatch.setattr(server, "_RESULT_ENGINE", "emdros")
    out = server.handle_search_bhsa("all verbs")
    assert out["tf_template"] == "wibble x=1"     # shown, marked invalid
    assert out["tf_validation_errors"]
    assert out["result_count"] == 1


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


def test_search_bhsa_falls_back_to_emdros_when_tf_invalid(stub_engines, monkeypatch):
    monkeypatch.setattr(server, "_tf_translator", StubTranslator("wibble x=1"))
    monkeypatch.setattr(server, "_RESULT_ENGINE", "tf")
    out = server.handle_search_bhsa("all verbs")
    assert out["tf_validation_errors"]
    assert out["engine"] == "emdros"              # fallback fired
    assert out["result_count"] == 1


def test_search_bhsa_falls_back_to_tf_when_mql_invalid(stub_engines, monkeypatch):
    monkeypatch.setattr(server, "_translator", StubTranslator("DROP DATABASE x"))
    monkeypatch.setattr(server, "_RESULT_ENGINE", "emdros")
    out = server.handle_search_bhsa("all verbs")
    assert out["mql_validation_errors"]
    assert out["engine"] == "tf"
    assert out["result_count"] == 1


def test_search_bhsa_no_valid_artifact(stub_engines, monkeypatch):
    monkeypatch.setattr(server, "_translator", StubTranslator("DROP DATABASE x"))
    monkeypatch.setattr(server, "_tf_translator", StubTranslator("wibble x=1"))
    out = server.handle_search_bhsa("all verbs")
    assert out["error"] == "no valid query artifact to run"
    assert out["mql_validation_errors"] and out["tf_validation_errors"]

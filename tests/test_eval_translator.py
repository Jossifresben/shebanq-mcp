import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import eval_translator as ev  # noqa: E402


def test_cost_matches_pricing():
    assert abs(ev.cost("claude-opus-4-8", 4000, 60) - (0.020 + 0.0015)) < 1e-9
    assert ev.cost("claude-haiku-4-5", 1000, 100) < ev.cost("claude-opus-4-8", 1000, 100)


def test_score_invalid_when_validation_fails():
    from shebanq_mcp.feature_reference import FeatureReference
    ref = FeatureReference.load()
    verdict, count = ev.score("SELECT ALL OBJECTS WHERE [word rela=Objc] GO", 5, ref)
    assert verdict == "invalid" and count is None


def test_score_ok_and_wrong(monkeypatch):
    from shebanq_mcp.feature_reference import FeatureReference
    ref = FeatureReference.load()
    monkeypatch.setattr(ev, "run_query", lambda mql, db, limit=1: type("R", (), {"count": 48})())
    ok, c = ev.score("SELECT ALL OBJECTS WHERE [word lex='BR>['] GO", 48, ref)
    assert ok == "ok" and c == 48
    wrong, c2 = ev.score("SELECT ALL OBJECTS WHERE [word lex='BR>['] GO", 99, ref)
    assert wrong == "wrong:48" and c2 == 48

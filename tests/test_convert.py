import pytest

from shebanq_mcp.convert import detect_and_convert
from shebanq_mcp.feature_reference import FeatureReference


@pytest.fixture(scope="module")
def ref():
    return FeatureReference.load()


def test_mql_detected_and_converted(ref):
    out = detect_and_convert("SELECT ALL OBJECTS WHERE [word sp=verb] GO", ref)
    assert out == {"direction": "mql_to_tf", "output": "word sp=verb",
                   "notes": []}


def test_tf_detected_and_converted(ref):
    out = detect_and_convert("word sp=verb", ref)
    assert out == {"direction": "tf_to_mql",
                   "output": "SELECT ALL OBJECTS WHERE [word sp=verb] GO",
                   "notes": []}


def test_detection_is_case_insensitive_and_strips(ref):
    out = detect_and_convert("  select all objects where [word sp=verb] go  ", ref)
    assert out["direction"] == "mql_to_tf"
    assert "output" in out


def test_get_note_passes_through(ref):
    out = detect_and_convert(
        "SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
        "[word sp=verb]] GO", ref)
    assert out["notes"] == ["GET clauses dropped; Text-Fabric results "
                            "expose all features."]


def test_refusal_carries_direction_and_error(ref):
    out = detect_and_convert("word lex~BR", ref)
    assert out["direction"] == "tf_to_mql"
    assert "cannot be converted" in out["error"]
    assert "output" not in out


def test_empty_input(ref):
    assert detect_and_convert("   ", ref) == {"error": "input is empty"}

from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.tf_translate import build_tf_prompt, build_tf_translator


def test_tf_prompt_contains_primer_and_reference():
    ref = FeatureReference.load()
    prompt = build_tf_prompt(ref)
    assert "Text-Fabric search template" in prompt   # output rule
    assert "indentation" in prompt.lower()           # primer teaches nesting
    assert "[word]" in prompt                        # reference block grouping
    assert "UNQUOTED" not in prompt                  # no MQL quoting talk


def test_tf_prompt_has_no_mql_skeleton():
    ref = FeatureReference.load()
    prompt = build_tf_prompt(ref)
    assert "SELECT ALL OBJECTS" not in prompt


def test_build_tf_translator_none_provider():
    assert build_tf_translator("none") is None


def test_build_tf_translator_anthropic_uses_tf_prompt():
    t = build_tf_translator("anthropic")
    ref = FeatureReference.load()
    assert t._prompt_builder(ref) == build_tf_prompt(ref)

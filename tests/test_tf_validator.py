import pytest

from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.tf_validator import validate_tf


@pytest.fixture(scope="module")
def ref():
    return FeatureReference.load()


def ok(template, ref):
    result = validate_tf(template, ref)
    assert result.ok, result.errors
    return result


def bad(template, ref):
    result = validate_tf(template, ref)
    assert not result.ok
    return result.errors


def test_flat_template_valid(ref):
    ok("word sp=verb", ref)


def test_nested_template_valid(ref):
    ok("clause\n  phrase function=Pred\n    word sp=verb vs=nif", ref)


def test_lexeme_with_trailing_bracket_valid(ref):
    ok("word lex=BR>[", ref)


def test_unknown_object_type(ref):
    errors = bad("wibble sp=verb", ref)
    assert any("unknown object type 'wibble'" in e for e in errors)


def test_unknown_feature_on_type(ref):
    errors = bad("word function=Pred", ref)   # function lives on phrase, not word
    assert any("'function' is not valid on object type 'word'" in e for e in errors)


def test_unknown_enum_value(ref):
    errors = bad("word sp=wibble", ref)
    assert any("unknown value 'wibble'" in e for e in errors)


def test_first_line_must_not_be_indented(ref):
    errors = bad("  word sp=verb", ref)
    assert any("first line" in e for e in errors)


def test_misaligned_indentation(ref):
    # 3-space line under a 0/2 stack aligns with no enclosing level
    errors = bad("clause\n  phrase\n   word", ref)
    assert any("does not align" in e for e in errors)


def test_tabs_rejected(ref):
    errors = bad("clause\n\tword", ref)
    assert any("tab" in e.lower() for e in errors)


def test_empty_template_rejected(ref):
    errors = bad("", ref)
    assert any("empty" in e.lower() for e in errors)


def test_malformed_line_rejected(ref):
    errors = bad("word sp = verb", ref)       # spaces around '=' break pairs
    assert errors


def test_blank_lines_ignored(ref):
    ok("clause\n\n  word sp=verb", ref)


def test_multi_word_value_rejected(ref):
    # 'gloss=be strong' is not expressible as a v1 feature=value pair
    errors = bad("word gloss=be strong", ref)
    assert errors


def test_named_sibling_with_ordering_valid(ref):
    ok("clause\n  p1:phrase function=Pred\n  p2:phrase function=Objc\np1 << p2",
       ref)


def test_three_named_siblings_chain_valid(ref):
    ok("clause\n  p1:phrase\n  p2:phrase\n  p3:phrase\np1 << p2\np2 << p3", ref)


def test_unordered_named_siblings_still_valid_as_template(ref):
    # names without ordering are valid TF (unordered); the converter, not the
    # validator, is what refuses converting them to MQL
    ok("clause\n  p1:phrase function=Pred\n  p2:phrase function=Objc", ref)


def test_duplicate_name_refused(ref):
    errs = bad("clause\n  p1:phrase\n  p1:phrase\np1 << p1", ref)
    assert any("duplicate" in e.lower() for e in errs)


def test_ordering_undefined_name_refused(ref):
    errs = bad("clause\n  p1:phrase\np1 << p9", ref)
    assert any("p9" in e for e in errs)


def test_self_ordering_refused(ref):
    errs = bad("clause\n  p1:phrase\np1 << p1", ref)
    assert any("itself" in e.lower() or "distinct" in e.lower() for e in errs)


def test_malformed_ordering_line_refused(ref):
    errs = bad("clause\n  p1:phrase\n  p2:phrase\np1 <> p2", ref)
    assert errs


def test_loosened_constraint_still_refused(ref):
    # Guards the STRICT pairs group: loose \S+=\S+ would silently accept
    # and then silently drop `lex~=BR`; the strict version must refuse it.
    errs = bad("word lex~=BR", ref)
    assert errs

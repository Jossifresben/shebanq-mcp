from shebanq_mcp.feature_reference import FeatureReference


def test_known_feature_has_gloss():
    ref = FeatureReference.load()
    assert ref.feature_gloss("vs") == "verbal stem"


def test_known_value_is_valid():
    ref = FeatureReference.load()
    assert ref.is_valid("vs", "nif") is True


def test_unknown_value_is_invalid():
    ref = FeatureReference.load()
    assert ref.is_valid("vs", "niphal") is False


def test_unknown_feature_is_invalid():
    ref = FeatureReference.load()
    assert ref.is_valid("bogus", "x") is False


def test_open_valued_feature_accepts_any_value():
    ref = FeatureReference.load()
    assert ref.is_valid("lex", "BR>") is True


def test_lookup_returns_value_table():
    # v2: lookup returns {"objects": {otype: {kind, gloss, values}}}
    ref = FeatureReference.load()
    result = ref.lookup("vs")
    word_spec = result["objects"]["word"]
    assert word_spec["gloss"] == "verbal stem"
    assert word_spec["values"]["nif"] == "Nif'al"


def test_kind_distinguishes_enum_and_string():
    ref = FeatureReference.load()
    assert ref.kind("vs") == "enum"
    assert ref.kind("lex") == "string"


def test_is_enum_and_is_string():
    ref = FeatureReference.load()
    assert ref.is_enum("sp") is True
    assert ref.is_enum("lex") is False
    assert ref.is_string("lex") is True
    assert ref.is_string("sp") is False


def test_enum_constant_membership():
    ref = FeatureReference.load()
    assert ref.is_enum_constant("nif") is True
    assert ref.is_enum_constant("verb") is True
    assert ref.is_enum_constant("niphal") is False


def test_v2_object_types_ordered():
    ref = FeatureReference.load()
    names = [o["name"] for o in ref.object_types()]
    assert names.index("clause") < names.index("phrase") < names.index("word")
    assert "verse" in names


def test_v2_scoped_lookups():
    ref = FeatureReference.load()
    assert ref.kind_for("typ", "clause") == "enum"
    assert "Ellp" in ref.values_for("typ", "clause")
    assert "Ellp" not in (ref.values_for("typ", "phrase") or {})
    assert "VP" in ref.values_for("typ", "phrase")
    assert ref.kind_for("rela", "clause") == "enum"
    assert ref.kind_for("lex", "word") == "string"
    assert ref.kind_for("lex", "clause") is None
    assert set(ref.objects_for("function")) == {"phrase", "phrase_atom"}


def test_v2_union_backcompat():
    ref = FeatureReference.load()
    # union semantics keep the old method names working
    assert ref.has_feature("typ") and ref.has_feature("rela")
    assert ref.is_enum("typ") and ref.is_string("lex")
    assert ref.is_valid("typ", "Ellp") and ref.is_valid("typ", "VP")
    assert not ref.is_valid("typ", "nonsense")
    assert ref.is_valid("lex", "anything")          # open-valued
    assert ref.feature_gloss("function")            # some gloss survives


def test_v2_features_for_object():
    ref = FeatureReference.load()
    clause_feats = ref.features_for("clause")
    assert "typ" in clause_feats and "kind" in clause_feats
    assert "lex" not in clause_feats


def test_v2_union_backcompat_multitype_feature():
    ref = FeatureReference.load()
    # rela spans clause/clause_atom/phrase/phrase_atom/subphrase with different
    # closed value sets; the v1 union shim must accept a value valid on ANY type
    # and reject genuine garbage (validator object-awareness comes in a later plan).
    assert len(ref.objects_for("rela")) >= 2
    # a real rela value (pick one that exists — verify with values_for) passes:
    some_clause_rela = next(iter(ref.values_for("rela", "clause")))
    assert ref.is_valid("rela", some_clause_rela)
    assert not ref.is_valid("rela", "nonsense_rela_value")


def test_mql_primer_ships_and_matches_fixtures():
    from importlib import resources
    import json
    from pathlib import Path
    text = resources.files("shebanq_mcp").joinpath("mql_primer.md").read_text(encoding="utf-8")
    assert "SELECT ALL OBJECTS WHERE" in text and "first" in text
    qs = json.loads((Path(__file__).parent / "fixtures" / "scholar_questions.json").read_text())
    ell = next(q for q in qs["questions"] if q["name"] == "ellipsis_conj_objc")
    assert ell["mql"] in text, "the motivating example must appear verbatim in the primer"

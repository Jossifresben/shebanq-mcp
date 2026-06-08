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
    ref = FeatureReference.load()
    result = ref.lookup("vs")
    assert result["gloss"] == "verbal stem"
    assert result["values"]["nif"] == "Niphal"


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

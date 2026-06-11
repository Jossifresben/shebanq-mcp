import pytest

from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.translate import AnthropicTranslator, build_translator


class _FakeBlock:
    def __init__(self, text):
        self.text = text


class _FakeMessage:
    def __init__(self, text):
        self.content = [_FakeBlock(text)]


class _FakeMessages:
    def __init__(self, text):
        self._text = text
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeMessage(self._text)


class _FakeClient:
    def __init__(self, text):
        self.messages = _FakeMessages(text)


def test_anthropic_translator_returns_mql():
    client = _FakeClient("SELECT ALL OBJECTS WHERE [word vs='nif'] GO")
    t = AnthropicTranslator(client=client)
    mql = t.translate("all niphal verbs", FeatureReference.load())
    assert mql == "SELECT ALL OBJECTS WHERE [word vs='nif'] GO"


def test_translator_injects_feature_reference_into_prompt():
    client = _FakeClient("SELECT ALL OBJECTS WHERE [word vs='nif'] GO")
    AnthropicTranslator(client=client).translate("all niphal verbs", FeatureReference.load())
    system = client.messages.last_kwargs["system"]
    assert "vs" in system and "Niphal" in system


def test_translator_strips_code_fences():
    client = _FakeClient("```\nSELECT ALL OBJECTS WHERE [word vs='nif'] GO\n```")
    mql = AnthropicTranslator(client=client).translate("x", FeatureReference.load())
    assert mql.startswith("SELECT") and "```" not in mql


def test_translator_uses_temperature_zero_for_reproducibility():
    # Same question must yield the same query. Greedy decoding (temperature 0)
    # makes the translation reproducible instead of resampling a different (and
    # sometimes wrong) query on every click.
    client = _FakeClient("SELECT ALL OBJECTS WHERE [word vs='nif'] GO")
    AnthropicTranslator(client=client).translate("x", FeatureReference.load())
    assert client.messages.last_kwargs["temperature"] == 0


def test_primer_documents_lexeme_pos_suffixes():
    # The model must know lex carries a part-of-speech suffix: verbs '[', nouns
    # '/', prepositions bare. Without it, it confuses <M (with) and <M/ (people).
    from shebanq_mcp.translate import _load_primer
    primer = _load_primer()
    assert "<M/" in primer and "<M" in primer
    assert "preposition" in primer.lower()


def test_build_translator_default_is_anthropic():
    t = build_translator("anthropic")
    assert isinstance(t, AnthropicTranslator)


def test_build_translator_none_returns_none():
    # The "nod to C": the server can run translation-free.
    assert build_translator("none") is None


def test_build_translator_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")
    assert build_translator() is None


def test_build_translator_unknown_provider_raises():
    with pytest.raises(ValueError):
        build_translator("bogus")


import shebanq_mcp.translate as t


def test_build_translator_uses_llm_model_env(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("LLM_MODEL", "claude-haiku-4-5")
    tr = t.build_translator()
    assert tr is not None and tr._model == "claude-haiku-4-5"


def test_build_translator_defaults_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    monkeypatch.delenv("LLM_MODEL", raising=False)
    tr = t.build_translator()
    assert tr._model == t.DEFAULT_MODEL


def test_build_translator_none_provider(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "none")
    assert t.build_translator() is None


def test_build_prompt_includes_primer_and_reference():
    from shebanq_mcp.feature_reference import FeatureReference
    p = t.build_prompt(FeatureReference.load())
    # terse output rule
    assert "ONLY the MQL" in p
    # primer content (the sequence/adjacency lesson is primer-specific)
    assert ".." in p and "first" in p and "4490" in p
    # the object-grouped v2 reference block
    assert "Object hierarchy" in p
    # quoting rule reaches the model
    assert "UNQUOTED" in p


def test_prompt_includes_morphology_features():
    from shebanq_mcp.feature_reference import FeatureReference
    p = t.build_prompt(FeatureReference.load())
    for feat in ("prs_ps", "prs_gn", "prs_nu", "pdp", "ls", "nametype"):
        assert feat in p

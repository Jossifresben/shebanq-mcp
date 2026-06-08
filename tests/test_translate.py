from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.translate import translate_to_mql


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


def test_translate_returns_mql_string():
    client = _FakeClient("SELECT ALL OBJECTS WHERE [word vs='nif'] GO")
    mql = translate_to_mql("all niphal verbs", FeatureReference.load(), client=client)
    assert mql == "SELECT ALL OBJECTS WHERE [word vs='nif'] GO"


def test_translate_injects_feature_reference_into_prompt():
    client = _FakeClient("SELECT ALL OBJECTS WHERE [word vs='nif'] GO")
    translate_to_mql("all niphal verbs", FeatureReference.load(), client=client)
    system = client.messages.last_kwargs["system"]
    assert "vs" in system and "Niphal" in system


def test_translate_strips_code_fences():
    fenced = "```\nSELECT ALL OBJECTS WHERE [word vs='nif'] GO\n```"
    client = _FakeClient(fenced)
    mql = translate_to_mql("x", FeatureReference.load(), client=client)
    assert mql.startswith("SELECT") and "```" not in mql

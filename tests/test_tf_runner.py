import pytest

from shebanq_mcp import tf_runner
from shebanq_mcp.formatter import format_results


class FakeFeature:
    def __init__(self, mapping):
        self._m = mapping

    def v(self, n):
        return self._m.get(n)


class FakeApi:
    """The slice of the TF api the runner touches: F/Fs, T, L."""

    def __init__(self, features, otypes, sections, texts, lex_up=None):
        self._features = {k: FakeFeature(v) for k, v in features.items()}
        self._features["otype"] = FakeFeature(otypes)
        self._sections = sections
        self._texts = texts
        self._lex_up = lex_up or {}

        class T:
            sectionFromNode = staticmethod(lambda n: self._sections[n])
            text = staticmethod(lambda n: self._texts[n])
        self.T = T()

        class L:
            u = staticmethod(
                lambda n, otype=None: self._lex_up.get(n, ()))
        self.L = L()

    class _F:
        pass

    @property
    def F(self):
        f = FakeApi._F()
        for name, feat in self._features.items():
            setattr(f, name, feat)
        return f

    def Fs(self, name):
        return self._features.get(name)


class FakeApp:
    def __init__(self, api, results):
        self.api = api
        self._results = results

    def search(self, template, silent="deep"):
        return self._results


@pytest.fixture(autouse=True)
def reset_app():
    tf_runner._A = None
    yield
    tf_runner._A = None


def make_app():
    api = FakeApi(
        features={
            "sp": {11: "verb", 12: "verb"},
            "vs": {11: "nif", 12: "qal"},
            "gloss": {11: "create", 12: None},
        },
        otypes={11: "word", 12: "word", 90: "lex"},
        sections={11: ("Genesis", 1, 1), 12: ("Genesis", 1, 2)},
        texts={11: "ברא", 12: "אמר"},
        lex_up={12: (90,)},
    )
    api._features["gloss"]._m[90] = "say"   # lex-level gloss for node 12
    return FakeApp(api, results=[(1, 11), (1, 12)])


def test_leaf_node_maps_to_row():
    tf_runner._A = make_app()
    res = tf_runner.run_template("clause\n  word sp=verb vs=nif")
    assert res.count == 2
    row = res.matches[0]
    assert row["id_d"] == 11
    assert (row["book"], row["chapter"], row["verse"]) == ("Genesis", "1", "1")
    assert row["text"] == "ברא"
    assert row["gloss"] == "create"
    assert row["sp"] == "verb" and row["vs"] == "nif"


def test_gloss_falls_back_to_lex_node():
    tf_runner._A = make_app()
    res = tf_runner.run_template("word sp=verb")
    assert res.matches[1]["gloss"] == "say"   # node 12 gloss came via L.u -> lex


def test_limit_caps_matches_but_not_count():
    tf_runner._A = make_app()
    res = tf_runner.run_template("word sp=verb", limit=1)
    assert res.count == 2
    assert len(res.matches) == 1


def test_rows_format_cleanly():
    tf_runner._A = make_app()
    res = tf_runner.run_template("word sp=verb")
    formatted = format_results(res.matches)
    assert formatted[0]["reference"] == "Genesis 1:1"
    assert formatted[0]["features"] == {"sp": "verb"}   # only the leaf-line features


def test_leaf_features_parsed_from_last_line():
    assert tf_runner._leaf_features(
        "clause\n  phrase function=Pred\n    word sp=verb vs=nif"
    ) == ["sp", "vs"]
    assert tf_runner._leaf_features("word") == []


def test_above_verse_leaf_does_not_crash():
    api = FakeApi(
        features={},
        otypes={5: "book"},
        sections={5: ("Genesis",)},          # book nodes give a 1-tuple
        texts={5: "..."},
    )
    tf_runner._A = FakeApp(api, results=[(5,)])
    res = tf_runner.run_template("book")
    row = res.matches[0]
    assert row["book"] == "Genesis"
    assert row["chapter"] is None and row["verse"] is None
    formatted = format_results(res.matches)
    assert formatted[0]["reference"] is None


# ---- data-backed pinned counts (CI only) -----------------------------------
# The same six counts the Emdros tests pin, on the same 2021 data. A mismatch
# here is a fork bug (template generation or version pin), never data drift.

PINNED = [
    ("word sp=verb", 73710),
    ("word sp=verb vs=nif", 4145),
    ("word lex=BR>[", 48),
    ("word sp=subs gn=f nu=pl", 5992),
    ("word vt=impv", 4306),
    ("word sp=nmpr", 33002),
]


@pytest.mark.tf
@pytest.mark.parametrize("template,expected", PINNED)
def test_pinned_counts(require_tf, template, expected):
    res = tf_runner.run_template(template, limit=5)
    assert res.count == expected
    assert len(res.matches) <= 5
    assert res.matches[0]["book"]            # references resolve


@pytest.mark.tf
def test_nested_template_runs(require_tf):
    res = tf_runner.run_template(
        "clause\n  phrase function=Pred\n    word sp=verb vs=nif", limit=3)
    assert res.count > 0
    row = res.matches[0]
    assert row["text"] and row["book"]

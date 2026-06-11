import pytest
from shebanq_mcp.runner import run_query, RunResult, _parse_get_lists, _parse_block_tree


@pytest.mark.emdros
def test_known_query_returns_matches(require_emdros, db_path):
    # BR>[ ("bara", to create) — BHSA verb lexemes carry a trailing '['.
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"
    result = run_query(mql, db_path)
    assert isinstance(result, RunResult)
    assert result.count > 0
    assert result.count == len(result.matches)
    assert "id_d" in result.matches[0]


@pytest.mark.emdros
def test_empty_result_is_honest(require_emdros, db_path):
    mql = "SELECT ALL OBJECTS WHERE [word lex='THIS_LEX_DOES_NOT_EXIST'] GO"
    result = run_query(mql, db_path)
    assert result.count == 0
    assert result.matches == []


@pytest.mark.emdros
def test_run_query_with_features_returns_values(require_emdros, db_path):
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET sp, gloss] GO"
    result = run_query(mql, db_path, features=["sp", "gloss"])
    assert result.count > 0
    first = result.matches[0]
    assert "sp" in first and "gloss" in first


# --- Harvest-loop cap (no Emdros needed: fake the env/sheaf) ---

class _FakeMO:
    def __init__(self, idx, calls):
        self.idx = idx
        self._calls = calls

    def getID_D(self):
        return self.idx

    def getFeatureAsString(self, i):
        self._calls[0] += 1            # count expensive harvest work
        return f"f{self.idx}.{i}"


class _FakeIter:
    def __init__(self, items):
        self._items = list(items)
        self._pos = 0

    def hasNext(self):
        return self._pos < len(self._items)

    def next(self):
        item = self._items[self._pos]
        self._pos += 1
        return item


class _FakeStraw:
    def __init__(self, mos):
        self._mos = mos

    def const_iterator(self):
        return _FakeIter(self._mos)


class _FakeSheaf:
    def __init__(self, straws):
        self._straws = straws

    def const_iterator(self):
        return _FakeIter(self._straws)


class _FakeEnv:
    def __init__(self, n, calls):
        mos = [_FakeMO(i, calls) for i in range(n)]
        self._sheaf = _FakeSheaf([_FakeStraw(mos)])

    def executeString(self, *a):
        return True

    def getSheaf(self):
        return self._sheaf


def test_run_query_caps_harvest_but_counts_all(monkeypatch):
    import shebanq_mcp.runner as runner
    calls = [0]
    monkeypatch.setattr(runner, "_make_env", lambda db: _FakeEnv(10, calls))
    res = run_query("Q GO", "x.db", features=["gloss"], limit=3)
    assert res.count == 10            # honest total
    assert len(res.matches) == 3      # only the first 3 harvested
    assert calls[0] == 3              # getFeatureAsString NOT called past the cap


def test_run_query_no_limit_harvests_all(monkeypatch):
    import shebanq_mcp.runner as runner
    calls = [0]
    monkeypatch.setattr(runner, "_make_env", lambda db: _FakeEnv(5, calls))
    res = run_query("Q GO", "x.db", features=["gloss"])   # limit=None
    assert res.count == 5 and len(res.matches) == 5 and calls[0] == 5


# --- Nested verse-reference tests (no Emdros needed) ---


def test_parse_get_lists_flat():
    mql = "SELECT ALL OBJECTS WHERE [word sp=verb GET sp, gloss] GO"
    assert _parse_get_lists(mql) == [["sp", "gloss"]]


def test_parse_get_lists_nested_in_order():
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[word lex='BR>[' GET g_word_utf8, gloss]] GO")
    assert _parse_get_lists(mql) == [["book", "chapter", "verse"],
                                     ["g_word_utf8", "gloss"]]


def test_parse_get_lists_none():
    assert _parse_get_lists("SELECT ALL OBJECTS WHERE [word sp=verb] GO") == []


class _NMo:
    """A matched object with named-by-index features and an optional inner sheaf."""
    def __init__(self, idx, feats, inner=None):
        self.idx, self._feats, self._inner = idx, feats, inner

    def getID_D(self):
        return self.idx

    def getFeatureAsString(self, i):
        return self._feats[i]

    def getSheaf(self):
        return self._inner


def test_run_query_nested_attaches_verse_reference(monkeypatch):
    import shebanq_mcp.runner as runner
    words = [_NMo(101, ["בָּרָא", "create"]), _NMo(102, ["יִּבְרָא", "create"])]
    word_sheaf = _FakeSheaf([_FakeStraw(words)])
    verse = _NMo(1, ["Genesis", "1", "1"], word_sheaf)
    verse_sheaf = _FakeSheaf([_FakeStraw([verse])])

    class _Env:
        def executeString(self, *a):
            return True

        def getSheaf(self):
            return verse_sheaf

    monkeypatch.setattr(runner, "_make_env", lambda db: _Env())
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[word lex='BR>[' GET g_word_utf8, gloss]] GO")
    res = run_query(mql, "x.db")
    assert res.count == 2                       # leaf words, NOT the 1 verse
    r0 = res.matches[0]
    assert r0["id_d"] == 101
    assert r0["g_word_utf8"] == "בָּרָא" and r0["gloss"] == "create"
    assert r0["book"] == "Genesis" and r0["chapter"] == "1" and r0["verse"] == "1"


def test_run_query_nested_respects_limit(monkeypatch):
    import shebanq_mcp.runner as runner
    words = [_NMo(200 + i, ["w%d" % i, "g"]) for i in range(5)]
    verse = _NMo(1, ["Exodus", "2", "3"], _FakeSheaf([_FakeStraw(words)]))
    verse_sheaf = _FakeSheaf([_FakeStraw([verse])])

    class _Env:
        def executeString(self, *a):
            return True

        def getSheaf(self):
            return verse_sheaf

    monkeypatch.setattr(runner, "_make_env", lambda db: _Env())
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[word GET g_word_utf8, gloss]] GO")
    res = run_query(mql, "x.db", limit=2)
    assert res.count == 5 and len(res.matches) == 2   # all counted, 2 harvested
    assert [m["id_d"] for m in res.matches] == [200, 201]


def test_run_query_nested_isolates_reference_per_verse(monkeypatch):
    import shebanq_mcp.runner as runner
    v1_words = _FakeSheaf([_FakeStraw([_NMo(11, ["w1", "g1"])])])
    v2_words = _FakeSheaf([_FakeStraw([_NMo(22, ["w2", "g2"])])])
    v1 = _NMo(1, ["Genesis", "1", "1"], v1_words)
    v2 = _NMo(2, ["Exodus", "2", "2"], v2_words)
    verse_sheaf = _FakeSheaf([_FakeStraw([v1, v2])])

    class _Env:
        def executeString(self, *a):
            return True

        def getSheaf(self):
            return verse_sheaf

    monkeypatch.setattr(runner, "_make_env", lambda db: _Env())
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[word GET g_word_utf8, gloss]] GO")
    res = run_query(mql, "x.db")
    assert res.count == 2
    by_id = {r["id_d"]: r for r in res.matches}
    assert by_id[11]["book"] == "Genesis" and by_id[11]["verse"] == "1"
    assert by_id[22]["book"] == "Exodus" and by_id[22]["verse"] == "2"


# --- Emdros-backed nested verse-reference tests (require live DB) ---


@pytest.mark.emdros
def test_nested_bara_has_reference(require_emdros, db_path):
    # The first occurrence of the lexeme BR>[ ("bara") is Genesis 1:1.
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[word lex='BR>[' GET g_word_utf8, gloss]] GO")
    result = run_query(mql, db_path)
    assert result.count == 48                       # leaf words, same as flat
    first = result.matches[0]
    assert first["book"] == "Genesis"
    assert first["chapter"] == "1" and first["verse"] == "1"


@pytest.mark.emdros
def test_flat_bara_unchanged(require_emdros, db_path):
    mql = "SELECT ALL OBJECTS WHERE [word lex='BR>['] GO"
    result = run_query(mql, db_path)
    assert result.count == 48 and result.matches[0].get("book") is None


# --- Structural nesting depth tests ---


def test_nesting_depth_flat_with_bracket_in_literal():
    from shebanq_mcp.runner import _nesting_depth
    # the '[' inside the lexeme 'BR>[' must NOT count as nesting
    assert _nesting_depth("SELECT ALL OBJECTS WHERE [word lex='BR>['] GO") == 1


def test_nesting_depth_nested():
    from shebanq_mcp.runner import _nesting_depth
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[word lex='BR>[' GET g_word_utf8, gloss]] GO")
    assert _nesting_depth(mql) == 2


def test_run_query_nested_without_inner_get_still_descends(monkeypatch):
    import shebanq_mcp.runner as runner
    words = [_NMo(301, []), _NMo(302, [])]     # inner word block GETs nothing
    verse = _NMo(1, ["Genesis", "1", "1"], _FakeSheaf([_FakeStraw(words)]))
    verse_sheaf = _FakeSheaf([_FakeStraw([verse])])

    class _Env:
        def executeString(self, *a):
            return True

        def getSheaf(self):
            return verse_sheaf

    monkeypatch.setattr(runner, "_make_env", lambda db: _Env())
    mql = "SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse [word sp=verb]] GO"
    res = run_query(mql, "x.db")
    assert res.count == 2                       # the 2 words, NOT 1 verse
    assert res.matches[0]["book"] == "Genesis" and res.matches[0]["verse"] == "1"
    assert "id_d" in res.matches[0]


# --- Block-aware GET parsing and inner-only GET crash fix ---


def _gets(node):
    """Flatten a block tree to nested [get, [children...]] lists for assertions."""
    return [node["get"], [_gets(c) for c in node["children"]]]


def test_parse_block_tree_assigns_get_to_owning_block():
    tree = _parse_block_tree(
        "SELECT ALL OBJECTS WHERE [clause typ=WayX [phrase function=Subj GET function]] GO"
    )
    assert _gets(tree) == [[], [[[], [[["function"], []]]]]]
    tree = _parse_block_tree(
        "SELECT ALL OBJECTS WHERE [clause GET typ [phrase GET function [word GET lex, gloss]]] GO"
    )
    assert _gets(tree) == [[], [[["typ"], [[["function"], [[["lex", "gloss"], []]]]]]]]
    # '[' inside a string literal must not shift levels
    tree = _parse_block_tree(
        "SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse [word lex='BR>[' GET g_word_utf8, gloss]] GO"
    )
    assert _gets(tree) == [[], [[["book", "chapter", "verse"],
                                [[["g_word_utf8", "gloss"], []]]]]]


def test_parse_block_tree_sibling_gets_stay_separate():
    """Two sibling blocks at the same depth each keep their OWN GET list; the old
    by-depth parse merged them, over-indexing getFeatureAsString in the harvest
    (a SIGABRT in the real Emdros C layer)."""
    tree = _parse_block_tree(
        "SELECT ALL OBJECTS WHERE [clause "
        "[phrase function=Pred [word sp=verb GET g_word_utf8, gloss]] .. "
        "[phrase function=Cmpl [word sp=prep GET lex]]] GO"
    )
    clause = tree["children"][0]
    pred_word = clause["children"][0]["children"][0]
    cmpl_word = clause["children"][1]["children"][0]
    assert pred_word["get"] == ["g_word_utf8", "gloss"]
    assert cmpl_word["get"] == ["lex"]


def test_run_query_nested_get_only_on_inner_never_touches_outer(monkeypatch):
    import shebanq_mcp.runner as runner

    class _Boom:  # the outer (clause) object retrieved NO features
        def __init__(self, idx, inner):
            self.idx, self._inner = idx, inner

        def getID_D(self):
            return self.idx

        def getFeatureAsString(self, i):
            raise AssertionError("outer object has no GET features; must not be read")

        def getSheaf(self):
            return self._inner

    phrases = [_NMo(11, ["Subj"]), _NMo(12, ["Subj"])]      # inner phrase: GET function
    clause = _Boom(1, _FakeSheaf([_FakeStraw(phrases)]))

    class _Env:
        def executeString(self, *a):
            return True

        def getSheaf(self):
            return _FakeSheaf([_FakeStraw([clause])])

    monkeypatch.setattr(runner, "_make_env", lambda db: _Env())
    mql = "SELECT ALL OBJECTS WHERE [clause typ=WayX [phrase function=Subj GET function]] GO"
    res = run_query(mql, "x.db")
    assert res.count == 2
    assert res.matches[0]["function"] == "Subj" and "id_d" in res.matches[0]


def test_run_query_nested_skips_none_sheaf_siblings(monkeypatch):
    """An asymmetric nest where one sibling block has no inner query (e.g.
    [phrase function=Conj] beside [phrase function=Objc [word ...]]) yields a None
    inner sheaf for that sibling. The harvest must skip it, not crash."""
    import shebanq_mcp.runner as runner
    word = _NMo(101, ["דָּבָר", "word"])
    word_sheaf = _FakeSheaf([_FakeStraw([word])])
    conj = _NMo(201, [], None)                  # no inner block -> getSheaf() is None
    objc = _NMo(202, [], word_sheaf)
    phrase_sheaf = _FakeSheaf([_FakeStraw([conj, objc])])
    clause = _NMo(301, [], phrase_sheaf)
    verse = _NMo(1, ["Genesis", "1", "1"], _FakeSheaf([_FakeStraw([clause])]))
    verse_sheaf = _FakeSheaf([_FakeStraw([verse])])

    class _Env:
        def executeString(self, *a):
            return True

        def getSheaf(self):
            return verse_sheaf

    monkeypatch.setattr(runner, "_make_env", lambda db: _Env())
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[clause typ=Ellp [phrase first function=Conj] .. "
           "[phrase function=Objc [word GET g_word_utf8, gloss]]]] GO")
    res = run_query(mql, "x.db")
    assert res.count == 1                        # the one object word; conj skipped
    r = res.matches[0]
    assert r["id_d"] == 101 and r["g_word_utf8"] == "דָּבָר"
    assert r["book"] == "Genesis" and r["verse"] == "1"


# --- Sibling leaf blocks that each carry their own GET (worker-crash fix) ---

# The translator generates this shape for verb+complement questions ("spoke
# with"): a Pred word and a Cmpl word, sibling leaf blocks, each with its own
# GET. The fakes raise IndexError on an out-of-range feature index, modelling
# the real failure: Emdros aborts the worker process (SIGABRT, exit -6).

_SPOKE_WITH_MQL = """SELECT ALL OBJECTS WHERE
  [verse GET book, chapter, verse
    [clause
      [phrase function=Pred
        [word sp=verb AND vt=wayq AND lex='DBR[' GET g_word_utf8, gloss]
      ]
      ..
      [phrase function=Cmpl
        [word sp=prep AND lex='<M' GET g_word_utf8, gloss]
      ]
    ]
  ]
GO"""


def _spoke_with_env(pred_feats, cmpl_feats):
    pred_word = _NMo(101, pred_feats)
    cmpl_word = _NMo(102, cmpl_feats)
    pred_phrase = _NMo(11, [], _FakeSheaf([_FakeStraw([pred_word])]))
    cmpl_phrase = _NMo(12, [], _FakeSheaf([_FakeStraw([cmpl_word])]))
    clause = _NMo(21, [], _FakeSheaf([_FakeStraw([pred_phrase, cmpl_phrase])]))
    verse = _NMo(1, ["Genesis", "1", "1"],
                 _FakeSheaf([_FakeStraw([clause])]))

    class _Env:
        def executeString(self, *a):
            return True

        def getSheaf(self):
            return _FakeSheaf([_FakeStraw([verse])])

    return _Env()


def test_run_query_sibling_get_blocks_do_not_overrun_features(monkeypatch):
    import shebanq_mcp.runner as runner
    env = _spoke_with_env(["וַיְדַבֵּר", "speak"], ["עִם", "with"])
    monkeypatch.setattr(runner, "_make_env", lambda db: env)
    res = run_query(_SPOKE_WITH_MQL, "x.db")
    assert res.count == 2                       # the Pred word and the Cmpl word
    by_id = {r["id_d"]: r for r in res.matches}
    assert by_id[101]["g_word_utf8"] == "וַיְדַבֵּר" and by_id[101]["gloss"] == "speak"
    assert by_id[102]["g_word_utf8"] == "עִם" and by_id[102]["gloss"] == "with"
    assert by_id[101]["book"] == "Genesis" and by_id[102]["verse"] == "1"


def test_run_query_sibling_get_blocks_with_different_features(monkeypatch):
    import shebanq_mcp.runner as runner
    env = _spoke_with_env(["וַיְדַבֵּר", "speak"], ["<M"])
    monkeypatch.setattr(runner, "_make_env", lambda db: env)
    mql = _SPOKE_WITH_MQL.replace(
        "[word sp=prep AND lex='<M' GET g_word_utf8, gloss]",
        "[word sp=prep AND lex='<M' GET lex]")
    res = run_query(mql, "x.db")
    assert res.count == 2
    by_id = {r["id_d"]: r for r in res.matches}
    assert by_id[101]["g_word_utf8"] == "וַיְדַבֵּר"
    assert by_id[102]["lex"] == "<M" and "g_word_utf8" not in by_id[102]


@pytest.mark.emdros
def test_sibling_get_query_survives_real_engine(require_emdros, db_path):
    # The exact user query that killed the worker (SIGABRT) in v0.2.0.
    result = run_query(_SPOKE_WITH_MQL, db_path)
    assert isinstance(result.count, int)
    for row in result.matches:
        assert "book" in row and "g_word_utf8" in row

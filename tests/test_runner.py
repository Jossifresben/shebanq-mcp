import pytest
from shebanq_mcp.runner import run_query, RunResult


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

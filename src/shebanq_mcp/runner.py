import re
from dataclasses import dataclass, field

# A GET clause lists the features to return; it is always terminated by the
# opening bracket of an inner block ('[') or the closing bracket of its own
# block (']'). Capturing them left-to-right yields the per-nesting-level lists
# in outermost-first order.
_GET_CLAUSE = re.compile(r"\bGET\s+([A-Za-z0-9_,\s]+?)\s*(?=[\[\]])", re.IGNORECASE)

# Verse-level features that form a citation. The runner propagates these from a
# containing object down onto each leaf row; formatter._reference renders them.
_REF_KEYS = ("book", "chapter", "verse")


def _parse_get_lists(mql: str) -> list[list[str]]:
    return [[f.strip() for f in clause.split(",") if f.strip()]
            for clause in _GET_CLAUSE.findall(mql)]


def _parse_get_by_level(mql: str) -> dict:
    """Map each object-block nesting LEVEL to its own GET features, assigning a
    GET clause to the block it is syntactically inside (by bracket depth) rather
    than by textual order. So a query that GETs only on an inner block does not
    misalign its features onto the outer object (which retrieved nothing).
    Robust to '[' inside string literals (e.g. the lexeme 'BR>[')."""
    stripped = re.sub(r"'[^']*'", "", mql)
    out: dict = {}
    depth = 0
    for m in re.finditer(r"\[|\]|\bGET\s+([A-Za-z0-9_,\s]+?)(?=[\[\]])", stripped):
        tok = m.group(0)
        if tok == "[":
            depth += 1
        elif tok == "]":
            depth -= 1
        else:                       # GET clause: belongs to the block at this depth
            out.setdefault(depth - 1, []).extend(
                f.strip() for f in m.group(1).split(",") if f.strip())
    return out


def _nesting_depth(mql: str) -> int:
    """Structural object-block nesting depth, robust to '[' inside string
    literals (e.g. the lexeme 'BR>['). 1 = a flat single-object query, 2 = a
    verse-over-word nest."""
    stripped = re.sub(r"'[^']*'", "", mql)
    depth = top = 0
    for ch in stripped:
        if ch == "[":
            depth += 1
            top = max(top, depth)
        elif ch == "]":
            depth -= 1
    return top


def _harvest_nested(sheaf, get_by_level, depth, ctx, matches, limit, leaf_depth):
    names = get_by_level.get(depth, [])
    is_leaf = depth >= leaf_depth
    total = 0
    it = sheaf.const_iterator()
    while it.hasNext():
        sit = it.next().const_iterator()
        while sit.hasNext():
            mo = sit.next()
            feats = {n: mo.getFeatureAsString(i) for i, n in enumerate(names)}
            if not is_leaf:
                child = dict(ctx)
                for k in _REF_KEYS:
                    if k in feats:
                        child[k] = feats[k]
                total += _harvest_nested(mo.getSheaf(), get_by_level, depth + 1,
                                         child, matches, limit, leaf_depth)
            else:
                total += 1
                if limit is not None and len(matches) >= limit:
                    continue
                row = {"id_d": mo.getID_D(), **feats}
                for k in _REF_KEYS:
                    if k in ctx:
                        row[k] = ctx[k]
                matches.append(row)
    return total


@dataclass
class RunResult:
    count: int
    matches: list[dict] = field(default_factory=list)


# The SWIG Python module ships under different names across Emdros builds:
# `EmdrosPy3` (3.9.0 source build), `EmdrosPy` (historical), or `emdros`.
_EMDROS_MODULE_NAMES = ("emdros", "EmdrosPy3", "EmdrosPy")


def _import_emdros():
    last_err: ImportError | None = None
    for name in _EMDROS_MODULE_NAMES:
        try:
            return __import__(name)
        except ImportError as exc:
            last_err = exc
    raise last_err if last_err else ImportError("no Emdros module found")


def _make_env(db_path: str):
    emdros = _import_emdros()  # lazy: only needed when actually executing a query
    # Signature: (output_kind, charset, hostname, user, password, initial_db,
    # backend). For SQLite the database file path is the initial_db.
    return emdros.EmdrosEnv(
        emdros.kOKConsole,
        emdros.kCSUTF8,
        "", "", "", db_path,
        emdros.kSQLite3,
    )


def run_query(mql: str, db_path: str, features: list[str] | None = None,
              limit: int | None = None) -> RunResult:
    """Run an MQL query. `count` is the true total of matched leaf objects;
    `matches` holds the harvested rows (capped at `limit`). A nested
    verse-over-word query attaches the containing verse's book/chapter/verse to
    each word row; a flat query harvests `features` from each matched object as
    before."""
    features = features or []
    env = _make_env(db_path)
    if not env.executeString(mql, True, False, True):
        raise RuntimeError(f"Emdros error: {env.getCompilerError()}")
    sheaf = env.getSheaf()

    levels = _nesting_depth(mql)
    if levels > 1:                                  # nested: harvest leaf rows
        get_by_level = _parse_get_by_level(mql)
        matches: list[dict] = []
        total = _harvest_nested(sheaf, get_by_level, 0, {}, matches, limit, levels - 1)
        return RunResult(count=total, matches=matches)

    matches = []                                    # flat: existing behaviour
    total = 0
    it = sheaf.const_iterator()
    while it.hasNext():
        straw = it.next()
        sit = straw.const_iterator()
        while sit.hasNext():
            mo = sit.next()
            total += 1
            if limit is not None and len(matches) >= limit:
                continue  # count it, but skip the expensive feature harvest
            row = {"id_d": mo.getID_D()}
            for i, feat in enumerate(features):
                row[feat] = mo.getFeatureAsString(i)
            matches.append(row)
    return RunResult(count=total, matches=matches)

from dataclasses import dataclass, field


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
    """Run an MQL query. `count` is the true total of matched objects; `matches`
    holds the harvested rows. When `limit` is set, only the first `limit` rows
    are harvested (the rest are counted but not materialized), so a query that
    matches hundreds of thousands of objects does not build a giant list. With
    `limit=None` every match is harvested (count == len(matches))."""
    features = features or []
    env = _make_env(db_path)
    ok = env.executeString(mql, True, False, True)
    if not ok:
        raise RuntimeError(f"Emdros error: {env.getCompilerError()}")

    sheaf = env.getSheaf()
    matches: list[dict] = []
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

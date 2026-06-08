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
    return emdros.EmdrosEnv(
        emdros.kOKConsole,
        emdros.kCSUTF8,
        "", "", db_path,
        emdros.kSQLite3,
    )


def run_query(mql: str, db_path: str, features: list[str] | None = None) -> RunResult:
    features = features or []
    env = _make_env(db_path)
    ok = env.executeString(mql, True, False, True)
    if not ok:
        raise RuntimeError(f"Emdros error: {env.getCompilerError()}")

    sheaf = env.getSheaf()
    matches: list[dict] = []
    it = sheaf.const_iterator()
    while it.hasNext():
        straw = it.next()
        sit = straw.const_iterator()
        while sit.hasNext():
            mo = sit.next()
            row = {"id_d": mo.getID_D(), "monad": mo.getFirst()}
            for i, feat in enumerate(features):
                row[feat] = mo.getFeatureAsString(i)
            matches.append(row)
    return RunResult(count=len(matches), matches=matches)

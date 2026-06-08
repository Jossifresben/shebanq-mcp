import os
import shutil
import pytest

DB_PATH = os.environ.get("BHSA_SQLITE", "data/bhsa.sqlite3")


def _emdros_available() -> bool:
    if shutil.which("mql") is None and not os.path.exists(DB_PATH):
        return False
    import importlib
    found = False
    for name in ("emdros", "EmdrosPy3", "EmdrosPy"):
        try:
            importlib.import_module(name)
            found = True
            break
        except ImportError:
            continue
    if not found:
        return False
    return os.path.exists(DB_PATH)


@pytest.fixture
def db_path() -> str:
    return DB_PATH


@pytest.fixture(autouse=False)
def require_emdros():
    if not _emdros_available():
        pytest.skip("Emdros binding or BHSA database not available")

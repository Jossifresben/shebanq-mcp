"""Introspect a BHSA Emdros database: object types, their features and types,
and the enumeration names. Prints the engine's human-readable tables.

Run where Emdros + the DB are available (e.g. CI):
    python scripts/dump_schema.py data/bhsa.sqlite3

The output is the authoritative source for which features exist on each object
type and which are enumerations (enum-typed features must be queried UNQUOTED in
MQL, string features quoted).
"""
import sys

from shebanq_mcp.runner import _import_emdros

DB = sys.argv[1] if len(sys.argv) > 1 else "data/bhsa.sqlite3"

emdros = _import_emdros()
env = emdros.EmdrosEnv(
    emdros.kOKConsole, emdros.kCSUTF8, "", "", "", DB, emdros.kSQLite3,
)

QUERIES = [
    "SELECT OBJECT TYPES GO",
    "SELECT FEATURES FROM OBJECT TYPE [word] GO",
    "SELECT FEATURES FROM OBJECT TYPE [phrase] GO",
    "SELECT FEATURES FROM OBJECT TYPE [clause] GO",
    "SELECT FEATURES FROM OBJECT TYPE [sentence] GO",
    "SELECT ENUMERATIONS GO",
]

for q in QUERIES:
    print(f"\n===== {q} =====", flush=True)
    ok = env.executeString(q, True, True, True)  # bResult, bPrintResult, bReportError
    if not ok:
        print("ERROR:", env.getCompilerError(), flush=True)

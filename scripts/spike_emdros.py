"""Spike: confirm the Emdros Python binding API against the built BHSA db.

Run: python scripts/spike_emdros.py data/bhsa.sqlite3
Prints the number of matches for a tiny known query and the first object id.
This file documents the exact API the runner depends on.
"""
import sys
import emdros

DB = sys.argv[1] if len(sys.argv) > 1 else "data/bhsa.sqlite3"

env = emdros.EmdrosEnv(
    emdros.kOKConsole, emdros.kCSUTF8,
    "", "", DB, emdros.BACKEND_SQLITE3,
)

QUERY = "SELECT ALL OBJECTS WHERE [word lex='BR>' ] GO"
ok = env.executeString(QUERY, True, False, True)
if not ok:
    print("compiler error:", env.getCompilerError())
    sys.exit(1)

sheaf = env.getSheaf()
count = 0
first_id = None
it = sheaf.const_iterator()
while it.hasNext():
    straw = it.next()
    sit = straw.const_iterator()
    while sit.hasNext():
        mo = sit.next()
        if first_id is None:
            first_id = mo.getID_D()
        count += 1

print("matches:", count, "first id:", first_id)

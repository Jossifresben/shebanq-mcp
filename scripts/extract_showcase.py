"""Extract real showcase data from the BHSA database.

Runs each featured search via the tested run_query, collecting the total count
and up to SAMPLE_N real sample rows (Hebrew word + English gloss). Prints the
showcase JSON to stdout. Run in CI where Emdros + the DB exist:

    python scripts/extract_showcase.py data/bhsa.sqlite3 > demo/showcase.json
"""
import json
import sys

from shebanq_mcp.runner import run_query, _import_emdros
from shebanq_mcp.server import _wrap_in_verse

DB = sys.argv[1] if len(sys.argv) > 1 else "data/bhsa.sqlite3"
SAMPLE_N = 5

SEARCHES = [
    {
        "id": "niphal-verbs",
        "question": "Find all Niphal verbs",
        "mql": "SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif GET g_word_utf8, gloss] GO",
        "where": "sp=verb AND vs=nif",
    },
    {
        "id": "bara-create",
        "question": "Where does the verb בָּרָא (bara, 'to create') occur?",
        "mql": "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO",
        "where": "lex='BR>['",
    },
    {
        "id": "feminine-plural-nouns",
        "question": "Find feminine plural nouns",
        "mql": "SELECT ALL OBJECTS WHERE [word sp=subs AND gn=f AND nu=pl GET g_word_utf8, gloss] GO",
        "where": "sp=subs AND gn=f AND nu=pl",
    },
    {
        "id": "imperative-verbs",
        "question": "Find all imperative verbs",
        "mql": "SELECT ALL OBJECTS WHERE [word vt=impv GET g_word_utf8, gloss] GO",
        "where": "vt=impv",
    },
    {
        "id": "proper-nouns",
        "question": "Find all proper nouns (names)",
        "mql": "SELECT ALL OBJECTS WHERE [word sp=nmpr GET g_word_utf8, gloss] GO",
        "where": "sp=nmpr",
    },
]


def _samples_with_refs(inner_where: str, db: str, n: int) -> list | None:
    """Run a verse>word nested query and harvest up to n samples with verse
    references. Returns None on any failure (caller falls back to flat samples).

    The verse object carries book (enum book name), chapter (int) and verse
    (int); the inner word carries g_word_utf8 and gloss.
    """
    try:
        emdros = _import_emdros()
        env = emdros.EmdrosEnv(
            emdros.kOKConsole, emdros.kCSUTF8, "", "", "", db, emdros.kSQLite3,
        )
        mql = (
            "SELECT ALL OBJECTS WHERE "
            "[verse GET book, chapter, verse "
            "  [word " + inner_where + " GET g_word_utf8, gloss] "
            "] GO"
        )
        if not env.executeString(mql, True, False, True):
            return None
        out: list = []
        sheaf = env.getSheaf()
        it = sheaf.const_iterator()
        while it.hasNext() and len(out) < n:
            straw = it.next()
            sit = straw.const_iterator()
            while sit.hasNext() and len(out) < n:
                vmo = sit.next()
                ref = (
                    f"{vmo.getFeatureAsString(0)} "
                    f"{vmo.getFeatureAsString(1)}:{vmo.getFeatureAsString(2)}"
                )
                inner = vmo.getSheaf()
                iit = inner.const_iterator()
                while iit.hasNext() and len(out) < n:
                    istraw = iit.next()
                    wit = istraw.const_iterator()
                    while wit.hasNext() and len(out) < n:
                        wmo = wit.next()
                        out.append({
                            "hebrew": wmo.getFeatureAsString(0),
                            "gloss": wmo.getFeatureAsString(1),
                            "reference": ref,
                        })
        return out or None
    except Exception:
        return None


def extract(db: str) -> dict:
    searches = []
    for s in SEARCHES:
        res = run_query(s["mql"], db, features=["g_word_utf8", "gloss"])
        samples = _samples_with_refs(s["where"], db, SAMPLE_N)
        if samples is None:
            samples = [
                {
                    "hebrew": m.get("g_word_utf8", ""),
                    "gloss": m.get("gloss", ""),
                    "reference": None,
                }
                for m in res.matches[:SAMPLE_N]
            ]
        searches.append({
            "id": s["id"],
            "question": s["question"],
            "mql": _wrap_in_verse(s["mql"]),
            "count": res.count,
            "samples": samples,
        })
    return {"version": "bhsa-2021", "searches": searches}


if __name__ == "__main__":
    print(json.dumps(extract(DB), ensure_ascii=False, indent=2))

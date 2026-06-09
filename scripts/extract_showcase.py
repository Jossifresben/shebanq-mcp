"""Extract real showcase data from the BHSA database.

Runs each featured search via the tested run_query, collecting the total count
and up to SAMPLE_N real sample rows (Hebrew word + English gloss). Prints the
showcase JSON to stdout. Run in CI where Emdros + the DB exist:

    python scripts/extract_showcase.py data/bhsa.sqlite3 > demo/showcase.json
"""
import json
import sys

from shebanq_mcp.runner import run_query

DB = sys.argv[1] if len(sys.argv) > 1 else "data/bhsa.sqlite3"
SAMPLE_N = 5

SEARCHES = [
    {
        "id": "niphal-verbs",
        "question": "Find all Niphal verbs in the Hebrew Bible.",
        "mql": "SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif GET g_word_utf8, gloss] GO",
    },
    {
        "id": "bara-create",
        "question": "Where does the verb בָּרָא (bara, 'to create') occur?",
        "mql": "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO",
    },
    {
        "id": "feminine-plural-nouns",
        "question": "Find feminine plural nouns.",
        "mql": "SELECT ALL OBJECTS WHERE [word sp=subs AND gn=f AND nu=pl GET g_word_utf8, gloss] GO",
    },
    {
        "id": "imperative-verbs",
        "question": "Find all imperative verbs.",
        "mql": "SELECT ALL OBJECTS WHERE [word vt=impv GET g_word_utf8, gloss] GO",
    },
    {
        "id": "proper-nouns",
        "question": "Find all proper nouns (names).",
        "mql": "SELECT ALL OBJECTS WHERE [word sp=nmpr GET g_word_utf8, gloss] GO",
    },
]


def extract(db: str) -> dict:
    searches = []
    for s in SEARCHES:
        res = run_query(s["mql"], db, features=["g_word_utf8", "gloss"])
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
            "mql": s["mql"],
            "count": res.count,
            "samples": samples,
        })
    return {"version": "bhsa-2021", "searches": searches}


if __name__ == "__main__":
    print(json.dumps(extract(DB), ensure_ascii=False, indent=2))

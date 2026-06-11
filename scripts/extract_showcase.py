"""Extract real showcase data from the BHSA database.

Runs each featured search via the tested run_query, collecting the total count
and up to SAMPLE_N real sample rows (Hebrew word + gloss + verse reference). Every
query is verse-wrapped and drills down to [word GET g_word_utf8, gloss], so
run_query returns word rows that already carry book/chapter/verse. Prints the
showcase JSON to stdout. Run in CI where Emdros + the DB exist:

    python scripts/extract_showcase.py data/bhsa.sqlite3 > demo/showcase.json
"""
import json
import sys

from shebanq_mcp.runner import run_query

DB = sys.argv[1] if len(sys.argv) > 1 else "data/bhsa.sqlite3"
SAMPLE_N = 5
_V = "GET book, chapter, verse"   # the verse wrapper that carries the reference

# Two plain word-level classics (no verse wrapper, so the rows show Hebrew + gloss
# with no reference), then clause/phrase-structure searches that show off the
# curriculum. The structural ones verse-wrap and drill to [word ...] so their rows
# carry a real reference (a bare clause query has no single word to display).
SEARCHES = [
    {"id": "bara-create",
     "question": "Where does the verb בָּרָא (bara, to create) occur?",
     "mql": "SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss] GO"},
    {"id": "niphal-verbs",
     "question": "Find all Niphal verbs",
     "mql": "SELECT ALL OBJECTS WHERE "
            "[word sp=verb AND vs=nif GET g_word_utf8, gloss] GO"},
    {"id": "ellipsis-conj-object",
     "question": "Object words in ellipsis clauses that begin with a conjunction",
     "mql": f"SELECT ALL OBJECTS WHERE [verse {_V} "
            "[clause typ=Ellp [phrase first function=Conj] .. "
            "[phrase function=Objc [word GET g_word_utf8, gloss]]]] GO"},
    {"id": "nominal-clause-subjects",
     "question": "Subjects of verbless (nominal) clauses",
     "mql": f"SELECT ALL OBJECTS WHERE [verse {_V} "
            "[clause typ=NmCl [phrase function=Subj "
            "[word GET g_word_utf8, gloss]]]] GO"},
    {"id": "wayyiqtol-objects",
     "question": "Objects of the verb in narrative (wayyiqtol) clauses",
     "mql": f"SELECT ALL OBJECTS WHERE [verse {_V} "
            "[clause typ=WayX [phrase function=Objc "
            "[word GET g_word_utf8, gloss]]]] GO"},
    {"id": "construct-chain-nouns",
     "question": "Nouns in construct chains (the genitive relation)",
     "mql": f"SELECT ALL OBJECTS WHERE [verse {_V} "
            "[phrase typ=NP [subphrase rela=rec "
            "[word GET g_word_utf8, gloss]]]] GO"},
]


def _reference(m: dict) -> str | None:
    if m.get("book") and m.get("chapter") and m.get("verse"):
        return f"{m['book']} {m['chapter']}:{m['verse']}"
    return None


def extract(db: str) -> dict:
    searches = []
    for s in SEARCHES:
        # features are used by the flat path (the bare word queries); the nested
        # path ignores them and harvests from the query's own GET clauses.
        res = run_query(s["mql"], db, features=["g_word_utf8", "gloss"],
                        limit=SAMPLE_N)
        samples = [
            {"hebrew": m.get("g_word_utf8", ""), "gloss": m.get("gloss", ""),
             "reference": _reference(m)}
            for m in res.matches
        ]
        searches.append({
            "id": s["id"], "question": s["question"], "mql": s["mql"],
            "count": res.count, "samples": samples,
        })
    return {"version": "bhsa-2021", "searches": searches}


if __name__ == "__main__":
    print(json.dumps(extract(DB), ensure_ascii=False, indent=2))

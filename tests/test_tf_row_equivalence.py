"""Row-level cross-engine equivalence: the strongest form of the Rosetta
guarantee. Counts agreeing could in principle hide two different result
sets of equal size; these tests compare the FULL multiset of
(book, chapter, verse, surface form) rows from both engines. This is the
exact property the two-box UI design rests on: the displayed TF template,
derived deterministically from the executed MQL, would return the same
rows if run. Runs only where BOTH engines are available (the emdros CI
job, which also installs TF)."""
import pytest

from shebanq_mcp import tf_runner
from shebanq_mcp.feature_reference import FeatureReference
from shebanq_mcp.mql_to_tf import mql_to_tf
from shebanq_mcp.runner import run_query

# Word-level constraints; each becomes a verse-wrapped MQL (so Emdros rows
# carry book/chapter/verse) and, via the converter, a verse/word template.
CONSTRAINTS = [
    "lex='BR>['",                       # bara, 48 rows
    "sp=verb AND vs=nif",               # Niphal verbs, 4145 rows
    "sp=subs AND gn=f AND nu=pl",       # feminine plural nouns, 5992 rows
    "vt=impv",                          # imperatives, 4306 rows
    "prs_ps=p3 AND prs_gn=m AND prs_nu=sg",   # 3ms suffixes, 13754 rows
]


def _emdros_rows(mql, db_path):
    res = run_query(mql, db_path, [])
    return sorted((r["book"], str(r["chapter"]), str(r["verse"]),
                   r["g_word_utf8"]) for r in res.matches)


def _english_to_native():
    """TF's section API serves English book names (1_Samuel); the Emdros dump
    carries the ETCBC native names (Samuel_I). Both live in the TF data, so
    the bridge table comes from the corpus itself, not from hand-keeping."""
    api = tf_runner.warm().api
    return {api.T.sectionFromNode(n)[0]: api.F.book.v(n)
            for n in api.F.otype.s("book")}


def _tf_rows(template):
    res = tf_runner.run_template(template, features=["g_word_utf8"])
    to_native = _english_to_native()
    return sorted((to_native[r["book"]], str(r["chapter"]), str(r["verse"]),
                   r["g_word_utf8"]) for r in res.matches)


@pytest.mark.tf
@pytest.mark.emdros
@pytest.mark.parametrize("constraint", CONSTRAINTS)
def test_row_sets_identical(require_emdros, require_tf, db_path, constraint):
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           f"[word {constraint} GET g_word_utf8]] GO")
    template = mql_to_tf(mql, FeatureReference.load()).text
    emdros = _emdros_rows(mql, db_path)
    tf = _tf_rows(template)
    assert len(emdros) == len(tf), (len(emdros), len(tf))
    assert emdros == tf            # full multiset, every row, both engines


@pytest.mark.tf
@pytest.mark.emdros
def test_gap_siblings_match_tf_ordering(require_emdros, require_tf, db_path):
    """The semantic arbiter, round two. Round one (2026-06-13) proved that
    MQL's BARE sibling juxtaposition means adjacent-within-the-parent's-monads
    (25827 rows; gaps in the clause skipped), which no TF template operator
    expresses (TF '<<' gave 40371, '<:' 25698; the 129-row gap is the
    gap-straddling clauses, confirmed by direct slot analysis on the corpus).

    MQL's OTHER sibling form, [A] .. [B] ("B anywhere after A"), should be
    semantically identical to TF '<<'. This test proves or refutes that with
    the full row multiset. If it passes, the faithful conversion pairing is
    MQL '..' <-> TF '<<', and bare juxtaposition stays refused."""
    mql = ("SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse "
           "[clause [phrase function=Pred] .. "
           "[phrase function=Objc [word GET g_word_utf8]]]] GO")
    # Hand-written template: the converter does not accept '..' yet; this
    # test is the semantic gate for teaching it to.
    template = ("verse\n  clause\n    p1:phrase function=Pred\n"
                "    p2:phrase function=Objc\n      word\np1 << p2")
    emdros = _emdros_rows(mql, db_path)
    tf = _tf_rows(template)
    assert len(emdros) == len(tf), (len(emdros), len(tf))   # expect 40371
    assert emdros == tf

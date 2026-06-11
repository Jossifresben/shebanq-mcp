"""Execute Text-Fabric search templates against the BHSA corpus.

The corpus loads once per process (warm()) and is pinned to the 2021 release,
matching the Emdros shebanq_etcbc2021 data so both engines answer identically.
Results are tuples of node numbers, one element per template line; the LAST
element is the leaf the user asked about (tf_primer.md instructs the
translator to put it last). Each leaf maps to the same raw-row shape the
Emdros runner produces, so format_results() is shared.

All TF calls pass silent="deep": in MCP stdio mode stdout is the protocol
channel and any TF progress chatter would corrupt it.
"""
import os
import re

from .runner import RunResult

DEFAULT_TF_VERSION = "2021"

_A = None   # the warm TF app; module-global so fork()ed workers inherit it


class TFUnavailable(RuntimeError):
    """text-fabric is not installed or the BHSA data is not present."""


def warm(version: str | None = None):
    """Load the corpus once; subsequent calls are free. Raises TFUnavailable
    with an actionable message if text-fabric or the data is missing.
    A `version` differing from the already-warm corpus is ignored; this server
    loads one version per process."""
    global _A
    if _A is None:
        v = version or os.environ.get("BHSA_TF_VERSION", DEFAULT_TF_VERSION)
        try:
            from tf.app import use
        except ImportError as exc:
            raise TFUnavailable(
                "text-fabric is not installed (pip install 'shebanq-mcp[tf]')"
            ) from exc
        try:
            _A = use("etcbc/bhsa", version=v, silent="deep")
        except Exception as exc:  # noqa: BLE001 - data download/load failure
            raise TFUnavailable(
                f"could not load BHSA TF data version {v}: {exc}") from exc
        if _A is None:
            raise TFUnavailable(
                f"could not load BHSA TF data version {v}")
    return _A


def _leaf_features(template: str) -> list[str]:
    """Feature names constrained on the last template line; these are echoed
    back per row (the TF analogue of the MQL GET clause)."""
    lines = [line for line in template.splitlines() if line.strip()]
    if not lines:
        return []
    # '=' only, deliberately: tf_validator's v1 grammar admits only feature=value pairs.
    # If the validator grows other comparators, extend this regex with it.
    return re.findall(r"([A-Za-z_][A-Za-z0-9_]*)=", lines[-1])


def _gloss(api, n):
    """The lexeme gloss. In BHSA TF gloss lives on lex nodes; many versions
    also expose it on words. Try the node, then climb to its lex."""
    gf = api.Fs("gloss")
    if gf is None:
        return None
    g = gf.v(n)
    if g is None and api.F.otype.v(n) == "word":
        lexs = api.L.u(n, otype="lex")
        if lexs:
            g = gf.v(lexs[0])
    return g


def run_template(template: str, features: list[str] | None = None,
                 limit: int | None = None,
                 version: str | None = None) -> RunResult:
    """Run a TF search template. count is the true total of result tuples;
    matches holds harvested leaf rows (capped at limit)."""
    A = warm(version)
    api = A.api
    results = A.search(template, silent="deep")
    feats = features if features is not None else _leaf_features(template)
    matches: list[dict] = []
    for tup in results:
        if limit is not None and len(matches) >= limit:
            break                       # count is len(results); harvest is capped
        n = tup[-1]
        section = tuple(api.T.sectionFromNode(n)) + (None, None, None)
        book, chapter, verse = section[:3]
        row = {
            "id_d": n,
            "book": book,
            "chapter": str(chapter) if chapter is not None else None,
            "verse": str(verse) if verse is not None else None,
            "text": api.T.text(n),
            "gloss": _gloss(api, n),
        }
        for f in feats:
            feat = api.Fs(f)
            row[f] = feat.v(n) if feat else None
        matches.append(row)
    return RunResult(count=len(results), matches=matches)


def tf_target(template, _db_path, features, q):
    """QueryGuard worker target for TF (same contract as guard._default_target).
    With a fork start method the child inherits the warm _A; with spawn it
    loads the corpus itself (slow but correct)."""
    try:
        raw = os.environ.get("MAX_RESULTS", "100")
        limit = int(raw) if raw else None
        res = run_template(template, features=features or None, limit=limit)
        q.put(("ok", res))
    except Exception as exc:  # noqa: BLE001 - report any failure to the parent
        q.put(("err", repr(exc)))

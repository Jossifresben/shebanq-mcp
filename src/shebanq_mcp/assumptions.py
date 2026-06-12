"""Extract the curated BHSA encoding caveats a query relies on.

Pure, deterministic, no model. Given an MQL query or a Text-Fabric search
template, find every catalogue feature the query touches (as a constraint
or as a GET/harvest feature) and return the deduplicated caveat strings,
in stable catalogue order. The gloss trap fires when gloss is only
displayed, so GET features must trigger.

Feature names are collected with the same regexes the validators use, so
this cannot disagree with what validation saw. Extraction is best-effort:
malformed input yields an empty list, never an exception (the validators
own error reporting).
"""
import re

from .feature_reference import FeatureReference

# MQL: feature=value constraints and GET feature lists, over a
# string-literal-stripped copy so a value like lex='gloss' cannot be read
# as the feature name.
_STRING_LITERAL = re.compile(r"""(['\"]).*?\1""", re.DOTALL)
_MQL_CONSTRAINT = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*=")
_MQL_GET = re.compile(r"\bGET\s+([A-Za-z0-9_,\s]+?)\s*(?=[\[\]])", re.IGNORECASE)
# TF template: feature=value pairs (the template has no GET clause).
_TF_PAIR = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=\S+")
_IS_MQL = re.compile(r"(?i)^\s*select\b")


def _mql_feature_names(query: str) -> list[str]:
    names: list[str] = []
    stripped = _STRING_LITERAL.sub("''", query)
    for m in _MQL_GET.finditer(stripped):
        names += [f.strip() for f in m.group(1).split(",") if f.strip()]
    # constraints: feature= ; exclude GET-list bare names handled above.
    # Strip GET clauses before scanning constraints so GET feature names are
    # not double-read as constraints (harmless to dedup, but keep it clean).
    no_get = _MQL_GET.sub(" ", stripped)
    names += _MQL_CONSTRAINT.findall(no_get)
    return names


def _tf_feature_names(template: str) -> list[str]:
    names: list[str] = []
    for line in template.splitlines():
        names += _TF_PAIR.findall(line)
    return names


def assumptions_for(query_text: str, ref: FeatureReference) -> list[str]:
    text = (query_text or "").strip()
    if not text:
        return []
    raw = (_mql_feature_names(text) if _IS_MQL.match(text)
           else _tf_feature_names(text))
    # Collect caveats in stable catalogue order, deduped by NOTE TEXT.
    seen: set[str] = set()
    used = set(raw)
    out: list[str] = []
    for name in ref.features:                  # catalogue order
        if name not in used:
            continue
        note = ref.caveat_for(name)
        if note and note not in seen:
            seen.add(note)
            out.append(note)
    return out

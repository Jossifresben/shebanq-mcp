"""Deterministic MQL-to-TF-template conversion: the mirror of tf_to_mql.

A scholar with a SHEBANQ query (their own or a cited one) gets the
Text-Fabric template that runs the same search in a notebook. NO model in
the loop: brackets become indentation, AND between constraints becomes a
space, quoted string values lose their quotes. GET clauses are dropped
with a note: GET only selects which features come back, never what
matches, and TF results expose every feature.

Scope is the convertible MQL subset (the shape tf_to_mql emits, plus GET).
Richer MQL (OR, NOT, NOTEXIST, FOCUS, sequence/adjacency operators,
HAVING MONADS) has no place in the v1 template grammar and is refused,
never silently dropped.
"""
import re
from dataclasses import dataclass, field

from .feature_reference import FeatureReference
from .tf_to_mql import ConversionError
from .validator import validate_mql

_SKELETON = re.compile(r"(?is)^\s*SELECT\s+ALL\s+OBJECTS\s+WHERE\s+(.*?)\s+GO\s*$")
# Scanned with string literals stripped, so lex='OR' cannot trip it.
_UNSUPPORTED = re.compile(
    r"(?i)\b(OR|NOT|NOTEXIST|EXISTS|FOCUS|HAVING|RETRIEVE|NORETRIEVE"
    r"|FIRST|LAST|AS|IN)\b|[!*]|\.\.")
_STRING_LITERAL = re.compile(r"'[^']*'")
_BLOCK_OPEN = re.compile(r"\[\s*([A-Za-z_][A-Za-z0-9_]*)")
_GET = re.compile(r"(?i)\bGET\s+[A-Za-z0-9_,\s]+?(?=[\[\]])")
_CONSTRAINT = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:'([^']*)'|([^\s\]]+))$")

_GET_NOTE = "GET clauses dropped; Text-Fabric results expose all features."


@dataclass
class ConversionResult:
    text: str
    notes: list[str] = field(default_factory=list)


def _parse_constraints(region: str) -> list[str]:
    """'sp=verb AND lex='BR>['' -> ['sp=verb', 'lex=BR>[']. Refuses anything
    that is not feature=value pairs joined by AND."""
    region = region.strip()
    if not region:
        return []
    out: list[str] = []
    for part in re.split(r"(?i)\s+AND\s+", region):
        m = _CONSTRAINT.match(part.strip())
        if not m:
            raise ConversionError(
                f"constraint '{part.strip()}' cannot be converted to a "
                "Text-Fabric feature=value pair")
        feat = m.group(1)
        value = m.group(2) if m.group(2) is not None else m.group(3)
        if " " in value:
            raise ConversionError(
                f"value {value!r} for feature '{feat}' contains a space; "
                "Text-Fabric feature=value pairs cannot carry spaces")
        out.append(f"{feat}={value}")
    return out


def mql_to_tf(mql: str, ref: FeatureReference) -> ConversionResult:
    """Convert convertible MQL to a v1-grammar TF search template."""
    m = _SKELETON.match(mql)
    if not m:
        raise ConversionError(
            "only 'SELECT ALL OBJECTS WHERE <blocks> GO' queries can be "
            "converted (the SHEBANQ-citable shape)")
    validation = validate_mql(mql, ref)
    if not validation.ok:
        raise ConversionError("; ".join(validation.errors))
    body = m.group(1)

    # Refuse out-of-grammar constructs, with literals stripped so a keyword
    # inside a quoted value is safe.
    stripped = _STRING_LITERAL.sub("''", body)
    bad = _UNSUPPORTED.search(_GET.sub("", stripped))
    if bad:
        raise ConversionError(
            f"'{bad.group(0)}' has no Text-Fabric equivalent in the v1 "
            "template grammar and cannot be converted")

    # Drop GET clauses (note once if any were present).
    notes: list[str] = []
    if _GET.search(body):
        body = _GET.sub("", body)
        notes.append(_GET_NOTE)

    # Walk the bracket structure; emit one line per block at 2-space depth.
    lines: list[str] = []
    depth = 0
    i, n = 0, len(body)
    while i < n:
        ch = body[i]
        if ch == "'":                       # skip string literals whole
            j = body.find("'", i + 1)
            i = n if j == -1 else j + 1
            continue
        if ch == "[":
            mo = _BLOCK_OPEN.match(body, i)
            if not mo:
                raise ConversionError("malformed block open near "
                                      f"'{body[i:i+20]}'")
            otype = mo.group(1)
            # The constraint region runs to this block's first child or close.
            j = mo.end()
            k = j
            while k < n and body[k] not in "[]":
                if body[k] == "'":
                    k2 = body.find("'", k + 1)
                    k = n if k2 == -1 else k2 + 1
                    continue
                k += 1
            constraints = _parse_constraints(body[j:k])
            lines.append("  " * depth + " ".join([otype] + constraints))
            depth += 1
            i = k
            continue
        if ch == "]":
            depth -= 1
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        raise ConversionError(
            f"unexpected text '{body[i:i+20].strip()}' between blocks "
            "cannot be converted")
    return ConversionResult(text="\n".join(lines), notes=notes)

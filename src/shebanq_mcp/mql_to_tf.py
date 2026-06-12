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
never silently dropped. Sibling blocks (multiple children under one parent)
are converted faithfully: each sibling gets a name (p1, p2, ...) and
ordering lines (p1 << p2) are appended so the Text-Fabric template
preserves MQL's textual (left-to-right) order. Multiple top-level roots
are still refused (TF templates require a single root).
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

# Operator constant — swap in ONE place if CI proves << is wrong.
_ORDER_OP = "<<"

_GET_NOTE = "GET clauses dropped; Text-Fabric results expose all features."


@dataclass
class ConversionResult:
    text: str
    notes: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal node tree used by the two-pass emitter
# ---------------------------------------------------------------------------

@dataclass
class _Block:
    otype: str
    constraints: list[str]
    children: list["_Block"] = field(default_factory=list)
    # assigned in the naming pass; None means "no name needed"
    name: str | None = None


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


def _parse_blocks(body: str) -> list[_Block]:
    """Walk the bracket structure and return the list of top-level _Block
    nodes. Each block's children list carries its direct child blocks.
    Refuses multiple top-level roots."""
    roots: list[_Block] = []
    stack: list[_Block] = []  # open blocks, innermost last
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
            # Constraint region: from end of otype match to the next [ or ]
            j = mo.end()
            k = j
            while k < n and body[k] not in "[]":
                if body[k] == "'":
                    k2 = body.find("'", k + 1)
                    k = n if k2 == -1 else k2 + 1
                    continue
                k += 1
            constraints = _parse_constraints(body[j:k])
            block = _Block(otype=otype, constraints=constraints)
            if stack:
                stack[-1].children.append(block)
            else:
                roots.append(block)
            stack.append(block)
            i = k
            continue
        if ch == "]":
            if not stack:
                raise ConversionError(
                    "unbalanced brackets: more ']' than '[' in the query")
            stack.pop()
            i += 1
            continue
        if ch.isspace():
            i += 1
            continue
        raise ConversionError(
            f"unexpected text '{body[i:i+20].strip()}' between blocks "
            "cannot be converted")
    if stack:
        raise ConversionError(
            "unbalanced brackets: a '[' block is never closed")
    return roots


def _assign_names(roots: list[_Block]) -> list[tuple[str, str]]:
    """Pre-order walk: for each block with >=2 children, assign p1..pN names
    to ALL its children (in textual order) and record (prev, this) ordering
    pairs. A block with exactly one child: child gets NO name (chain case).
    Returns the list of ordering pairs in encountered order."""
    counter = [0]   # mutable int in a list so the nested fn can increment it
    pairs: list[tuple[str, str]] = []

    def _walk(block: _Block) -> None:
        if len(block.children) >= 2:
            prev_name: str | None = None
            for child in block.children:
                counter[0] += 1
                child.name = f"p{counter[0]}"
                if prev_name is not None:
                    pairs.append((prev_name, child.name))
                prev_name = child.name
        for child in block.children:
            _walk(child)

    for root in roots:
        _walk(root)
    return pairs


def _render(roots: list[_Block], pairs: list[tuple[str, str]]) -> str:
    """Emit object lines (with optional name prefix) then ordering lines."""
    lines: list[str] = []

    def _emit(block: _Block, depth: int) -> None:
        prefix = f"{block.name}:" if block.name else ""
        parts = [block.otype] + block.constraints
        lines.append("  " * depth + prefix + " ".join(parts))
        for child in block.children:
            _emit(child, depth + 1)

    for root in roots:
        _emit(root, 0)

    for a, b in pairs:
        lines.append(f"{a} {_ORDER_OP} {b}")

    return "\n".join(lines)


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

    # Drop GET clauses (note once if any were present). Decide on the
    # literal-stripped text so 'GET' inside a quoted value is never touched;
    # if a raw match overlaps a literal, refuse rather than corrupt it.
    notes: list[str] = []
    if _GET.search(body):
        for m_get in _GET.finditer(body):
            for m_lit in _STRING_LITERAL.finditer(body):
                if m_get.start() < m_lit.end() and m_lit.start() < m_get.end():
                    raise ConversionError(
                        "a quoted value containing 'GET' cannot be "
                        "converted safely; rename or drop that value")
        body = _GET.sub("", body)
        notes.append(_GET_NOTE)

    # Pass 1: parse the bracket structure into a node tree.
    roots = _parse_blocks(body)

    if not roots:
        raise ConversionError("the query has no object blocks to convert")

    # Multiple top-level roots are refused (TF needs a single root).
    if len(roots) > 1:
        raise ConversionError(
            "multiple top-level object blocks cannot be converted: "
            "a Text-Fabric template must have a single root")

    # Pass 2: assign names to siblings (multi-child parents only) and
    # collect the ordering pairs.
    pairs = _assign_names(roots)

    # Pass 3: render.
    text = _render(roots, pairs)

    return ConversionResult(text=text, notes=notes)

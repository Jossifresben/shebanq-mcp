"""Deterministic TF-template-to-MQL conversion, for SHEBANQ citation.

A scholar working in a Text-Fabric notebook needs a citable SHEBANQ permalink
for publication. This converts their template to the equivalent MQL with NO
model in the loop: indentation becomes brackets, spaces between constraints
become AND, and the quoting rule comes from the shared catalogue (string
features quoted, enum features bare). The output is validated MQL or a
ConversionError that says plainly what could not be carried over.

Scope is the v1 template grammar tf_validator accepts. Richer TF constructs
(regex ~, quantifier blocks, relational operators) have no MQL equivalent
here and are refused, never silently dropped.
"""
from .feature_reference import FeatureReference
from .tf_validator import _LINE, _PAIR, validate_tf


class ConversionError(ValueError):
    """The template is invalid or uses constructs outside the v1 grammar."""


def _constraints(otype: str, pairs: str, ref: FeatureReference) -> str:
    parts = []
    for feat, value in _PAIR.findall(pairs):
        if ref.kind_for(feat, otype) == "string":
            parts.append(f"{feat}='{value}'")
        else:
            parts.append(f"{feat}={value}")
    if not parts:
        return otype
    return f"{otype} " + " AND ".join(parts)


def tf_to_mql(template: str, ref: FeatureReference) -> str:
    """Convert a v1-grammar TF search template to equivalent MQL."""
    # Surface out-of-grammar TF syntax with a specific message before the
    # generic validator complaint (a '~' line also fails _LINE).
    for lineno, raw in enumerate(template.splitlines(), 1):
        line = raw.strip()
        if not line:
            continue
        if not _LINE.match(line):
            raise ConversionError(
                f"line {lineno} ('{line}') uses Text-Fabric syntax that "
                "cannot be converted to MQL here (only "
                "'<object_type> feature=value ...' lines are supported)")
    validation = validate_tf(template, ref)
    if not validation.ok:
        raise ConversionError("; ".join(validation.errors))

    # Build nested MQL blocks from indentation. Each open block tracks its
    # indent; a shallower or equal line closes blocks down to its parent.
    out: list[str] = []
    stack: list[int] = []              # indents of open blocks
    for raw in template.splitlines():
        if not raw.strip():
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        while stack and stack[-1] >= indent:
            stack.pop()
            out.append("]")
        m = _LINE.match(raw.strip())
        out.append("[" + _constraints(m.group(1), m.group(2), ref))
        stack.append(indent)
    out.extend("]" * len(stack))
    body = " ".join(out).replace("[ ", "[").replace(" ]", "]")
    return f"SELECT ALL OBJECTS WHERE {body} GO"

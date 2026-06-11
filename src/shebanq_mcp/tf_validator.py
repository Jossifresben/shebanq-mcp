"""Static validation of Text-Fabric search templates.

Three checks: every line's object type is known; every feature=value pair uses
a feature valid on that type (with enum values from the shared catalogue);
indentation is well-formed. No read-only guard is needed: templates are passed
to A.search(), which cannot mutate, and nothing here is ever evaluated.

v1 grammar (the shape tf_primer.md teaches): each line is
    <otype> [<feature>=<value>]...
Relational operators and quantifiers are out of scope; a line that does not
match the grammar is an error, never silently accepted.
"""
import re

from .feature_reference import FeatureReference
from .validator import ValidationResult

# <otype> followed by zero or more feature=value pairs. Values are any run of
# non-space characters: BHSA lexemes carry trailing '[' or '/' (BR>[, DBR/).
_LINE = re.compile(
    r"^([A-Za-z_][A-Za-z0-9_]*)"
    r"((?:\s+[A-Za-z_][A-Za-z0-9_]*=\S+)*)\s*$"
)
_PAIR = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\S+)")


def _check_line(otype: str, pairs: str, ref: FeatureReference,
                lineno: int) -> list[str]:
    errors: list[str] = []
    if not ref.is_object_type(otype):
        valid = ", ".join(o["name"] for o in ref.object_types())
        errors.append(
            f"line {lineno}: unknown object type '{otype}' (valid: {valid})")
        return errors                  # feature checks need a real type
    for feat, value in _PAIR.findall(pairs):
        kind = ref.kind_for(feat, otype)
        if kind is None:
            errors.append(
                f"line {lineno}: feature '{feat}' is not valid on object "
                f"type '{otype}'")
        elif kind == "enum":
            if value not in (ref.values_for(feat, otype) or {}):
                errors.append(
                    f"line {lineno}: unknown value '{value}' for enum "
                    f"feature '{feat}' on object type '{otype}'")
        # string features accept any value; TF never quotes
    return errors


def validate_tf(template: str, ref: FeatureReference) -> ValidationResult:
    errors: list[str] = []
    stack: list[int] = []              # active indentation levels
    indent_step: int | None = None     # first non-zero indent increment seen
    saw_content = False
    for lineno, raw in enumerate(template.splitlines(), 1):
        if not raw.strip():
            continue
        saw_content = True
        head = raw[: len(raw) - len(raw.lstrip())]
        if "\t" in head:
            errors.append(f"line {lineno}: indentation uses a tab; use spaces")
            continue
        indent = len(head)
        if not stack:
            if indent != 0:
                errors.append(
                    f"line {lineno}: first line must not be indented")
            stack = [indent]
        elif indent > stack[-1]:
            step = indent - stack[-1]
            if indent_step is None:
                indent_step = step
            if step != indent_step:
                errors.append(
                    f"line {lineno}: indentation does not align with any "
                    "enclosing level")
                stack.append(indent)   # keep going; report later lines too
            else:
                stack.append(indent)
        else:
            while stack and stack[-1] > indent:
                stack.pop()
            if not stack or stack[-1] != indent:
                errors.append(
                    f"line {lineno}: indentation does not align with any "
                    "enclosing level")
                stack.append(indent)   # keep going; report later lines too
        m = _LINE.match(raw.strip())
        if not m:
            errors.append(
                f"line {lineno}: expected '<object_type> feature=value ...' "
                f"(got '{raw.strip()}')")
            continue
        errors.extend(_check_line(m.group(1), m.group(2), ref, lineno))
    if not saw_content:
        errors.append("template is empty")
    return ValidationResult(ok=not errors, errors=errors)

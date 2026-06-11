import re
from dataclasses import dataclass, field

from .feature_reference import FeatureReference


# Read-only enforcement. Strip string literals first so a keyword inside a
# quoted feature value (e.g. lex='DELETE') cannot trip the guard.
_STRING_LITERAL = re.compile(r"""(['\"]).*?\1""", re.DOTALL)
_MUTATING = re.compile(
    r"\b(CREATE|DROP|UPDATE|DELETE|INSERT|ALTER|REPLACE|VACUUM|ATTACH|DETACH"
    r"|PRAGMA|BEGIN|COMMIT|ROLLBACK|ABORT|USE)\b",
    re.IGNORECASE,
)
_READ_VERB = re.compile(r"^\s*(SELECT|GET)\b", re.IGNORECASE)


def _read_only_errors(mql: str) -> list[str]:
    stripped = _STRING_LITERAL.sub("''", mql)
    errors: list[str] = []
    if not _READ_VERB.match(stripped):
        errors.append(
            "only read-only queries are allowed; the query must begin with "
            "SELECT or GET"
        )
    m = _MUTATING.search(stripped)
    if m:
        errors.append(
            "mutating MQL is not permitted on this read-only endpoint "
            f"(found '{m.group(1).upper()}')"
        )
    return errors


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


_BLOCK_OPEN = re.compile(r"\[\s*([A-Za-z_][A-Za-z0-9_]*)")
_GET_AT = re.compile(r"GET\s+([A-Za-z0-9_,\s]+?)\s*(?=[\[\]])", re.IGNORECASE)
_CONSTRAINT_AT = re.compile(
    r"([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:(['\"])(.*?)\2|([^\s\]]+))")


def _structure_errors(mql: str, ref: FeatureReference) -> list[str]:
    errors: list[str] = []
    stack: list[str] = []           # enclosing object types, innermost last
    i, n = 0, len(mql)
    while i < n:
        ch = mql[i]
        if ch in "'\"":             # skip a string literal whole
            j = mql.find(ch, i + 1)
            i = n if j == -1 else j + 1
            continue
        if ch == "[":
            m = _BLOCK_OPEN.match(mql, i)
            if m:
                otype = m.group(1)
                if not ref.is_object_type(otype):
                    valid = ", ".join(o["name"] for o in ref.object_types())
                    errors.append(f"unknown object type '{otype}' (valid: {valid})")
                stack.append(otype)
                i = m.end()
                continue
            i += 1
            continue
        if ch == "]":
            if stack:
                stack.pop()
            i += 1
            continue
        if stack:
            mg = _GET_AT.match(mql, i)
            if mg:
                for feat in (f.strip() for f in mg.group(1).split(",") if f.strip()):
                    if ref.kind_for(feat, stack[-1]) is None:
                        errors.append(
                            f"GET feature '{feat}' is not valid on object type "
                            f"'{stack[-1]}'")
                i = mg.end()
                continue
            mc = _CONSTRAINT_AT.match(mql, i)
            if mc:
                feat = mc.group(1)
                quoted = mc.group(2) is not None
                value = mc.group(3) if quoted else mc.group(4)
                otype = stack[-1]
                kind = ref.kind_for(feat, otype)
                if kind is None:
                    errors.append(
                        f"feature '{feat}' is not valid on object type '{otype}'")
                elif kind == "enum":
                    if quoted:
                        errors.append(
                            f"enum feature '{feat}' must be unquoted "
                            f"(use {feat}={value})")
                    elif value not in (ref.values_for(feat, otype) or {}):
                        errors.append(
                            f"unknown value '{value}' for enum feature '{feat}' "
                            f"on object type '{otype}'")
                elif kind == "string" and not quoted:
                    errors.append(
                        f"string feature '{feat}' must be quoted (use {feat}='{value}')")
                i = mc.end()
                continue
        i += 1
    return errors


def validate_mql(mql: str, ref: FeatureReference) -> ValidationResult:
    errors = _read_only_errors(mql) + _structure_errors(mql, ref)
    return ValidationResult(ok=not errors, errors=errors)

import re
from dataclasses import dataclass, field

from .feature_reference import FeatureReference

# A constraint is `name = value`, where value is either quoted (a string
# feature: name='val' / name="val") or a bare token (an enum/integer feature:
# name=val). The two alternatives are captured separately so we can tell whether
# the value was quoted.
_CONSTRAINT = re.compile(
    r"""\b([A-Za-z_][A-Za-z0-9_]*)\s*=\s*"""   # feature name, then '='
    r"""(?:(['"])(.*?)\2|([^\s\]]+))""",        # quoted value OR bare token
    re.VERBOSE,
)


# Read-only enforcement. Strip string literals first so a keyword inside a
# quoted feature value (e.g. lex='DELETE') cannot trip the guard.
_STRING_LITERAL = re.compile(r"""(['\"]).*?\1""", re.DOTALL)
_MUTATING = re.compile(
    r"\b(CREATE|DROP|UPDATE|DELETE|INSERT|ALTER|REPLACE|VACUUM|ATTACH|DETACH"
    r"|PRAGMA|BEGIN|COMMIT|ROLLBACK)\b",
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


def validate_mql(mql: str, ref: FeatureReference) -> ValidationResult:
    errors: list[str] = _read_only_errors(mql)
    for match in _CONSTRAINT.finditer(mql):
        feature = match.group(1)
        quoted = match.group(2) is not None
        value = match.group(3) if quoted else match.group(4)

        if not ref.has_feature(feature):
            errors.append(
                f"unknown feature '{feature}' (not in BHSA feature reference)"
            )
            continue

        if ref.is_enum(feature):
            if quoted:
                errors.append(
                    f"enum feature '{feature}' must be unquoted "
                    f"(use {feature}={value}, not {feature}='{value}')"
                )
            elif not ref.is_enum_constant(value):
                errors.append(
                    f"unknown enum value '{value}' for feature '{feature}'"
                )
        elif ref.is_string(feature):
            if not quoted:
                errors.append(
                    f"string feature '{feature}' must be quoted "
                    f"(use {feature}='{value}', not {feature}={value})"
                )

    return ValidationResult(ok=not errors, errors=errors)

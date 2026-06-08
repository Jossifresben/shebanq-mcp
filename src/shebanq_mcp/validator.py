import re
from dataclasses import dataclass, field

from .feature_reference import FeatureReference

# Matches `name='value'` or `name="value"` constraints inside MQL blocks.
_CONSTRAINT = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:=|==)\s*(['\"])(.*?)\2")


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)


def validate_mql(mql: str, ref: FeatureReference) -> ValidationResult:
    errors: list[str] = []
    for feature, _quote, value in _CONSTRAINT.findall(mql):
        if not ref.has_feature(feature):
            errors.append(
                f"unknown feature '{feature}' (not in BHSA feature reference)"
            )
        elif not ref.is_valid(feature, value):
            errors.append(
                f"invalid value '{value}' for feature '{feature}'"
            )
    return ValidationResult(ok=not errors, errors=errors)

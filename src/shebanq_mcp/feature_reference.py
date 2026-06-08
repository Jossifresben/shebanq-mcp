import json
from importlib import resources
from dataclasses import dataclass


@dataclass
class FeatureReference:
    version: str
    features: dict
    enum_constants: frozenset

    @classmethod
    def load(cls) -> "FeatureReference":
        text = resources.files("shebanq_mcp").joinpath("features.json").read_text(
            encoding="utf-8"
        )
        data = json.loads(text)
        return cls(
            version=data["version"],
            features=data["features"],
            enum_constants=frozenset(data.get("enum_constants", [])),
        )

    def has_feature(self, name: str) -> bool:
        return name in self.features

    def feature_gloss(self, name: str) -> str | None:
        f = self.features.get(name)
        return f["gloss"] if f else None

    def kind(self, feature: str) -> str | None:
        """'enum', 'string', or 'integer' — or None if the feature is unknown."""
        f = self.features.get(feature)
        return f.get("kind") if f else None

    def is_enum(self, feature: str) -> bool:
        return self.kind(feature) == "enum"

    def is_string(self, feature: str) -> bool:
        return self.kind(feature) == "string"

    def is_enum_constant(self, value: str) -> bool:
        """Whether a value is a member of the shared all_enum set (the constants
        the engine accepts for any enumeration feature)."""
        return value in self.enum_constants

    def is_valid(self, feature: str, value: str) -> bool:
        f = self.features.get(feature)
        if f is None:
            return False
        values = f.get("values")
        if values is None:  # open-valued feature (e.g. lex)
            return True
        return value in values

    def lookup(self, feature: str) -> dict | None:
        return self.features.get(feature)

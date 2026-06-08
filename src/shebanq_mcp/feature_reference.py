import json
from importlib import resources
from dataclasses import dataclass


@dataclass
class FeatureReference:
    version: str
    features: dict

    @classmethod
    def load(cls) -> "FeatureReference":
        text = resources.files("shebanq_mcp").joinpath("features.json").read_text(
            encoding="utf-8"
        )
        data = json.loads(text)
        return cls(version=data["version"], features=data["features"])

    def has_feature(self, name: str) -> bool:
        return name in self.features

    def feature_gloss(self, name: str) -> str | None:
        f = self.features.get(name)
        return f["gloss"] if f else None

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

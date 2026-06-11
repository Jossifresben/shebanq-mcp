import json
from importlib import resources
from dataclasses import dataclass


@dataclass
class FeatureReference:
    version: str
    features: dict           # name -> {"objects": {otype: {kind, gloss, values?}}}
    _object_types: list      # ordered [{name, gloss}], outermost first
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
            _object_types=data["object_types"],
            enum_constants=frozenset(data.get("enum_constants", [])),
        )

    # ---- v2 scoped API ----
    def object_types(self) -> list:
        return self._object_types

    def is_object_type(self, name: str) -> bool:
        return any(o["name"] == name for o in self._object_types)

    def objects_for(self, feature: str) -> list[str]:
        f = self.features.get(feature)
        return list(f["objects"]) if f else []

    def kind_for(self, feature: str, object_type: str) -> str | None:
        f = self.features.get(feature)
        spec = (f or {}).get("objects", {}).get(object_type)
        return spec["kind"] if spec else None

    def values_for(self, feature: str, object_type: str) -> dict | None:
        f = self.features.get(feature)
        spec = (f or {}).get("objects", {}).get(object_type)
        return spec.get("values") if spec else None

    def gloss_for(self, feature: str, object_type: str) -> str | None:
        f = self.features.get(feature)
        spec = (f or {}).get("objects", {}).get(object_type)
        return spec.get("gloss") if spec else None

    def features_for(self, object_type: str) -> dict:
        """name -> per-type spec, for every feature that lives on object_type."""
        out = {}
        for name, f in self.features.items():
            spec = f.get("objects", {}).get(object_type)
            if spec:
                out[name] = spec
        return out

    # ---- union back-compat (validator v1 semantics) ----
    def _entries(self, feature: str) -> list[dict]:
        f = self.features.get(feature)
        return list(f["objects"].values()) if f else []

    def has_feature(self, name: str) -> bool:
        return name in self.features

    def kind(self, feature: str) -> str | None:
        kinds = {e["kind"] for e in self._entries(feature)}
        return next(iter(kinds)) if len(kinds) == 1 else (
            "enum" if "enum" in kinds else next(iter(kinds), None))

    def is_enum(self, feature: str) -> bool:
        return self.kind(feature) == "enum"

    def is_string(self, feature: str) -> bool:
        return self.kind(feature) == "string"

    def feature_gloss(self, name: str) -> str | None:
        for e in self._entries(name):
            if e.get("gloss"):
                return e["gloss"]
        return None

    def is_enum_constant(self, value: str) -> bool:
        return value in self.enum_constants

    def is_valid(self, feature: str, value: str) -> bool:
        entries = self._entries(feature)
        if not entries:
            return False
        union: set = set()
        for e in entries:
            vals = e.get("values")
            if vals is None:
                return True          # any open-valued entry accepts anything
            union.update(vals)
        return value in union

    def lookup(self, feature: str) -> dict | None:
        return self.features.get(feature)

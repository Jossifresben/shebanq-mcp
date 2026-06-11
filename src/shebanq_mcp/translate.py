"""NL -> MQL translation.

Translation is the one model-dependent seam in the server. It is isolated behind
the `Translator` protocol so the provider is a swappable adapter. An Anthropic
adapter ships as the default; add others (OpenAI, a local model) by writing a
class with a `translate()` method and a branch in `build_translator()`.

The server may also run translation-free: `build_translator("none")` returns
None, in which case `search_bhsa` is unavailable and callers use `run_mql` with
a query composed elsewhere (e.g. by the MCP host's own model).
"""
import os
from importlib import resources
from typing import Protocol

from .feature_reference import FeatureReference

DEFAULT_MODEL = "claude-opus-4-8"

_OUTPUT_RULE = (
    "You translate questions about the Hebrew Bible into Emdros MQL queries over "
    "the BHSA database. Output ONLY the MQL query: no explanation, no code fences. "
    "Use only the object types, features, and values in the reference below, and "
    "follow the MQL primer."
)


def _load_primer() -> str:
    return resources.files("shebanq_mcp").joinpath("mql_primer.md").read_text(
        encoding="utf-8"
    )


def _reference_block(ref: FeatureReference) -> str:
    lines = ["Object hierarchy (outermost first): "
             + " > ".join(o["name"] for o in ref.object_types())]
    # A feature on several object types (e.g. typ, rela) is listed once per type
    # on purpose — its value set differs per type and the model needs each.
    for o in ref.object_types():
        feats = ref.features_for(o["name"])
        if not feats:
            continue
        lines.append(f"\n[{o['name']}] — {o['gloss']}")
        for name, spec in sorted(feats.items()):
            kind = spec.get("kind", "string")
            values = spec.get("values")
            if kind == "enum" and values:
                vals = ", ".join(f"{k}={v}" for k, v in values.items())
                lines.append(f"- {name} [enum, UNQUOTED]: {spec.get('gloss', '')}; values: {vals}")
            elif kind == "string":
                lines.append(f"- {name} [string, QUOTED]: {spec.get('gloss', '')}")
            else:
                lines.append(f"- {name} [{kind}]: {spec.get('gloss', '')}")
    return "\n".join(lines)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def build_prompt(ref: FeatureReference) -> str:
    """The provider-agnostic system prompt: a terse output rule, the MQL primer
    (curriculum), and the v2 object-scoped feature reference."""
    return "\n\n".join([
        _OUTPUT_RULE,
        _load_primer(),
        "BHSA feature reference (feature [kind]: gloss; values), grouped by object "
        "type:\n" + _reference_block(ref),
    ])


class Translator(Protocol):
    """Anything that turns a plain-language question into candidate MQL."""

    def translate(self, question: str, ref: FeatureReference) -> str: ...


class AnthropicTranslator:
    """Default adapter: drafts MQL with the Anthropic API."""

    def __init__(self, client=None, model: str = DEFAULT_MODEL):
        self._client = client
        self._model = model

    def _ensure_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic()
        return self._client

    def translate(self, question: str, ref: FeatureReference) -> str:
        client = self._ensure_client()
        msg = client.messages.create(
            model=self._model,
            max_tokens=1024,
            system=build_prompt(ref),
            messages=[{"role": "user", "content": question}],
        )
        return _strip_fences(msg.content[0].text)


def build_translator(provider: str | None = None) -> "Translator | None":
    """Construct the configured translator. `provider` defaults to LLM_PROVIDER
    then "anthropic"; "none"/"off"/"" returns None. The model is LLM_MODEL (env),
    defaulting to DEFAULT_MODEL."""
    provider = (provider or os.environ.get("LLM_PROVIDER", "anthropic")).strip().lower()
    if provider in ("none", "off", ""):
        return None
    if provider == "anthropic":
        model = os.environ.get("LLM_MODEL", "").strip() or DEFAULT_MODEL
        return AnthropicTranslator(model=model)
    raise ValueError(
        f"unknown LLM_PROVIDER '{provider}' (supported: anthropic, none)"
    )

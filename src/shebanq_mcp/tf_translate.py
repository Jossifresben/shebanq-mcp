"""NL -> Text-Fabric search template translation.

Mirrors translate.py for the TF engine: same Translator protocol, same
Anthropic adapter, but the system prompt teaches TF search templates instead
of MQL. The shared FeatureReference constrains both translators to one
feature vocabulary, so the two artifacts cannot disagree about what a value
means.
"""
import os
from importlib import resources

from .feature_reference import FeatureReference
from .translate import (
    DEFAULT_MODEL,
    AnthropicTranslator,
    Translator,
    _reference_block,
)

_TF_OUTPUT_RULE = (
    "You translate questions about the Hebrew Bible into Text-Fabric search "
    "templates over the BHSA corpus. Output ONLY the Text-Fabric search template: "
    "no explanation, no code fences. Use only the object types, features, and "
    "values in the reference below, and follow the primer. Never quote values."
)


def _load_tf_primer() -> str:
    return resources.files("shebanq_mcp").joinpath("tf_primer.md").read_text(
        encoding="utf-8"
    )


def build_tf_prompt(ref: FeatureReference) -> str:
    """The provider-agnostic TF system prompt: output rule, TF primer, and the
    object-scoped feature reference without MQL quoting annotations."""
    return "\n\n".join([
        _TF_OUTPUT_RULE,
        _load_tf_primer(),
        "BHSA feature reference (feature [kind]: gloss; values), grouped by object "
        "type:\n" + _reference_block(ref, quoting=False),
    ])


def build_tf_translator(provider: str | None = None) -> "Translator | None":
    """Construct the TF translator with the same provider/model config as the
    MQL one (LLM_PROVIDER, LLM_MODEL). Returns None for provider 'none'."""
    provider = (provider or os.environ.get("LLM_PROVIDER", "anthropic")).strip().lower()
    if provider in ("none", "off", ""):
        return None
    if provider == "anthropic":
        model = os.environ.get("LLM_MODEL", "").strip() or DEFAULT_MODEL
        return AnthropicTranslator(model=model, prompt_builder=build_tf_prompt)
    raise ValueError(
        f"unknown LLM_PROVIDER '{provider}' (supported: anthropic, none)"
    )

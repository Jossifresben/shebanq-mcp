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
from typing import Protocol

from .feature_reference import FeatureReference

DEFAULT_MODEL = "claude-opus-4-8"

_INSTRUCTIONS = """You translate questions about the Hebrew Bible into Emdros \
MQL queries over the BHSA database. Output ONLY the MQL query, nothing else: no \
explanation, no code fences. Use only the features and values listed below. \
Prefer querying the appropriate object type (word, phrase, clause, sentence). \
Always end the query with GO. Add a GET clause listing the features needed to \
display results (e.g. GET sp, gloss).

CRITICAL quoting rule:
- Enumeration features are compared UNQUOTED: write sp=verb, vs=nif (NOT \
sp='verb').
- String features are compared QUOTED: write lex='BR>[', gloss='create'.
Getting this wrong makes the query fail to compile.

BHSA feature reference (feature [kind]: gloss; values):
{reference}"""


def _reference_block(ref: FeatureReference) -> str:
    lines = []
    for name, spec in ref.features.items():
        kind = spec.get("kind", "string")
        values = spec.get("values")
        if kind == "enum" and values:
            vals = ", ".join(f"{k}={v}" for k, v in values.items())
            lines.append(f"- {name} [enum, UNQUOTED]: {spec['gloss']}; values: {vals}")
        elif kind == "string":
            lines.append(f"- {name} [string, QUOTED]: {spec['gloss']}")
        else:
            lines.append(f"- {name} [{kind}]: {spec['gloss']}")
    return "\n".join(lines)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def build_prompt(ref: FeatureReference) -> str:
    """The provider-agnostic system prompt, shared by all adapters."""
    return _INSTRUCTIONS.format(reference=_reference_block(ref))


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
    """Construct the configured translator.

    `provider` defaults to the LLM_PROVIDER env var, then to "anthropic".
    "none"/"off"/"" returns None (translation-free server).
    """
    provider = (provider or os.environ.get("LLM_PROVIDER", "anthropic")).strip().lower()
    if provider in ("none", "off", ""):
        return None
    if provider == "anthropic":
        return AnthropicTranslator()
    raise ValueError(
        f"unknown LLM_PROVIDER '{provider}' (supported: anthropic, none)"
    )

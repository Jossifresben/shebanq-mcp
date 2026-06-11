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

# The worked examples below are authored to teach query STRUCTURE and to GET
# display features (g_word_utf8, gloss) so generated queries match what the web
# demo shows. They are deliberately NOT synced from
# tests/fixtures/featured_searches.json (that fixture exists for count
# regression, where the GET clause is irrelevant) — keep them display-oriented.
_INSTRUCTIONS = """You translate questions about the Hebrew Bible into Emdros \
MQL queries over the BHSA database. Output ONLY the MQL query, nothing else: no \
explanation, no code fences. Use only the features and values listed below. \
Prefer querying the appropriate object type (word, phrase, clause, sentence).

QUERY STRUCTURE (required). Write exactly one complete query of this form:
  SELECT ALL OBJECTS WHERE [<object_type> <conditions> GET <features>] GO
- The query MUST begin with `SELECT ALL OBJECTS WHERE` and end with `GO`.
- The `GET` clause goes INSIDE the object's square brackets, after the \
conditions, and lists the features to return (use g_word_utf8 and gloss to show \
the word and its meaning).
- Combine multiple conditions with AND inside the brackets.

Worked examples:
  Q: Find all Niphal verbs
  SELECT ALL OBJECTS WHERE [word sp=verb AND vs=nif GET g_word_utf8, gloss] GO

  Q: Where does the verb bara (to create) occur?
  SELECT ALL OBJECTS WHERE [word lex='BR>[' GET g_word_utf8, gloss, vs] GO

  Q: Where does bara occur, with the book, chapter and verse?
  SELECT ALL OBJECTS WHERE [verse GET book, chapter, verse \
[word lex='BR>[' GET g_word_utf8, gloss]] GO

VERSE REFERENCES (location). A word does not carry book/chapter/verse; those \
live on the verse around it. When the question asks WHERE something occurs, or \
asks for the reference/citation, nest the word query inside a verse: \
[verse GET book, chapter, verse [word <conditions> GET g_word_utf8, gloss]]. The \
matches are still the words, now each with its location. For a plain count or \
list with no location, keep the flat [word ...] form.

CRITICAL quoting rule:
- Enumeration features are compared UNQUOTED: write sp=verb, vs=nif (NOT \
sp='verb').
- String features are compared QUOTED: write lex='BR>[', gloss='create'.
Getting this wrong makes the query fail to compile.

BHSA feature reference (feature [kind]: gloss; values):
{reference}"""


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

from .feature_reference import FeatureReference

_MODEL = "claude-opus-4-8"

_INSTRUCTIONS = """You translate questions about the Hebrew Bible into Emdros \
MQL queries over the BHSA database. Output ONLY the MQL query, nothing else: no \
explanation, no code fences. Use only the features and values listed below. \
Prefer querying the appropriate object type (word, phrase, clause, sentence). \
Always end the query with GO. Add a GET clause listing the features needed to \
display results (e.g. GET sp, gloss).

BHSA feature reference (feature: gloss; valid values):
{reference}"""


def _reference_block(ref: FeatureReference) -> str:
    lines = []
    for name, spec in ref.features.items():
        values = spec.get("values")
        if values:
            vals = ", ".join(f"{k}={v}" for k, v in values.items())
            lines.append(f"- {name}: {spec['gloss']}; values: {vals}")
        else:
            lines.append(f"- {name}: {spec['gloss']}; (open value)")
    return "\n".join(lines)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    return t.strip()


def _default_client():
    import anthropic
    return anthropic.Anthropic()


def translate_to_mql(question: str, ref: FeatureReference, client=None) -> str:
    client = client or _default_client()
    system = _INSTRUCTIONS.format(reference=_reference_block(ref))
    msg = client.messages.create(
        model=_MODEL,
        max_tokens=1024,
        system=system,
        messages=[{"role": "user", "content": question}],
    )
    return _strip_fences(msg.content[0].text)

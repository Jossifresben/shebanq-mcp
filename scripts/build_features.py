"""Generate src/shebanq_mcp/features.json from the ETCBC BHSA feature docs.

The ETCBC publishes per-feature Markdown docs under bhsa/docs/features/. Each
documents a feature name, description, and (for enumerations) its value codes.
This script parses those docs into the features.json schema used at runtime.

Usage: python scripts/build_features.py <path-to-bhsa/docs/features> <out.json>

This is a build-time tool; runtime never imports it. Keep the hand-seeded
features.json as the source of truth until this generator is validated against
it (the seeded entries must round-trip identically).
"""
import json
import sys
from pathlib import Path


def parse_feature_doc(path: Path) -> dict | None:
    # ETCBC feature docs are Markdown. Extract the gloss (first description line)
    # and any value table. Doc structure varies; this parser targets the common
    # "## Values" table form and returns None for features without one.
    text = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    gloss = next((ln.lstrip("# ").strip() for ln in lines if not ln.startswith("#")), path.stem)
    values: dict[str, str] = {}
    in_values = False
    for ln in lines:
        if ln.lower().startswith("## value"):
            in_values = True
            continue
        if in_values and ln.startswith("|") and "|" in ln[1:]:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if len(cells) >= 2 and cells[0] not in ("value", "---", ""):
                values[cells[0]] = cells[1]
    return {"gloss": gloss, "values": values or None}


def main() -> None:
    docs_dir = Path(sys.argv[1])
    out = Path(sys.argv[2])
    features = {}
    for doc in sorted(docs_dir.glob("*.md")):
        parsed = parse_feature_doc(doc)
        if parsed:
            features[doc.stem] = parsed
    out.write_text(
        json.dumps({"version": "bhsa-2021", "features": features}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"wrote {len(features)} features to {out}")


if __name__ == "__main__":
    main()

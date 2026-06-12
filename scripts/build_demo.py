"""Inline demo/showcase.json into demo/template.html -> demo/index.html.

No database, no network; the TF equivalents are derived locally from the
feature catalogue. Re-run whenever showcase.json or template.html changes:

    .venv/bin/python scripts/build_demo.py

Note: use the venv Python, not system python3. System python3 may resolve
shebanq_mcp to a different, older checkout and raise an ImportError.
"""
import json
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "demo"


def augment_with_tf(showcase: dict) -> dict:
    """Attach the Text-Fabric equivalent (or the refusal reason) to each
    showcase search, derived deterministically from its MQL."""
    from shebanq_mcp.feature_reference import FeatureReference
    from shebanq_mcp.mql_to_tf import mql_to_tf
    from shebanq_mcp.tf_to_mql import ConversionError

    ref = FeatureReference.load()
    for s in showcase.get("searches", []):
        try:
            r = mql_to_tf(s["mql"], ref)
            s["tf"] = {"template": r.text, "notes": r.notes}
        except ConversionError as exc:
            s["tf"] = {"error": str(exc)}
    return showcase


def render(showcase: dict, template: str) -> str:
    return template.replace("{{DATA}}", json.dumps(showcase, ensure_ascii=False))


def main() -> None:
    showcase = json.loads((DEMO / "showcase.json").read_text(encoding="utf-8"))
    showcase = augment_with_tf(showcase)
    template = (DEMO / "template.html").read_text(encoding="utf-8")
    (DEMO / "index.html").write_text(render(showcase, template), encoding="utf-8")
    print(f"wrote {DEMO / 'index.html'}")


if __name__ == "__main__":
    main()

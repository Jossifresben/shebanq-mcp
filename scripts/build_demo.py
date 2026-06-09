"""Inline demo/showcase.json into demo/template.html -> demo/index.html.

Pure transform: no database, no network. Re-run whenever showcase.json changes:
    python scripts/build_demo.py
"""
import json
from pathlib import Path

DEMO = Path(__file__).resolve().parent.parent / "demo"


def render(showcase: dict, template: str) -> str:
    return template.replace("{{DATA}}", json.dumps(showcase, ensure_ascii=False))


def main() -> None:
    showcase = json.loads((DEMO / "showcase.json").read_text(encoding="utf-8"))
    template = (DEMO / "template.html").read_text(encoding="utf-8")
    (DEMO / "index.html").write_text(render(showcase, template), encoding="utf-8")
    print(f"wrote {DEMO / 'index.html'}")


if __name__ == "__main__":
    main()

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.build_demo import render  # noqa: E402

TEMPLATE = '<html><body><script>window.SHOWCASE = {{DATA}};</script></body></html>'

SHOWCASE = {
    "version": "bhsa-2021",
    "searches": [
        {
            "id": "x", "question": "Find Niphal verbs.",
            "mql": "SELECT ALL OBJECTS WHERE [word vs=nif] GO",
            "count": 4145,
            "samples": [{"hebrew": "ברא", "gloss": "create", "reference": None}],
        }
    ],
}


def test_render_inlines_data_and_drops_placeholder():
    out = render(SHOWCASE, TEMPLATE)
    assert "{{DATA}}" not in out
    assert "Find Niphal verbs." in out
    assert "vs=nif" in out
    assert "create" in out
    assert "4145" in out


def test_render_output_parses_back():
    out = render(SHOWCASE, TEMPLATE)
    blob = out.split("window.SHOWCASE = ", 1)[1].split(";</script>", 1)[0]
    assert json.loads(blob)["searches"][0]["count"] == 4145

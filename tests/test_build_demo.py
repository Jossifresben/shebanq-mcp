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


def test_render_derives_tf_for_each_search():
    from scripts.build_demo import augment_with_tf
    showcase = {"searches": [
        {"id": "a", "mql": "SELECT ALL OBJECTS WHERE [word sp=verb] GO"},
        {"id": "b", "mql": "SELECT ALL OBJECTS WHERE [word FOCUS sp=verb] GO"},
    ]}
    out = augment_with_tf(showcase)
    assert out["searches"][0]["tf"] == {"template": "word sp=verb", "notes": []}
    assert "cannot be converted" in out["searches"][1]["tf"]["error"]


def test_augment_with_assumptions():
    from scripts.build_demo import augment_with_assumptions
    showcase = {"searches": [
        {"id": "fem", "mql": "SELECT ALL OBJECTS WHERE [word sp=subs AND gn=f AND nu=pl GET g_word_utf8, gloss] GO"},
        {"id": "plain", "mql": "SELECT ALL OBJECTS WHERE [word sp=verb] GO"},
    ]}
    out = augment_with_assumptions(showcase)
    fem = out["searches"][0]["assumptions"]
    assert any("gender" in n.lower() for n in fem)
    assert any("dictionary" in n.lower() for n in fem)   # gloss via GET
    assert out["searches"][1].get("assumptions", []) == []

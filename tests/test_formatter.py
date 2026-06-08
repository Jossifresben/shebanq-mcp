from shebanq_mcp.formatter import format_results


def test_format_adds_reference_and_keeps_glosses():
    raw = [
        {"id_d": 1, "monad": 5, "sp": "verb", "vs": "qal", "gloss": "create",
         "book": "Genesis", "chapter": 1, "verse": 1},
    ]
    out = format_results(raw)
    assert out[0]["reference"] == "Genesis 1:1"
    assert out[0]["gloss"] == "create"
    assert out[0]["features"]["vs"] == "qal"


def test_format_handles_missing_locator_gracefully():
    raw = [{"id_d": 2, "monad": 9, "gloss": "x"}]
    out = format_results(raw)
    assert out[0]["reference"] is None
    assert out[0]["gloss"] == "x"

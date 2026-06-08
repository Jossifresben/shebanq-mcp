_RESERVED = {"id_d", "monad", "book", "chapter", "verse", "gloss", "text"}


def _reference(row: dict) -> str | None:
    book, chap, verse = row.get("book"), row.get("chapter"), row.get("verse")
    if book and chap and verse:
        return f"{book} {chap}:{verse}"
    return None


def format_results(raw: list[dict]) -> list[dict]:
    out = []
    for row in raw:
        features = {k: v for k, v in row.items() if k not in _RESERVED}
        out.append({
            "id_d": row.get("id_d"),
            "reference": _reference(row),
            "text": row.get("text"),
            "gloss": row.get("gloss"),
            "features": features,
        })
    return out

"""Generate demo/og.png (1200x630 Open Graph card). Run manually:
    python3 -m pip install pillow   # script-only dep, not a package dep
    python3 scripts/make_og_image.py
Unpointed Hebrew on purpose: vowel points need complex text shaping
(libraqm) that plain Pillow lacks; bare consonants render reliably. Pure
RTL text drawn by an LTR renderer needs reversing; text[::-1] is correct
for Hebrew-only strings (no digits, no mixed direction).
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "demo" / "og.png"
W, H = 1200, 630
BG, INK, ACCENT, MUTED = "#faf8f3", "#1a1a1a", "#7a5c2e", "#6b6b6b"

HEBREW = "בראשית ברא"[::-1]          # visual order for an LTR renderer
TITLE = "shebanq-mcp"
SUB = "Query the BHSA Hebrew Bible in plain language"
TAG = "AI as a way in, not a way around"

CANDIDATE_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",  # macOS; covers Latin + Hebrew
    "/System/Library/Fonts/ArialHB.ttc",                     # macOS Arial Hebrew (Hebrew only)
    "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",       # Linux
]


def load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in CANDIDATE_FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    raise SystemExit("no usable font found; edit CANDIDATE_FONTS")


def centered(draw, y, text, font, fill):
    w = draw.textlength(text, font=font)
    draw.text(((W - w) / 2, y), text, font=font, fill=fill)


def main() -> None:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=ACCENT)            # top accent bar
    d.rectangle([0, H - 10, W, H], fill=ACCENT)        # bottom accent bar
    centered(d, 110, HEBREW, load_font(150), INK)
    centered(d, 330, TITLE, load_font(64), ACCENT)
    centered(d, 420, SUB, load_font(36), INK)
    centered(d, 510, TAG, load_font(28), MUTED)
    img.save(OUT, "PNG")
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()

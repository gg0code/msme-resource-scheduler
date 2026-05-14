"""Brand header generator — v6.3.23 brand asset library.

FILE PURPOSE
Renders the eight WhatsApp HSM template IMAGE-header assets used by the
v6.3.23 brand asset library: one 640x335 PNG per brand category plus a
matching SVG source under _source/ for designer edits. The PNGs are
committed artifacts; the SVGs are committed as design provenance. Re-run
this script after editing the SPEC table (or the icon helpers) to
regenerate every asset in one pass.

Run from the repo root:
    python backend/scripts/generate_brand_headers.py

WHO CALLS THIS FILE
  - Human operator (once per design revision). Not imported by any
    runtime code path. The registry in
    app/services/whatsapp_template_assets.py points at the rendered
    PNGs, not at this script.

WHAT THIS FILE CALLS
  - PIL (Pillow) for PNG rasterisation. Tries arialbd.ttf (Win),
    DejaVuSans-Bold.ttf (Linux), Helvetica-Bold (Mac), then PIL's
    bitmap default. The committed PNGs were rendered with Arial Bold
    on Windows; subsequent re-renders on other platforms will produce
    visually close but not byte-identical output.

KEY DESIGN DECISIONS
  - Single source of truth is the SPEC table at the top of the module:
    eight rows of (key, hex, label, icon_fn). Editing one row + re-
    running this script is the entire design workflow.
  - SVG sources are hand-authored to mirror the PIL output shape-for-
    shape. They are not generated from the PIL canvas — exporting PIL
    primitives to SVG would lose the readable XML structure designers
    expect.
  - Icon geometry lives in pure-Python helper functions; no external
    icon library to keep this script trivially reproducible. Each
    helper draws into a fixed (ICON_CX, ICON_CY) center at radius
    ICON_R; tweak those constants to rebalance the layout.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

ASSETS_DIR = Path(__file__).resolve().parents[1] / "assets" / "whatsapp_headers"
SOURCE_DIR = ASSETS_DIR / "_source"

WIDTH, HEIGHT = 640, 335
ICON_CX, ICON_CY = 170, 167
ICON_R = 80
TEXT_CX = 430
ACCENT_BAR_HEIGHT = 14

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arialbd.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/Library/Fonts/Arial Bold.ttf",
    "/System/Library/Fonts/Helvetica.ttc",
]


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _hex_to_rgb(hex_rgb: str) -> tuple[int, int, int]:
    h = hex_rgb.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _accent(hex_rgb: str) -> tuple[int, int, int]:
    r, g, b = _hex_to_rgb(hex_rgb)
    return max(0, int(r * 0.7)), max(0, int(g * 0.7)), max(0, int(b * 0.7))


# ---------------------------------------------------------------------------
# Icon helpers — PIL
# ---------------------------------------------------------------------------

def _icon_sun(d: ImageDraw.ImageDraw, bg: tuple[int, int, int]) -> None:
    d.ellipse((ICON_CX - 42, ICON_CY - 42, ICON_CX + 42, ICON_CY + 42), fill="white")
    for i in range(8):
        a = i * math.pi / 4
        x1, y1 = ICON_CX + int(58 * math.cos(a)), ICON_CY + int(58 * math.sin(a))
        x2, y2 = ICON_CX + int(78 * math.cos(a)), ICON_CY + int(78 * math.sin(a))
        d.line((x1, y1, x2, y2), fill="white", width=7)


def _icon_moon(d: ImageDraw.ImageDraw, bg: tuple[int, int, int]) -> None:
    d.ellipse((ICON_CX - 60, ICON_CY - 60, ICON_CX + 60, ICON_CY + 60), fill="white")
    d.ellipse((ICON_CX - 22, ICON_CY - 64, ICON_CX + 98, ICON_CY + 56), fill=bg)


def _icon_document(d: ImageDraw.ImageDraw, bg: tuple[int, int, int]) -> None:
    d.rounded_rectangle(
        (ICON_CX - 50, ICON_CY - 62, ICON_CX + 50, ICON_CY + 62),
        radius=12, outline="white", width=7,
    )
    for offset in (-30, -10, 10, 30):
        d.line(
            (ICON_CX - 30, ICON_CY + offset, ICON_CX + 30, ICON_CY + offset),
            fill="white", width=5,
        )


def _icon_trend_up(d: ImageDraw.ImageDraw, bg: tuple[int, int, int]) -> None:
    # Diagonal arrow from bottom-left to top-right + arrowhead.
    d.line(
        (ICON_CX - 60, ICON_CY + 50, ICON_CX + 60, ICON_CY - 50),
        fill="white", width=9,
    )
    # Arrowhead — small triangle at top-right end.
    d.polygon(
        [
            (ICON_CX + 60, ICON_CY - 50),
            (ICON_CX + 30, ICON_CY - 55),
            (ICON_CX + 55, ICON_CY - 20),
        ],
        fill="white",
    )
    # Baseline tick at bottom-left for visual grounding.
    d.line(
        (ICON_CX - 70, ICON_CY + 60, ICON_CX + 70, ICON_CY + 60),
        fill="white", width=5,
    )


def _icon_alert(d: ImageDraw.ImageDraw, bg: tuple[int, int, int]) -> None:
    d.polygon(
        [
            (ICON_CX, ICON_CY - 65),
            (ICON_CX - 70, ICON_CY + 55),
            (ICON_CX + 70, ICON_CY + 55),
        ],
        fill="white",
    )
    # Exclamation: vertical stem + dot, drawn in bg colour.
    d.rectangle(
        (ICON_CX - 6, ICON_CY - 30, ICON_CX + 6, ICON_CY + 20),
        fill=bg,
    )
    d.ellipse(
        (ICON_CX - 7, ICON_CY + 30, ICON_CX + 7, ICON_CY + 44),
        fill=bg,
    )


def _icon_user_plus(d: ImageDraw.ImageDraw, bg: tuple[int, int, int]) -> None:
    # Head.
    d.ellipse((ICON_CX - 28, ICON_CY - 60, ICON_CX + 28, ICON_CY - 4), fill="white")
    # Shoulders/body.
    d.pieslice(
        (ICON_CX - 55, ICON_CY - 10, ICON_CX + 55, ICON_CY + 90),
        start=180, end=360, fill="white",
    )
    # Plus sign top-right.
    plus_cx, plus_cy = ICON_CX + 50, ICON_CY - 50
    d.rectangle((plus_cx - 14, plus_cy - 4, plus_cx + 14, plus_cy + 4), fill="white")
    d.rectangle((plus_cx - 4, plus_cy - 14, plus_cx + 4, plus_cy + 14), fill="white")


def _icon_calculator(d: ImageDraw.ImageDraw, bg: tuple[int, int, int]) -> None:
    d.rounded_rectangle(
        (ICON_CX - 50, ICON_CY - 64, ICON_CX + 50, ICON_CY + 64),
        radius=10, fill="white",
    )
    # Display strip.
    d.rectangle(
        (ICON_CX - 38, ICON_CY - 52, ICON_CX + 38, ICON_CY - 30),
        fill=bg,
    )
    # 3x3 button grid.
    for row in range(3):
        for col in range(3):
            x = ICON_CX - 38 + col * 28
            y = ICON_CY - 18 + row * 28
            d.rectangle((x, y, x + 18, y + 18), fill=bg)


def _icon_check(d: ImageDraw.ImageDraw, bg: tuple[int, int, int]) -> None:
    d.ellipse((ICON_CX - 70, ICON_CY - 70, ICON_CX + 70, ICON_CY + 70), fill="white")
    # Checkmark — two line segments forming a tick.
    d.line(
        (ICON_CX - 30, ICON_CY + 5, ICON_CX - 8, ICON_CY + 30),
        fill=bg, width=10,
    )
    d.line(
        (ICON_CX - 8, ICON_CY + 30, ICON_CX + 35, ICON_CY - 22),
        fill=bg, width=10,
    )


# ---------------------------------------------------------------------------
# Icon helpers — SVG (mirror the PIL output shape-for-shape)
# ---------------------------------------------------------------------------

def _svg_sun() -> str:
    out = [f'<circle cx="{ICON_CX}" cy="{ICON_CY}" r="42" fill="white"/>']
    for i in range(8):
        a = i * math.pi / 4
        x1, y1 = ICON_CX + 58 * math.cos(a), ICON_CY + 58 * math.sin(a)
        x2, y2 = ICON_CX + 78 * math.cos(a), ICON_CY + 78 * math.sin(a)
        out.append(
            f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" '
            f'stroke="white" stroke-width="7" stroke-linecap="round"/>'
        )
    return "\n  ".join(out)


def _svg_moon(bg_hex: str) -> str:
    return (
        f'<circle cx="{ICON_CX}" cy="{ICON_CY}" r="60" fill="white"/>\n  '
        f'<ellipse cx="{ICON_CX + 38}" cy="{ICON_CY - 4}" rx="60" ry="60" fill="{bg_hex}"/>'
    )


def _svg_document() -> str:
    rows = "\n  ".join(
        f'<line x1="{ICON_CX - 30}" y1="{ICON_CY + o}" x2="{ICON_CX + 30}" y2="{ICON_CY + o}" '
        f'stroke="white" stroke-width="5"/>'
        for o in (-30, -10, 10, 30)
    )
    return (
        f'<rect x="{ICON_CX - 50}" y="{ICON_CY - 62}" width="100" height="124" '
        f'rx="12" fill="none" stroke="white" stroke-width="7"/>\n  '
        f'{rows}'
    )


def _svg_trend_up() -> str:
    return (
        f'<line x1="{ICON_CX - 60}" y1="{ICON_CY + 50}" x2="{ICON_CX + 60}" y2="{ICON_CY - 50}" '
        f'stroke="white" stroke-width="9" stroke-linecap="round"/>\n  '
        f'<polygon points="{ICON_CX + 60},{ICON_CY - 50} {ICON_CX + 30},{ICON_CY - 55} '
        f'{ICON_CX + 55},{ICON_CY - 20}" fill="white"/>\n  '
        f'<line x1="{ICON_CX - 70}" y1="{ICON_CY + 60}" x2="{ICON_CX + 70}" y2="{ICON_CY + 60}" '
        f'stroke="white" stroke-width="5"/>'
    )


def _svg_alert(bg_hex: str) -> str:
    return (
        f'<polygon points="{ICON_CX},{ICON_CY - 65} {ICON_CX - 70},{ICON_CY + 55} '
        f'{ICON_CX + 70},{ICON_CY + 55}" fill="white"/>\n  '
        f'<rect x="{ICON_CX - 6}" y="{ICON_CY - 30}" width="12" height="50" fill="{bg_hex}"/>\n  '
        f'<circle cx="{ICON_CX}" cy="{ICON_CY + 37}" r="7" fill="{bg_hex}"/>'
    )


def _svg_user_plus() -> str:
    return (
        f'<ellipse cx="{ICON_CX}" cy="{ICON_CY - 32}" rx="28" ry="28" fill="white"/>\n  '
        f'<path d="M {ICON_CX - 55} {ICON_CY + 40} '
        f'a 55 50 0 0 1 110 0 Z" fill="white"/>\n  '
        f'<rect x="{ICON_CX + 36}" y="{ICON_CY - 54}" width="28" height="8" fill="white"/>\n  '
        f'<rect x="{ICON_CX + 46}" y="{ICON_CY - 64}" width="8" height="28" fill="white"/>'
    )


def _svg_calculator(bg_hex: str) -> str:
    buttons = "\n  ".join(
        f'<rect x="{ICON_CX - 38 + col * 28}" y="{ICON_CY - 18 + row * 28}" '
        f'width="18" height="18" fill="{bg_hex}"/>'
        for row in range(3) for col in range(3)
    )
    return (
        f'<rect x="{ICON_CX - 50}" y="{ICON_CY - 64}" width="100" height="128" '
        f'rx="10" fill="white"/>\n  '
        f'<rect x="{ICON_CX - 38}" y="{ICON_CY - 52}" width="76" height="22" fill="{bg_hex}"/>\n  '
        f'{buttons}'
    )


def _svg_check(bg_hex: str) -> str:
    return (
        f'<circle cx="{ICON_CX}" cy="{ICON_CY}" r="70" fill="white"/>\n  '
        f'<polyline points="{ICON_CX - 30},{ICON_CY + 5} {ICON_CX - 8},{ICON_CY + 30} '
        f'{ICON_CX + 35},{ICON_CY - 22}" '
        f'fill="none" stroke="{bg_hex}" stroke-width="10" '
        f'stroke-linecap="round" stroke-linejoin="round"/>'
    )


# ---------------------------------------------------------------------------
# SPEC — single source of truth
# ---------------------------------------------------------------------------

SPEC: list[tuple[str, str, str, Callable, Callable]] = [
    ("morning_briefing",   "#185FA5", "MORNING BRIEFING", _icon_sun,        lambda hex_: _svg_sun()),
    ("evening_summary",    "#3C3489", "EVENING SUMMARY",  _icon_moon,       _svg_moon),
    ("compliance_reminder","#BA7517", "COMPLIANCE",       _icon_document,   lambda hex_: _svg_document()),
    ("savings_summary",    "#0F6E56", "SAVINGS",          _icon_trend_up,   lambda hex_: _svg_trend_up()),
    ("conflict_alert",     "#A32D2D", "ALERT",            _icon_alert,      _svg_alert),
    ("team_invite",        "#534AB7", "INVITE",           _icon_user_plus,  lambda hex_: _svg_user_plus()),
    ("material_estimate",  "#D85A30", "ESTIMATE",         _icon_calculator, _svg_calculator),
    ("day7_first_insight", "#1D9E75", "DAY 7",            _icon_check,      _svg_check),
]


def _render_png(name: str, bg_hex: str, label: str, icon_fn: Callable) -> None:
    bg_rgb = _hex_to_rgb(bg_hex)
    accent_rgb = _accent(bg_hex)

    img = Image.new("RGB", (WIDTH, HEIGHT), color=bg_rgb)
    d = ImageDraw.Draw(img)

    # Bottom accent bar.
    d.rectangle(
        (0, HEIGHT - ACCENT_BAR_HEIGHT, WIDTH, HEIGHT),
        fill=accent_rgb,
    )

    icon_fn(d, bg_rgb)

    # Label — fit to the right text area. Start at 56pt, shrink to fit.
    font = None
    text_size = 56
    while text_size >= 28:
        font = _load_font(text_size)
        bbox = d.textbbox((0, 0), label, font=font)
        text_w = bbox[2] - bbox[0]
        if text_w <= 360:
            break
        text_size -= 2

    bbox = d.textbbox((0, 0), label, font=font)
    text_w, text_h = bbox[2] - bbox[0], bbox[3] - bbox[1]
    text_x = TEXT_CX - text_w // 2
    text_y = (HEIGHT - text_h) // 2 - bbox[1] - 6  # subtract baseline offset
    d.text((text_x, text_y), label, font=font, fill="white")

    # Small ZetaOps wordmark under the label for brand attribution.
    wm_font = _load_font(20)
    wm = "ZetaOps"
    wm_bbox = d.textbbox((0, 0), wm, font=wm_font)
    wm_w = wm_bbox[2] - wm_bbox[0]
    d.text(
        (TEXT_CX - wm_w // 2, HEIGHT - ACCENT_BAR_HEIGHT - 32),
        wm,
        font=wm_font,
        fill=(255, 255, 255, 200),
    )

    out_path = ASSETS_DIR / f"{name}.png"
    img.save(out_path, format="PNG", optimize=True)
    print(f"  wrote {out_path.relative_to(ASSETS_DIR.parent.parent)}")


def _render_svg(name: str, bg_hex: str, label: str, svg_icon_fn: Callable) -> None:
    accent_rgb = _accent(bg_hex)
    accent_hex = f"#{accent_rgb[0]:02x}{accent_rgb[1]:02x}{accent_rgb[2]:02x}"
    icon_xml = svg_icon_fn(bg_hex)
    svg = f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {WIDTH} {HEIGHT}" width="{WIDTH}" height="{HEIGHT}">
  <!-- v6.3.23 brand header source. Re-run backend/scripts/generate_brand_headers.py to refresh the PNG. -->
  <rect x="0" y="0" width="{WIDTH}" height="{HEIGHT}" fill="{bg_hex}"/>
  <rect x="0" y="{HEIGHT - ACCENT_BAR_HEIGHT}" width="{WIDTH}" height="{ACCENT_BAR_HEIGHT}" fill="{accent_hex}"/>
  {icon_xml}
  <text x="{TEXT_CX}" y="{HEIGHT // 2 + 12}" font-family="Arial, Helvetica, sans-serif"
        font-weight="bold" font-size="52" fill="white" text-anchor="middle">{label}</text>
  <text x="{TEXT_CX}" y="{HEIGHT - ACCENT_BAR_HEIGHT - 18}" font-family="Arial, Helvetica, sans-serif"
        font-weight="bold" font-size="18" fill="white" fill-opacity="0.8" text-anchor="middle">ZetaOps</text>
</svg>
"""
    out_path = SOURCE_DIR / f"{name}.svg"
    out_path.write_text(svg, encoding="utf-8")
    print(f"  wrote {out_path.relative_to(SOURCE_DIR.parent.parent)}")


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Rendering {len(SPEC)} brand headers into {ASSETS_DIR}")
    for name, bg_hex, label, icon_fn, svg_icon_fn in SPEC:
        _render_png(name, bg_hex, label, icon_fn)
        _render_svg(name, bg_hex, label, svg_icon_fn)
    print("Done.")


if __name__ == "__main__":
    main()

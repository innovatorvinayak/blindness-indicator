"""The drscreen mark: a rendered (not just decorative-canvas) logo.

Rendered once with PIL at 4x and downsampled (supersampling — Tk/PIL have no
native anti-aliased vector drawing), so it stays crisp at every size from a
16px window-titlebar icon up to a 512px report header. The design reads as a
retina under examination: an outer aperture ring, an iris arc standing in for
the screening sweep, and a pupil — the same visual idea as the animated
``RetinaGlyph`` on-screen, given a fixed, exportable form for places an
animated canvas can't go (the OS window icon, the HTML report).
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw

from drscreen.gui.theme import EMERALD, PALETTE, darken, lighten, mix

SUPERSAMPLE = 4


@lru_cache(maxsize=8)
def render_logo(size: int = 256) -> Image.Image:
    """Render the mark as an RGBA image, ``size`` x ``size`` pixels."""
    s = size * SUPERSAMPLE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = s / 2

    # Rounded-square emerald tile with a subtle top-left highlight, so it
    # reads as a glossy app icon rather than a flat sticker.
    pad = s * 0.04
    radius = s * 0.24
    draw.rounded_rectangle([pad, pad, s - pad, s - pad], radius=radius,
                          fill=_hex(EMERALD))
    _diagonal_sheen(img, s, pad, radius)

    # Outer aperture ring (cream) and a fainter inner ring, echoing the
    # animated brand glyph used elsewhere in the app.
    for scale, width, color in ((0.72, 0.045, PALETTE.accent),
                               (0.58, 0.022, mix(PALETTE.accent, EMERALD, 0.35))):
        r = s / 2 * scale
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=_hex(color),
                    width=max(1, int(s * width)))

    # A quarter-arc "scan" sweep, thicker and warmer, standing in for the
    # rotating scan wedge in the live UI.
    r = s / 2 * 0.72
    bbox = [cx - r, cy - r, cx + r, cy + r]
    draw.arc(bbox, start=-40, end=50, fill=_hex(PALETTE.gold), width=max(2, int(s * 0.05)))

    # Pupil/core.
    core_r = s / 2 * 0.20
    draw.ellipse([cx - core_r, cy - core_r, cx + core_r, cy + core_r],
                fill=_hex(darken(PALETTE.accent, 0.05)))
    highlight_r = core_r * 0.35
    hx, hy = cx - core_r * 0.35, cy - core_r * 0.35
    draw.ellipse([hx - highlight_r, hy - highlight_r, hx + highlight_r, hy + highlight_r],
                fill=_hex(lighten(PALETTE.accent, 0.5)))

    return img.resize((size, size), Image.LANCZOS)


def render_logo_png_bytes(size: int = 256) -> bytes:
    buf = BytesIO()
    render_logo(size).save(buf, format="PNG")
    return buf.getvalue()


def _diagonal_sheen(img: Image.Image, s: float, pad: float, radius: float) -> None:
    """A soft light-to-dark wash, the cheap version of a glossy bevel.

    Drawn on a transparent overlay and composited through a rounded-rect mask,
    so the bands never square off the icon's rounded corners.
    """
    size = (int(s), int(s))
    overlay = Image.new("RGBA", size, (0, 0, 0, 0))
    band = ImageDraw.Draw(overlay)
    steps = 24
    for i in range(steps):
        t = i / steps
        color = mix(lighten(EMERALD, 0.18), darken(EMERALD, 0.10), t)
        y0 = pad + (s - 2 * pad) * t
        y1 = pad + (s - 2 * pad) * (t + 1 / steps)
        band.rectangle([pad, y0, s - pad, y1], fill=(*_hex(color), 255))

    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, s - pad, s - pad], radius=radius, fill=255)
    img.paste(overlay, (0, 0), mask)


def _hex(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

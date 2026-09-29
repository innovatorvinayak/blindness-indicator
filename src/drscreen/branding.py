"""The DRSCREEN mark, rendered with PIL.

Same design as the SVG in the web UI (``frontend/src/components/Logo.tsx``):
an aperture closing around an iris — six blades on an outer ring, a
cyan→violet iris, and a bright fovea core. This raster version exists for
the places an SVG can't go: the favicon and the exported HTML report header.

Drawn at 4x and downsampled (supersampling), since PIL has no anti-aliased
vector drawing of its own.
"""

from __future__ import annotations

from functools import lru_cache
from io import BytesIO

from PIL import Image, ImageDraw

from drscreen.theme import CYAN, VIOLET, VOID, lighten, mix

SUPERSAMPLE = 4


@lru_cache(maxsize=8)
def render_logo(size: int = 256) -> Image.Image:
    """Render the mark as an RGBA image, ``size`` x ``size`` pixels."""
    s = size * SUPERSAMPLE
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx = cy = s / 2

    # Dark rounded tile so the mark reads on light backgrounds too (the
    # report header is cream, the favicon sits on whatever the browser uses).
    pad = s * 0.04
    draw.rounded_rectangle([pad, pad, s - pad, s - pad], radius=s * 0.24, fill=_rgb(VOID))

    # Six aperture blades: short arcs evenly spaced around the outer ring,
    # each tinted along the cyan -> violet axis by its angle.
    blade_box = _box(cx, cy, s / 2 * 0.80)
    for i in range(6):
        start = i * 60 - 38
        draw.arc(blade_box, start=start, end=start + 40,
                 fill=_rgb(mix(CYAN, VIOLET, i / 5)), width=max(2, int(s * 0.030)))

    # Iris: a filled disc under a crisp ring.
    iris_r = s / 2 * 0.44
    draw.ellipse(_box(cx, cy, iris_r), fill=(*_rgb(mix(CYAN, VIOLET, 0.5)), 64))
    draw.ellipse(_box(cx, cy, iris_r), outline=_rgb(mix(CYAN, VIOLET, 0.35)),
                 width=max(2, int(s * 0.020)))

    # Fovea: a soft cyan bloom with a white centre.
    _radial_bloom(img, cx, cy, s / 2 * 0.26, CYAN)
    core_r = s / 2 * 0.085
    draw.ellipse(_box(cx, cy, core_r), fill=_rgb(lighten(CYAN, 0.82)))

    return img.resize((size, size), Image.LANCZOS)


def render_logo_png_bytes(size: int = 256) -> bytes:
    buf = BytesIO()
    render_logo(size).save(buf, format="PNG")
    return buf.getvalue()


def _box(cx: float, cy: float, r: float) -> list[float]:
    return [cx - r, cy - r, cx + r, cy + r]


def _radial_bloom(img: Image.Image, cx: float, cy: float, r: float, color: str) -> None:
    """A soft glow, drawn as concentric rings of decreasing alpha — PIL has
    no radial-gradient primitive."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    steps = 26
    for i in range(steps, 0, -1):
        t = i / steps
        alpha = int(150 * (1 - t) ** 1.6)
        draw.ellipse(_box(cx, cy, r * t), fill=(*_rgb(color), alpha))
    img.alpha_composite(overlay)


def _rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]

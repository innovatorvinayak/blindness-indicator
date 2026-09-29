"""Brand tokens and colour maths for the "Deep Field" theme.

Three brand constants — a near-black void, electric cyan as the signal
colour, and violet as its counterweight — generate every other chrome tone,
so re-branding is a three-line edit here.

One deliberate exception: the five clinical **grade** colours (0-4) keep
green→amber→red semantics rather than brand colours. Recolouring "this
patient needs urgent referral" to match a palette would trade clinical
legibility for house style, which is the wrong trade in a screening tool.

The web UI (``frontend/``) declares the same tokens in its own CSS, since a
Next.js build can't import Python. This module is the source of truth for
everything rendered *by Python*: the logo in :mod:`drscreen.branding` and the
exported HTML report in :mod:`drscreen.reporting`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# The brand constants everything else is derived from.
# ---------------------------------------------------------------------------
VOID = "#05070F"
CYAN = "#22D3EE"
VIOLET = "#8B5CF6"


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    r, g, b = (max(0, min(255, round(c))) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(color_a: str, color_b: str, t: float) -> str:
    """Linear-interpolate between two hex colours. t=0 -> a, t=1 -> b."""
    t = max(0.0, min(1.0, t))
    a, b = hex_to_rgb(color_a), hex_to_rgb(color_b)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))


def darken(color: str, amount: float) -> str:
    """Blend a colour toward black by ``amount`` (0..1)."""
    return mix(color, "#000000", amount)


def lighten(color: str, amount: float) -> str:
    """Blend a colour toward white by ``amount`` (0..1)."""
    return mix(color, "#ffffff", amount)


def _build_tokens() -> dict[str, str]:
    return {
        "bg0": VOID,
        "bg1": mix(VOID, CYAN, 0.03),
        "bg2": mix(VOID, CYAN, 0.07),
        "surface": mix(VOID, CYAN, 0.05),
        "surface_hi": mix(VOID, CYAN, 0.12),
        "border": mix(VOID, CYAN, 0.22),
        "border_soft": mix(VOID, CYAN, 0.13),
        "ink": "#E6EDF7",
        "ink_dim": "#8FA3BF",
        "ink_faint": "#5B6C87",
        # Buttons filled with the accent need dark text on top of them.
        "ink_on_accent": VOID,
        "accent": CYAN,
        "accent_dim": mix(CYAN, VOID, 0.40),
        "accent_soft": mix(VOID, CYAN, 0.14),
        "secondary": VIOLET,
        "magenta": "#E879F9",
    }


@dataclass(frozen=True)
class Palette:
    bg0: str
    bg1: str
    bg2: str
    surface: str
    surface_hi: str
    border: str
    border_soft: str

    ink: str
    ink_dim: str
    ink_faint: str
    ink_on_accent: str

    accent: str
    accent_dim: str
    accent_soft: str
    secondary: str
    magenta: str

    # Clinical grade colours — intentionally NOT derived from the brand
    # palette; see the module docstring.
    grade0: str = "#2DE2A6"
    grade1: str = "#A3E635"
    grade2: str = "#FBBF24"
    grade3: str = "#FB923C"
    grade4: str = "#FF4D6D"
    danger: str = "#FF4D6D"
    success: str = "#2DE2A6"

    void: str = field(default=VOID)
    cyan: str = field(default=CYAN)
    violet: str = field(default=VIOLET)


PALETTE = Palette(**_build_tokens())

GRADE_COLORS = (PALETTE.grade0, PALETTE.grade1, PALETTE.grade2, PALETTE.grade3, PALETTE.grade4)


def grade_color(grade: int) -> str:
    return GRADE_COLORS[grade]

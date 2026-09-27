"""Design tokens and colour math for the "Emerald & Ivory" theme.

The whole palette is *derived* from two brand colours — a deep emerald
(``EMERALD``) and a warm ivory/cream (``CREAM``) — rather than hand-picked
per token. That keeps the theme internally consistent and makes it a one-line
change to re-brand: edit the two constants below and every surface, border,
text tone and button state is recomputed from them.

One deliberate exception: the five clinical **grade** colours (0-4) are kept
as standard red/amber/green semantics, not brand colours. Recolouring "this
patient needs urgent referral" to match a decor palette would trade clinical
legibility for house style, which is the wrong trade in a medical screening
tool — so brand colour controls chrome (backgrounds, buttons, glows), and
grade colour stays universally readable.

Tkinter has no real alpha compositing on non-toplevel widgets, so "glow" and
"glass" effects are faked by blending colours toward the background at draw
time (see :func:`mix`). Pure stdlib — no extra dependencies for a design
system built from scratch on top of ``tkinter.Canvas``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# The two brand colours everything else is derived from.
# ---------------------------------------------------------------------------
EMERALD = "#064E3B"
CREAM = "#F8E7C9"


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


def ease_out_cubic(t: float) -> float:
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def ease_in_out_sine(t: float) -> float:
    t = max(0.0, min(1.0, t))
    import math

    return -(math.cos(math.pi * t) - 1) / 2


def _build_tokens() -> dict[str, str]:
    """Derive every surface/text/accent tone from EMERALD and CREAM alone."""
    gold = mix("#caa227", CREAM, 0.12)          # a warm metallic accent in the same family
    jade = lighten(EMERALD, 0.30)                # a brighter cousin of emerald, for variety
    bg2 = darken(EMERALD, 0.66)
    border = darken(mix(EMERALD, CREAM, 0.28), 0.12)
    return {
        # Surfaces: progressively lighter tints of emerald, darkest first.
        "bg0": darken(EMERALD, 0.90),
        "bg1": darken(EMERALD, 0.80),
        "bg2": bg2,
        # "surface" is the frosted-glass panel tone (Apple-style
        # glassmorphism): every existing card, and every ttk style built on
        # it, already references this one token, so deriving it as the
        # translucent-looking glass fill (instead of a flat dark tint) makes
        # the whole app read as glass with no other call sites to touch.
        "surface": mix(darken(EMERALD, 0.33), CREAM, 0.11),
        "surface_hi": darken(EMERALD, 0.38),
        "border": border,
        # Halfway between the full border and bg2, so a subtle outline (e.g.
        # the empty image dropzone) still reads against its own fill instead
        # of disappearing into it.
        "border_soft": mix(border, bg2, 0.5),
        # Text: ivory at full strength, then dimmed by blending toward bg1.
        "ink": CREAM,
        "ink_dim": mix(CREAM, darken(EMERALD, 0.80), 0.42),
        "ink_faint": mix(CREAM, darken(EMERALD, 0.80), 0.56),
        "ink_on_cream": darken(EMERALD, 0.10),
        # Accents: cream is the primary CTA/glow colour; gold and jade give
        # the background orbs and secondary highlights variety without
        # leaving the emerald/cream family.
        "accent": CREAM,
        "accent_dim": mix(CREAM, EMERALD, 0.35),
        "accent_soft": mix(darken(EMERALD, 0.80), CREAM, 0.10),
        "secondary": jade,
        "gold": gold,
        # The rest of the glass look: a bright hairline top/left edge to
        # catch light like a glass rim, a dimmer bottom/right edge for
        # depth, and a dark tone for the panel's soft blended shadow.
        "glass_edge_light": mix(CREAM, darken(EMERALD, 0.33), 0.35),
        "glass_edge_dark": darken(EMERALD, 0.62),
        "glass_shadow": darken(EMERALD, 0.95),
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
    ink_on_cream: str

    accent: str
    accent_dim: str
    accent_soft: str
    secondary: str
    gold: str

    glass_edge_light: str
    glass_edge_dark: str
    glass_shadow: str

    # Clinical grade colours — intentionally NOT derived from the brand
    # palette; see the module docstring.
    grade0: str = "#2fd480"
    grade1: str = "#8fd13a"
    grade2: str = "#f2c14e"
    grade3: str = "#f0913b"
    grade4: str = "#f0495c"
    danger: str = "#f0495c"
    success: str = "#2fd480"

    font_family: str = "Helvetica Neue"
    serif_family: str = "Georgia"
    mono_family: str = "Menlo"

    emerald: str = field(default=EMERALD)
    cream: str = field(default=CREAM)


PALETTE = Palette(**_build_tokens())


def grade_color(grade: int) -> str:
    return (PALETTE.grade0, PALETTE.grade1, PALETTE.grade2, PALETTE.grade3, PALETTE.grade4)[grade]


def configure_ttk(style, palette: Palette = PALETTE) -> None:
    """Configure the Emerald & Ivory ttk theme. Call once per Tk root."""
    if "clam" in style.theme_names():
        style.theme_use("clam")

    base_font = (palette.font_family, 12)
    style.configure(".", background=palette.bg1, foreground=palette.ink, font=base_font,
                    borderwidth=0, focuscolor=palette.accent)

    style.configure("App.TFrame", background=palette.bg1)
    style.configure("Card.TFrame", background=palette.surface)
    style.configure("Transparent.TFrame", background=palette.surface)

    style.configure("Card.TLabel", background=palette.surface, foreground=palette.ink)
    style.configure("CardMuted.TLabel", background=palette.surface, foreground=palette.ink_dim,
                    font=(palette.font_family, 11))
    style.configure("CardTitle.TLabel", background=palette.surface, foreground=palette.ink,
                    font=(palette.font_family, 14, "bold"))
    style.configure("Header.TLabel", background=palette.bg1, foreground=palette.ink,
                    font=(palette.font_family, 19, "bold"))
    style.configure("Muted.TLabel", background=palette.bg1, foreground=palette.ink_dim,
                    font=(palette.font_family, 11))
    style.configure("Error.TLabel", background=palette.surface, foreground=palette.danger)
    style.configure("Warn.TLabel", background=palette.surface, foreground=palette.gold)

    style.configure("TEntry", fieldbackground=palette.bg2, background=palette.bg2,
                    foreground=palette.ink, insertcolor=palette.ink, bordercolor=palette.border,
                    lightcolor=palette.border, darkcolor=palette.border, padding=8)
    style.map("TEntry", bordercolor=[("focus", palette.accent)],
             fieldbackground=[("disabled", palette.bg1)])

    style.configure("TCombobox", fieldbackground=palette.bg2, background=palette.bg2,
                    foreground=palette.ink, arrowcolor=palette.ink_dim,
                    bordercolor=palette.border, padding=6)
    style.map("TCombobox", fieldbackground=[("readonly", palette.bg2)],
             foreground=[("readonly", palette.ink)])
    style.configure("Card.TCheckbutton", background=palette.surface, foreground=palette.ink_dim)
    style.map("Card.TCheckbutton", background=[("active", palette.surface)])

    style.configure("Treeview", background=palette.bg2, fieldbackground=palette.bg2,
                    foreground=palette.ink, rowheight=28, borderwidth=0,
                    font=(palette.font_family, 11))
    style.configure("Treeview.Heading", background=palette.surface_hi, foreground=palette.ink_dim,
                    font=(palette.font_family, 10, "bold"), borderwidth=0, relief="flat")
    style.map("Treeview", background=[("selected", palette.accent_soft)],
             foreground=[("selected", palette.ink)])
    style.map("Treeview.Heading", background=[("active", palette.surface_hi)])
    style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])

    style.configure("Vertical.TScrollbar", background=palette.surface_hi,
                    troughcolor=palette.bg1, bordercolor=palette.bg1, arrowcolor=palette.ink_dim)
    style.map("Vertical.TScrollbar", background=[("active", palette.border)])

"""Hand-built animated widgets on plain ``tk.Canvas``.

Tkinter ships no animation, alpha blending, or rounded shapes, so this module
provides the small set of primitives the premium UI needs: rounded rectangles,
a hover/press-animated button, a value-animated progress bar, a pulsing status
dot, a rotating brand glyph, and a drifting-particle background. Every looping
widget cancels its own ``after()`` jobs on ``<Destroy>`` so closing a view never
leaves a callback firing against a dead widget.
"""

from __future__ import annotations

import contextlib
import math
import random
import tkinter as tk
from collections.abc import Callable
from typing import ClassVar

import customtkinter as ctk

from drscreen.gui.theme import PALETTE, Palette, darken, ease_out_cubic, mix

FPS_MS = 33  # ~30fps: smooth enough for UI chrome, light on CPU


class AnimatedWidget(tk.Canvas):
    """Base class that tracks and safely tears down `after()` animation jobs."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, highlightthickness=0, bd=0, **kwargs)
        self._jobs: dict[str, str] = {}
        self._alive = True
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _tick(self, name: str, delay: int, fn: Callable[[], None]) -> None:
        if not self._alive:
            return
        fn()
        self._jobs[name] = self.after(delay, self._tick, name, delay, fn)

    def _start_loop(self, name: str, fn: Callable[[], None], delay: int = FPS_MS) -> None:
        self._stop_loop(name)
        self._tick(name, delay, fn)

    def _stop_loop(self, name: str) -> None:
        job = self._jobs.pop(name, None)
        if job is not None:
            with contextlib.suppress(tk.TclError):
                self.after_cancel(job)

    def _on_destroy(self, _event=None) -> None:
        self._alive = False
        for job in self._jobs.values():
            with contextlib.suppress(tk.TclError):
                self.after_cancel(job)
        self._jobs.clear()

    def _bind_stretch(self, redraw: Callable[[int, int], None]) -> None:
        """Redraw this widget's shapes whenever its *allocated* size changes —
        i.e. when a geometry manager gives it more or less room (``fill="x"``,
        a resized window), not just when someone sets its ``width=`` option."""
        def on_configure(event: tk.Event) -> None:
            w, h = max(event.width, 1), max(event.height, 1)
            if abs(w - self._cw) < 1 and abs(h - self._ch) < 1:
                return
            self._cw, self._ch = w, h
            redraw(w, h)
        self.bind("<Configure>", on_configure, add="+")


def _round_rect_points(x1: float, y1: float, x2: float, y2: float,
                       radius: float) -> list[float]:
    r = min(radius, (x2 - x1) / 2, (y2 - y1) / 2) if x2 > x1 and y2 > y1 else 0
    return [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]


def round_rect(canvas: tk.Canvas, x1: float, y1: float, x2: float, y2: float,
              radius: float = 16, **kwargs) -> int:
    """Draw a rounded rectangle as a smoothed polygon; returns the item id."""
    return canvas.create_polygon(_round_rect_points(x1, y1, x2, y2, radius),
                                 smooth=True, **kwargs)


class CanvasButton(AnimatedWidget):
    """A rounded, hover/press-animated button. No native ttk chrome anywhere.

    Pass ``responsive=True`` (and pack/grid it with ``fill="x"``/``sticky="ew"``)
    to have it redraw at whatever width its container actually allocates,
    instead of staying pinned to its construction-time ``width``.
    """

    VARIANTS: ClassVar[dict[str, dict[str, str]]] = {
        "primary": dict(fill=PALETTE.accent, text=PALETTE.ink_on_cream,
                       hover=mix(PALETTE.accent, PALETTE.gold, 0.16),
                       press=mix(PALETTE.accent, PALETTE.gold, 0.36)),
        "ghost": dict(fill=PALETTE.surface_hi, text=PALETTE.ink,
                     hover=mix(PALETTE.surface_hi, PALETTE.accent, 0.10),
                     press=darken(PALETTE.surface_hi, 0.14)),
        "danger": dict(fill=PALETTE.danger, text="#2a0a0d", hover=PALETTE.danger,
                      press=darken(PALETTE.danger, 0.18)),
    }

    def __init__(self, parent, text: str, command: Callable[[], None] | None = None,
                variant: str = "primary", width: int = 160, height: int = 44,
                font: tuple = (PALETTE.font_family, 12, "bold"), responsive: bool = False):
        bg = parent["bg"] if isinstance(parent, (tk.Frame, tk.Canvas)) else PALETTE.surface
        super().__init__(parent, width=width, height=height, bg=bg)
        self.command = command
        self.colors = self.VARIANTS[variant]
        self.enabled = True
        self._label = text
        self._font = font
        self._cw, self._ch = width, height
        self._rect = round_rect(self, 1, 1, width - 1, height - 1, radius=height / 2,
                                fill=self.colors["fill"], outline="")
        self._text = self.create_text(width / 2, height / 2, text=text, fill=self.colors["text"],
                                      font=font)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        if responsive:
            self._bind_stretch(self._redraw)

    def _redraw(self, w: int, h: int) -> None:
        self.coords(self._rect, *_round_rect_points(1, 1, w - 1, h - 1, h / 2))
        self.coords(self._text, w / 2, h / 2)

    def set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        fill = self.colors["fill"] if enabled else mix(self.colors["fill"], PALETTE.bg1, 0.65)
        text = self.colors["text"] if enabled else PALETTE.ink_faint
        self.itemconfigure(self._rect, fill=fill)
        self.itemconfigure(self._text, fill=text)
        self.configure(cursor="arrow" if not enabled else "pointinghand"
                       if _is_macos() else "hand2")

    def set_text(self, text: str) -> None:
        self.itemconfigure(self._text, text=text)

    def _on_enter(self, _e=None) -> None:
        if self.enabled:
            self.itemconfigure(self._rect, fill=self.colors["hover"])
            self.configure(cursor="pointinghand" if _is_macos() else "hand2")

    def _on_leave(self, _e=None) -> None:
        if self.enabled:
            self.itemconfigure(self._rect, fill=self.colors["fill"])

    def _on_press(self, _e=None) -> None:
        if self.enabled:
            self.itemconfigure(self._rect, fill=self.colors["press"])

    def _on_release(self, event) -> None:
        if not self.enabled:
            return
        self.itemconfigure(self._rect, fill=self.colors["hover"])
        inside = 0 <= event.x <= self._cw and 0 <= event.y <= self._ch
        if inside and self.command:
            self.command()


class AnimatedBar(AnimatedWidget):
    """A rounded progress bar whose fill eases toward a target value (0..1).

    Responsive by default: it redraws at whatever width its container
    allocates (pack/grid it with ``fill="x"``), so a probability bar in a
    card that grows with the window grows with it too, instead of leaving a
    fixed-width bar stranded in a corner.
    """

    def __init__(self, parent, width: int = 300, height: int = 12, track: str | None = None,
                responsive: bool = True):
        bg = parent["bg"] if isinstance(parent, (tk.Frame, tk.Canvas)) else PALETTE.surface
        super().__init__(parent, width=width, height=height, bg=bg)
        self._cw, self._ch = width, height
        self._value = 0.0
        self._target = 0.0
        self._start = 0.0
        self._t0 = 0
        self._duration = 500
        self._color = PALETTE.accent
        self._track_color = track or PALETTE.bg2
        self._track = round_rect(self, 0, 0, width, height, radius=height / 2,
                                 fill=self._track_color, outline="")
        self._fill = round_rect(self, 0, 0, 1, height, radius=height / 2,
                               fill=self._color, outline="")
        if responsive:
            self._bind_stretch(self._on_resize)

    def _on_resize(self, w: int, h: int) -> None:
        r = h / 2
        self.coords(self._track, *_round_rect_points(0, 0, w, h, r))
        self._redraw()

    def set_value(self, fraction: float, color: str | None = None, animate: bool = True) -> None:
        self._target = max(0.0, min(1.0, fraction))
        if color:
            self._color = color
            self.itemconfigure(self._fill, fill=color)
        if not animate:
            self._value = self._target
            self._redraw()
            return
        self._start = self._value
        self._t0 = 0
        self._start_loop("fill", self._step)

    def _step(self) -> None:
        self._t0 += FPS_MS
        t = ease_out_cubic(min(1.0, self._t0 / self._duration))
        self._value = self._start + (self._target - self._start) * t
        self._redraw()
        if t >= 1.0:
            self._stop_loop("fill")

    def _redraw(self) -> None:
        w = max(self._ch, self._cw * self._value)
        self.coords(self._fill, *_round_rect_points(0, 0, w, self._ch, self._ch / 2))


class StatusDot(AnimatedWidget):
    """A small pulsing dot: amber+pulsing (loading), green+gentle (ready), red (error)."""

    STATE_COLORS: ClassVar[dict[str, str]] = {
        "loading": PALETTE.gold, "ready": PALETTE.success, "error": PALETTE.danger,
    }

    def __init__(self, parent, size: int = 10):
        bg = parent["bg"] if isinstance(parent, (tk.Frame, tk.Canvas)) else PALETTE.bg1
        super().__init__(parent, width=size, height=size, bg=bg)
        self._size = size
        self._phase = 0.0
        self._state = "loading"
        cx = cy = size / 2
        self._glow = self.create_oval(0, 0, size, size, fill=bg, outline="")
        self._dot = self.create_oval(cx - 3, cy - 3, cx + 3, cy + 3,
                                     fill=self.STATE_COLORS["loading"], outline="")
        self._start_loop("pulse", self._step)

    def set_state(self, state: str) -> None:
        self._state = state
        color = self.STATE_COLORS.get(state, PALETTE.ink_faint)
        self.itemconfigure(self._dot, fill=color)

    def _step(self) -> None:
        self._phase = (self._phase + 0.08) % (2 * math.pi)
        pulse = 0.5 + 0.5 * math.sin(self._phase) if self._state != "error" else 1.0
        cx = cy = self._size / 2
        color = self.STATE_COLORS.get(self._state, PALETTE.ink_faint)
        r_glow = 2 + pulse * (self._size / 2 - 2)
        self.coords(self._glow, cx - r_glow, cy - r_glow, cx + r_glow, cy + r_glow)
        self.itemconfigure(self._glow, fill=mix(self["bg"], color, 0.25 + 0.35 * pulse))


class RetinaGlyph(AnimatedWidget):
    """A rotating, ring-and-scan-line brand mark — the product's visual signature."""

    def __init__(self, parent, size: int = 220):
        bg = parent["bg"] if isinstance(parent, (tk.Frame, tk.Canvas)) else PALETTE.bg1
        super().__init__(parent, width=size, height=size, bg=bg)
        self._size = size
        self._angle = 0.0
        self._draw_static()
        self._scan = self.create_arc(0, 0, 0, 0, style="pieslice", outline="",
                                     fill=PALETTE.accent)
        self._start_loop("rotate", self._step, delay=40)

    def _draw_static(self) -> None:
        s = self._size
        cx = cy = s / 2
        rings = [(0.98, PALETTE.border_soft), (0.78, PALETTE.border), (0.55, PALETTE.accent_soft)]
        for scale, color in rings:
            r = s / 2 * scale
            self.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=1.4)
        for deg in range(0, 360, 30):
            rad = math.radians(deg)
            r1, r2 = s / 2 * 0.98, s / 2 * 1.03
            self.create_line(cx + r1 * math.cos(rad), cy + r1 * math.sin(rad),
                            cx + r2 * math.cos(rad), cy + r2 * math.sin(rad),
                            fill=PALETTE.border, width=1)
        core_r = s / 2 * 0.14
        self.create_oval(cx - core_r, cy - core_r, cx + core_r, cy + core_r,
                        outline=PALETTE.accent, width=2, fill=PALETTE.bg2)

    def _step(self) -> None:
        s = self._size
        cx = cy = s / 2
        r = s / 2 * 0.78
        self._angle = (self._angle + 2.2) % 360
        self.coords(self._scan, cx - r, cy - r, cx + r, cy + r)
        self.itemconfigure(self._scan, start=self._angle, extent=46)


class BackgroundFX(AnimatedWidget):
    """The landing page's living background: a drifting aurora gradient, soft glow
    orbs, and slow bokeh particles. Redraws its gradient on resize."""

    def __init__(self, parent, palette: Palette = PALETTE,
                on_layout: Callable[[tk.Canvas, int, int], None] | None = None):
        super().__init__(parent, bg=palette.bg0)
        self.palette = palette
        self._hue_phase = 0.0
        self._bands: list[int] = []
        self._orbs: list[tuple[int, str, float, float, float]] = []
        self._particles: list[dict] = []
        self._cw, self._ch = 1, 1
        self._on_layout = on_layout
        self.bind("<Configure>", self._on_resize)
        self._start_loop("bg", self._step, delay=60)

    def _on_resize(self, event) -> None:
        if abs(event.width - self._cw) < 2 and abs(event.height - self._ch) < 2:
            return
        self._cw, self._ch = max(event.width, 1), max(event.height, 1)
        self.delete("all")
        self._build_gradient()
        self._build_orbs()
        self._build_particles()
        if self._on_layout:
            self._on_layout(self, self._cw, self._ch)

    def _build_gradient(self, top: str | None = None) -> None:
        bands = 48
        top = top or self.palette.bg2
        bottom = self.palette.bg0
        self._bands = []
        band_h = self._ch / bands
        for i in range(bands):
            color = mix(top, bottom, (i / bands) ** 1.4)
            item = self.create_rectangle(0, i * band_h, self._cw, (i + 1) * band_h + 1,
                                         fill=color, outline="")
            self._bands.append(item)

    def _build_orbs(self) -> None:
        specs = [(0.18, 0.22, self.palette.accent), (0.85, 0.15, self.palette.secondary),
                (0.7, 0.75, self.palette.gold)]
        self._orbs = []
        for fx, fy, color in specs:
            cx, cy = self._cw * fx, self._ch * fy
            base_r = min(self._cw, self._ch) * 0.28
            rings = 7
            for i in range(rings, 0, -1):
                r = base_r * i / rings
                strength = 0.10 * (1 - i / rings) ** 0.6
                item = self.create_oval(cx - r, cy - r, cx + r, cy + r, outline="",
                                       fill=mix(self.palette.bg1, color, strength))
                self._orbs.append((item, color, fx, fy, base_r))

    def _build_particles(self) -> None:
        rng = random.Random(7)
        self._particles = []
        count = max(14, int(self._cw * self._ch / 45000))
        for _ in range(count):
            item = self.create_oval(0, 0, 0, 0, outline="")
            self._particles.append({
                "id": item,
                "x": rng.uniform(0, self._cw),
                "y": rng.uniform(0, self._ch),
                "r": rng.uniform(1.0, 2.6),
                "speed": rng.uniform(6, 18) / 30,
                "drift": rng.uniform(-0.3, 0.3),
                "color": rng.choice(
                    [self.palette.accent, self.palette.ink, self.palette.secondary]),
                "alpha": rng.uniform(0.10, 0.35),
            })

    def _step(self) -> None:
        self._hue_phase = (self._hue_phase + 0.004) % 1.0
        t = (math.sin(self._hue_phase * 2 * math.pi) + 1) / 2
        top = mix(self.palette.bg2, self.palette.accent_soft, t * 0.6)
        if self._bands:
            self._redraw_gradient(top)
        for p in self._particles:
            p["y"] -= p["speed"]
            p["x"] += p["drift"]
            if p["y"] < -4:
                p["y"] = self._ch + 4
                p["x"] = random.uniform(0, self._cw)
            if p["x"] < -4:
                p["x"] = self._cw + 4
            elif p["x"] > self._cw + 4:
                p["x"] = -4
            r = p["r"]
            self.coords(p["id"], p["x"] - r, p["y"] - r, p["x"] + r, p["y"] + r)
            self.itemconfigure(p["id"], fill=mix(self.palette.bg1, p["color"], p["alpha"]))

    def _redraw_gradient(self, top: str) -> None:
        bands = len(self._bands)
        for i, item in enumerate(self._bands):
            color = mix(top, self.palette.bg0, (i / bands) ** 1.4)
            self.itemconfigure(item, fill=color)


class Pill(tk.Canvas):
    """A small static rounded badge/chip. Used for feature tags and status banners.

    Pass ``responsive=True`` to have it fill whatever width its container
    allocates (e.g. a referral banner that should span the full card width
    regardless of the window size) instead of staying at a fixed width.
    """

    def __init__(self, parent, text: str, fill: str, text_color: str,
                bg: str | None = None, width: int = 140, height: int = 30,
                font: tuple = (PALETTE.font_family, 10, "bold"), responsive: bool = False):
        super().__init__(parent, width=width, height=height,
                         bg=bg or (parent["bg"] if isinstance(parent, (tk.Frame, tk.Canvas))
                                  else PALETTE.surface),
                         highlightthickness=0, bd=0)
        self._rect = round_rect(self, 1, 1, width - 1, height - 1, radius=height / 2,
                               fill=fill, outline="")
        self._text = self.create_text(width / 2, height / 2, text=text, fill=text_color,
                                      font=font)
        self._cw, self._ch = width, height
        if responsive:
            self.bind("<Configure>", self._on_resize, add="+")

    def _on_resize(self, event: tk.Event) -> None:
        w, h = max(event.width, 1), max(event.height, 1)
        if abs(w - self._cw) < 1 and abs(h - self._ch) < 1:
            return
        self._cw, self._ch = w, h
        self.coords(self._rect, *_round_rect_points(1, 1, w - 1, h - 1, h / 2))
        self.coords(self._text, w / 2, h / 2)

    def set(self, text: str | None = None, fill: str | None = None,
           text_color: str | None = None) -> None:
        if text is not None:
            self.itemconfigure(self._text, text=text)
        if fill:
            self.itemconfigure(self._rect, fill=fill)
        if text_color:
            self.itemconfigure(self._text, fill=text_color)


class GlassPanel(tk.Frame):
    """A frosted, Apple-glassmorphism-style panel.

    Tkinter has no real blur or alpha compositing between widgets, so the
    "frosted glass" look is built entirely from layered, blended colour: a
    soft multi-ring drop shadow, a translucent-looking rounded fill, and a
    bright top/left rim that reads as light catching a glass edge (with a
    dimmer bottom/right edge for depth). It behaves like a plain ``tk.Frame``
    to use — pack/grid the panel itself, then put content in ``.body``,
    which carries a background colour that matches the glass fill so labels
    etc. blend into it seamlessly.
    """

    RADIUS = 18
    SHADOW_RINGS = 5
    OUTER_PAD = 12  # canvas margin reserved for the shadow to bleed into

    def __init__(self, parent, palette: Palette = PALETTE):
        bg = parent["bg"] if isinstance(parent, (tk.Frame, tk.Canvas)) else palette.bg1
        super().__init__(parent, bg=bg)
        self._palette = palette
        self._bg = bg
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.body = tk.Frame(self.canvas, bg=palette.surface)
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.canvas.bind("<Configure>", self._on_resize)
        self.body.bind("<Configure>", lambda _e: self._sync_height_to_content())

    def _sync_height_to_content(self) -> None:
        # Unlike a plain tk.Frame, a tk.Canvas never grows to fit an embedded
        # window's content on its own — its requested size is whatever was
        # last configured, full stop. Without this, every card silently
        # clips at a small default height (this is exactly the bug that made
        # the image-picker and Analyze button vanish: they simply fell
        # outside the canvas's unrelated-to-content height). Whenever the
        # content's natural height changes, grow the canvas — and therefore
        # this Frame's own reported size, so grid/pack lay out the *rest* of
        # the UI correctly too — to match.
        margin = 2 * (self.OUTER_PAD + self.RADIUS)
        needed = self.body.winfo_reqheight() + margin
        if abs(needed - self.canvas.winfo_reqheight()) > 1:
            self.canvas.configure(height=needed)

    def fit_to_content(self) -> None:
        """Call once after all content has been packed into ``.body``. Forces
        an immediate size sync instead of waiting for the next natural
        <Configure> event, so the panel reports its real height the moment
        it's placed rather than one layout pass late."""
        self.body.update_idletasks()
        self._sync_height_to_content()

    def _on_resize(self, event: tk.Event) -> None:
        w, h = max(event.width, 1), max(event.height, 1)
        pad = self.OUTER_PAD
        x1, y1, x2, y2 = pad, pad, w - pad, h - pad
        if x2 <= x1 or y2 <= y1:
            return
        self.canvas.delete("shape")
        p = self._palette

        for i in range(self.SHADOW_RINGS, 0, -1):
            grow = i * 1.6
            strength = 0.55 * (1 - i / self.SHADOW_RINGS) ** 0.7
            color = mix(self._bg, p.glass_shadow, strength)
            round_rect(self.canvas, x1 - grow, y1 - grow + 3, x2 + grow, y2 + grow + 3,
                      radius=self.RADIUS + grow, fill=color, outline="", tags="shape")

        # A thin full outline first, so all four corners read as rounded even
        # where the light/dark accent strokes below don't reach — then the
        # brighter top-left / dimmer bottom-right strokes on top of it are
        # what actually sells the "catching the light" glass cue.
        round_rect(self.canvas, x1, y1, x2, y2, radius=self.RADIUS,
                  fill=p.surface, outline=mix(p.glass_edge_light, p.glass_edge_dark, 0.5),
                  width=1, tags="shape")

        d = self.RADIUS * 2
        self.canvas.create_arc(x1, y1, x1 + d, y1 + d, start=90, extent=90, style="arc",
                              outline=p.glass_edge_light, width=1.4, tags="shape")
        self.canvas.create_line(x1 + self.RADIUS, y1, x2 - self.RADIUS, y1,
                               fill=p.glass_edge_light, width=1.4, tags="shape")
        self.canvas.create_line(x1, y1 + self.RADIUS, x1, y2 - self.RADIUS,
                               fill=p.glass_edge_light, width=1.4, tags="shape")
        self.canvas.create_arc(x2 - d, y2 - d, x2, y2, start=270, extent=90, style="arc",
                              outline=p.glass_edge_dark, width=1.2, tags="shape")
        self.canvas.create_line(x1 + self.RADIUS, y2, x2 - self.RADIUS, y2,
                               fill=p.glass_edge_dark, width=1.2, tags="shape")
        self.canvas.create_line(x2, y1 + self.RADIUS, x2, y2 - self.RADIUS,
                               fill=p.glass_edge_dark, width=1.2, tags="shape")

        # The embedded body is a genuine rectangular OS window, so sizing it
        # to the *full* rounded-rect bounds would square off every corner
        # and paint over the rim highlight entirely (both are drawn right at
        # that boundary). Insetting it by the corner radius lets the curves
        # and the light-catching rim actually show around it; the straight
        # edges have no visible seam since body and fill share the same `surface` colour.
        inset = self.RADIUS
        self.canvas.coords(self._window, x1 + inset, y1 + inset)
        self.canvas.itemconfigure(self._window, width=max(x2 - x1 - 2 * inset, 1),
                                  height=max(y2 - y1 - 2 * inset, 1))


def _is_macos() -> bool:
    import platform

    return platform.system() == "Darwin"


def shake(canvas: tk.Canvas, item: int, base_xy: tuple[float, float],
         amplitude: float = 10, cycles: int = 5, delay: int = 22) -> None:
    """A quick horizontal shake — used to signal a failed login without a dialog."""
    x0, y0 = base_xy
    offsets = [amplitude, -amplitude * 0.8, amplitude * 0.55, -amplitude * 0.3, 0]
    steps = (offsets * ((cycles // len(offsets)) + 1))[:cycles]

    def play(i: int) -> None:
        if i >= len(steps):
            canvas.coords(item, x0, y0)
            return
        canvas.coords(item, x0 + steps[i], y0)
        canvas.after(delay, play, i + 1)

    play(0)


def fade_window(root: tk.Tk, target: float, duration_ms: int = 180,
                on_done: Callable[[], None] | None = None) -> None:
    """Fade the whole window's opacity toward ``target`` (0..1)."""
    try:
        start = root.attributes("-alpha")
    except tk.TclError:
        if on_done:
            on_done()
        return
    steps = max(1, duration_ms // FPS_MS)

    def play(i: int) -> None:
        t = ease_out_cubic(i / steps)
        try:
            root.attributes("-alpha", start + (target - start) * t)
        except tk.TclError:
            return
        if i >= steps:
            if on_done:
                on_done()
        else:
            root.after(FPS_MS, play, i + 1)

    play(1)


class ScrollableFrame(ctk.CTkScrollableFrame):
    """A vertically scrollable container, built on CustomTkinter's
    ``CTkScrollableFrame`` rather than a hand-rolled canvas+embedded-window
    implementation.

    Two from-scratch scroll mechanisms were tried here first — hover-gated
    per-widget binding, then binding on the toplevel window — and both
    passed every synthetic ``event_generate`` test while still not
    responding reliably to a real trackpad/mouse-wheel on the actual
    hardware this was tested on. CustomTkinter's mousewheel handling
    (``bind_all`` plus a self-check that walks each event's widget ancestry
    to decide whether *this* scrollable frame is the right target) is
    battle-tested across a huge number of real deployments on macOS,
    Windows and Linux — rather than keep re-engineering a problem a mature,
    widely-used library has already solved, this delegates the actual
    scroll-driving mechanism to it.

    The public interface (``.body``, ``.enable_wheel_scroll()``,
    ``.disable_wheel_scroll()``, ``.scroll_to_top()``) is kept identical to
    the previous implementation so no call site needs to change.
    """

    def __init__(self, parent, bg: str, palette: Palette = PALETTE):
        super().__init__(
            parent, fg_color=bg, bg_color=bg, corner_radius=0, border_width=0,
            scrollbar_fg_color=bg,
            scrollbar_button_color=mix(bg, palette.ink, 0.30),
            scrollbar_button_hover_color=mix(bg, palette.ink, 0.50),
        )
        self.body = self  # content goes straight into this frame

    def enable_wheel_scroll(self) -> None:
        """No-op: CTkScrollableFrame wires up mousewheel scrolling itself,
        automatically, for as long as this widget exists. Kept as a method
        (rather than removing it) so views can call it unconditionally from
        ``activate()`` without needing to know which scroll implementation
        is behind ``self._scroll``."""

    def disable_wheel_scroll(self) -> None:
        """No-op — see :meth:`enable_wheel_scroll`."""

    def scroll_to_top(self) -> None:
        self._parent_canvas.yview_moveto(0)

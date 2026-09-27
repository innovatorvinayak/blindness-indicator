"""Desktop screening station: an animated landing/login screen plus the
screening dashboard, both on a premium dark theme built from scratch on
``tkinter.Canvas`` (see :mod:`drscreen.gui.canvas_widgets`).

Model loading and inference run on a worker thread; results are marshalled
back to the Tk main loop with ``after()``, so the window never freezes.
Every widget here is presentation only — all real work (auth, inference,
persistence, SMS) goes through :mod:`drscreen.storage` and
:mod:`drscreen.service`, unchanged and untouched by the redesign.
"""

from __future__ import annotations

import logging
import tkinter as tk
import webbrowser
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from PIL import Image, ImageTk

from drscreen.config import Settings
from drscreen.grading import Grade
from drscreen.gui.branding import render_logo
from drscreen.gui.canvas_widgets import (
    AnimatedBar,
    CanvasButton,
    GlassPanel,
    Pill,
    RetinaGlyph,
    ScrollableFrame,
    StatusDot,
    fade_window,
    shake,
)
from drscreen.gui.theme import PALETTE as C
from drscreen.gui.theme import configure_ttk, grade_color, mix
from drscreen.notify import build_sender
from drscreen.preprocessing import SUPPORTED_EXTENSIONS, assess_quality, load_image
from drscreen.storage import Database, DuplicateUsernameError, OperatorInfo, PatientInfo

log = logging.getLogger(__name__)

PREVIEW_SIZE = (360, 200)
WINDOW_SIZE = "1320x940"


class App(tk.Tk):
    def __init__(self, settings: Settings, db: Database):
        super().__init__()
        self.settings = settings
        self.db = db
        self.service = None  # ScreeningService, set once the model has loaded
        self.model_error: str | None = None
        self.operator: OperatorInfo | None = None
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="drscreen")

        self.title("DR Screening Station")
        self.geometry(WINDOW_SIZE)
        # Small on purpose: the dashboard now scrolls, so the window is free to
        # be resized down to a genuinely small size instead of being forced
        # to stay large just so nothing gets clipped.
        self.minsize(760, 560)
        self.configure(bg=C.bg0)
        configure_ttk(ttk.Style(self), C)
        import customtkinter as ctk

        ctk.set_appearance_mode("dark")
        self._icon = ImageTk.PhotoImage(render_logo(256))
        self.iconphoto(True, self._icon)

        self._view: tk.Widget | None = None
        self._show(LoginView(self))
        self._load_model()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # -- navigation ------------------------------------------------------------
    def show_login(self) -> None:
        self.operator = None
        self._transition(LoginView(self))

    def show_screening(self, operator: OperatorInfo) -> None:
        self.operator = operator
        self._transition(ScreeningView(self))

    def show_report(self, screening_id: int) -> None:
        self._transition(ReportView(self, screening_id))

    def show_settings(self) -> None:
        self._transition(SettingsView(self))

    def show_history(self) -> None:
        self._transition(HistoryView(self))

    def _show(self, view: tk.Widget) -> None:
        # A view's app-level bindings (keyboard shortcuts, wheel-scroll) are
        # installed/removed here — synchronously, in this exact order — not
        # at __init__/destroy() time. The old code bound a new view's
        # shortcuts the moment it was *constructed* (up to 140ms before this
        # runs, while the fade-out plays) and only unbound the outgoing
        # view's on its (also delayed) destroy — so the outgoing view's
        # cleanup could fire *after* the incoming view had already rebound
        # the same key sequence, silently erasing it. Deactivating the old
        # view right before destroying it, then activating the new one right
        # after placing it, both here, closes that gap entirely.
        if self._view is not None:
            deactivate = getattr(self._view, "deactivate", None)
            if deactivate is not None:
                deactivate()
            self._view.destroy()
        self._view = view
        view.place(x=0, y=0, relwidth=1, relheight=1)
        activate = getattr(view, "activate", None)
        if activate is not None:
            activate()

    def _transition(self, view: tk.Widget) -> None:
        """A short fade-through-black between views, instead of an instant cut."""
        def swap():
            self._show(view)
            fade_window(self, 1.0, duration_ms=180)
        fade_window(self, 0.0, duration_ms=140, on_done=swap)

    # -- background work --------------------------------------------------------
    def run_async(self, fn: Callable[[], Any], on_done: Callable[[Any], None],
                  on_error: Callable[[BaseException], None]) -> None:
        future = self._executor.submit(fn)
        self._poll(future, on_done, on_error)

    def _poll(self, future: Future, on_done, on_error) -> None:
        if not future.done():
            self.after(40, self._poll, future, on_done, on_error)
            return
        exc = future.exception()
        if exc is not None:
            log.exception("background task failed", exc_info=exc)
            on_error(exc)
        else:
            on_done(future.result())

    def _load_model(self) -> None:
        from drscreen.inference import Predictor
        from drscreen.service import ScreeningService

        def load():
            predictor = Predictor.from_checkpoint(
                self.settings.model_path, self.settings.device, tta=self.settings.tta,
                referral_threshold=self.settings.referral_threshold)
            sms = build_sender(self.settings)
            return ScreeningService(predictor, self.db, sms, self.settings)

        def done(service):
            self.service = service
            self._notify_model_status()

        def failed(exc):
            self.model_error = str(exc)
            self._notify_model_status()

        self.run_async(load, done, failed)

    def _notify_model_status(self) -> None:
        if isinstance(self._view, ScreeningView):
            self._view.refresh_model_status()

    def model_status(self) -> tuple[str, str]:
        if self.service is not None:
            meta = self.service.predictor.metadata
            return "ready", f"{meta.arch} · {meta.version} · {self.service.predictor.device}"
        if self.model_error:
            return "error", self.model_error.splitlines()[0]
        return "loading", "Loading model…"

    def _on_close(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
        self.destroy()


# ============================================================================
# Landing / login
# ============================================================================

FEATURES = ("ResNet-152 · PyTorch", "MySQL / SQLite", "Twilio SMS reports", "QWK-validated")


class LoginView(tk.Frame):
    """A living, animated landing page that doubles as the sign-in screen."""

    def __init__(self, app: App):
        super().__init__(app, bg=C.bg0)
        self.app = app
        self._entered = False

        from drscreen.gui.canvas_widgets import BackgroundFX

        self.bg = BackgroundFX(self, on_layout=self._layout_overlay)
        self.bg.place(x=0, y=0, relwidth=1, relheight=1)

        self.brand = RetinaGlyph(self, size=96)
        self.brand.place(x=48, y=44)

        self._card_base = (0.685, 0.5)
        self.card = self._build_card()
        self.card.place(relx=self._card_base[0], rely=self._card_base[1], anchor="center",
                        width=400, height=460)

        self.after(150, lambda: self.username_entry.focus_set())

    def activate(self) -> None:
        # Bound on the toplevel, not this frame: a plain Frame only receives
        # key events when it itself has focus, which it never does here (the
        # Entry widgets do) — binding on the window is what actually makes
        # Enter-to-submit work regardless of which field has focus. Called by
        # App._show() right after this view is placed, not from __init__ —
        # see the comment there for why that timing matters.
        self.app.bind("<Return>", lambda _e: self.sign_in())

    def deactivate(self) -> None:
        self.app.unbind("<Return>")

    # -- animated hero text, drawn straight onto the living background ----------
    def _layout_overlay(self, canvas: tk.Canvas, _width: int, height: int) -> None:
        x = 48
        title_y = height * 0.42
        canvas.create_text(x, title_y, text="Diabetic Retinopathy", anchor="w",
                          fill=C.ink, font=(C.font_family, 34, "bold"))
        canvas.create_text(x, title_y + 46, text="Screening, in minutes — not months.",
                          anchor="w", fill=mix(C.ink, C.accent, 0.35),
                          font=(C.font_family, 17))
        canvas.create_text(x, title_y + 92,
                          text="ResNet-152 grades a fundus photo on the 0-4 clinical\n"
                               "scale and flags referable cases for an ophthalmologist.",
                          anchor="w", fill=C.ink_dim, font=(C.font_family, 12), justify="left")

        pill_y = title_y + 150
        px = x
        for label in FEATURES:
            w = 24 + 7 * len(label)
            pill = Pill(self, label, fill=mix(C.bg1, C.accent, 0.10), text_color=C.ink_dim,
                       bg=C.bg1, width=w, height=28)
            canvas.create_window(px, pill_y, window=pill, anchor="w")
            px += w + 10

        canvas.create_text(x, height - 34,
                          text="AI-assisted screening aid — not a diagnostic device.",
                          anchor="w", fill=C.ink_faint, font=(C.font_family, 10, "italic"))
        if not self._entered:
            self._entered = True
            self.after(80, self._play_entrance)

    def _play_entrance(self) -> None:
        # A short fade-up for the whole window on first paint feels like a product
        # loading, not an instant window slam.
        try:
            self.app.attributes("-alpha", 0.0)
        except tk.TclError:
            return
        fade_window(self.app, 1.0, duration_ms=420)

    # -- the glass login card -----------------------------------------------------
    def _build_card(self) -> GlassPanel:
        card = GlassPanel(self)

        pad = tk.Frame(card.body, bg=C.surface)
        pad.pack(fill="both", expand=True, padx=32, pady=28)

        tk.Label(pad, text="Operator sign-in", bg=C.surface, fg=C.ink,
                font=(C.font_family, 19, "bold")).pack(anchor="w")
        tk.Label(pad, text="Screening records are tied to your account.", bg=C.surface,
                fg=C.ink_dim, font=(C.font_family, 11)).pack(anchor="w", pady=(2, 22))

        self.username = tk.StringVar()
        self.password = tk.StringVar()

        tk.Label(pad, text="USERNAME", bg=C.surface, fg=C.ink_faint,
                font=(C.font_family, 9, "bold")).pack(anchor="w")
        self.username_entry = ttk.Entry(pad, textvariable=self.username, font=(C.font_family, 13))
        self.username_entry.pack(fill="x", pady=(4, 16))

        tk.Label(pad, text="PASSWORD", bg=C.surface, fg=C.ink_faint,
                font=(C.font_family, 9, "bold")).pack(anchor="w")
        ttk.Entry(pad, textvariable=self.password, show="•",
                 font=(C.font_family, 13)).pack(fill="x", pady=(4, 6))

        self.message = tk.Label(pad, text="", bg=C.surface, fg=C.danger, wraplength=336,
                                justify="left", font=(C.font_family, 11), anchor="w")
        self.message.pack(fill="x", pady=(4, 10))

        CanvasButton(pad, "Sign in", command=self.sign_in, variant="primary",
                    width=336, height=46).pack(pady=(6, 10))
        CanvasButton(pad, "Create account", command=self.sign_up, variant="ghost",
                    width=336, height=46).pack()

        tk.Frame(pad, bg=C.border, height=1).pack(fill="x", pady=18)
        tk.Label(pad, text="New here? Creating an account takes one click above —\n"
                          "no admin approval needed for this local install.",
                bg=C.surface, fg=C.ink_faint, font=(C.font_family, 10),
                justify="left").pack(anchor="w")
        card.fit_to_content()
        return card

    # -- actions -------------------------------------------------------------------
    def sign_in(self) -> None:
        username, password = self.username.get().strip(), self.password.get()
        if not username or not password:
            self._fail("Enter your username and password.")
            return
        operator = self.app.db.authenticate(username, password)
        if operator is None:
            self.password.set("")
            self._fail("Incorrect username or password.")
            return
        self.app.show_screening(operator)

    def sign_up(self) -> None:
        try:
            operator = self.app.db.create_operator(self.username.get(), self.password.get())
        except (DuplicateUsernameError, ValueError) as exc:
            self._fail(str(exc))
            return
        self.app.show_screening(operator)

    def _fail(self, text: str) -> None:
        self.message.configure(text=text)
        x0, y0 = self._card_base
        px, py = self.winfo_width() * x0, self.winfo_height() * y0
        shake(self._as_place_shaker(), 0, (px, py))

    def _as_place_shaker(self) -> _ProxyCanvas:
        """Adapt the .place()-managed card to the (canvas, item) shake() signature
        by driving its x position directly, in pixels, on this frame."""
        return _ProxyCanvas(self.card)


class _ProxyCanvas:
    """Minimal shim so canvas_widgets.shake() can drive a place()-managed Frame."""

    def __init__(self, widget: tk.Widget):
        self.widget = widget

    def coords(self, _item, x, y) -> None:
        # place() ADDS x to any existing relx rather than replacing it, so the
        # card's original relx/rely (from its centred initial placement) must be
        # cleared here or it silently pushes the card off-screen.
        self.widget.place(x=x, y=y, relx=0, rely=0, anchor="center")

    def after(self, delay, fn, *args) -> None:
        self.widget.after(delay, fn, *args)


# ============================================================================
# Screening dashboard
# ============================================================================

class ScreeningView(tk.Frame):
    def __init__(self, app: App):
        super().__init__(app, bg=C.bg1)
        self.app = app
        self.image_path: Path | None = None
        self._preview_ref: ImageTk.PhotoImage | None = None
        self._busy = False
        self._last_screening_id: int | None = None

        self._build_header()

        # Everything below the header scrolls: on a short/non-maximised window
        # the cards simply no longer fit their natural height, and pack/grid
        # would silently push widgets (including the Analyze button) past the
        # visible edge with no way to reach them. A real scrollbar fixes that
        # at any window size instead of fighting for pixels via grid weights.
        scroll = ScrollableFrame(self, bg=C.bg1)
        scroll.pack(fill="both", expand=True)
        self._scroll = scroll

        body = tk.Frame(scroll.body, bg=C.bg1)
        body.pack(fill="both", expand=True, padx=24, pady=(4, 20))
        body.columnconfigure(0, weight=5, uniform="col")
        body.columnconfigure(1, weight=6, uniform="col")
        self._build_input_card(body).grid(row=0, column=0, sticky="new", padx=(0, 10))
        self._build_result_card(body).grid(row=0, column=1, sticky="new", padx=(10, 0))

        self.refresh_model_status()

    # -- keyboard shortcuts + wheel-scroll, installed/removed by App._show() --------
    _SHORTCUTS = ("<Control-o>", "<Command-o>", "<Control-Return>", "<Command-Return>",
                 "<Control-r>", "<Command-r>", "<Control-f>", "<Command-f>")

    def activate(self) -> None:
        b = self.app.bind
        b("<Control-o>", lambda _e: self.choose_image())
        b("<Command-o>", lambda _e: self.choose_image())
        b("<Control-Return>", lambda _e: self._shortcut_analyze())
        b("<Command-Return>", lambda _e: self._shortcut_analyze())
        b("<Control-r>", lambda _e: self._shortcut_view_report())
        b("<Command-r>", lambda _e: self._shortcut_view_report())
        b("<Control-f>", lambda _e: self.app.show_history())
        b("<Command-f>", lambda _e: self.app.show_history())
        self._scroll.enable_wheel_scroll()

    def deactivate(self) -> None:
        for seq in self._SHORTCUTS:
            self.app.unbind(seq)
        self._scroll.disable_wheel_scroll()

    def _shortcut_analyze(self) -> None:
        if self.analyze_btn.enabled:
            self.analyze()

    def _shortcut_view_report(self) -> None:
        if self.report_btn.enabled:
            self.view_report()

    # -- layout --------------------------------------------------------------------
    def _card(self, parent) -> GlassPanel:
        return GlassPanel(parent)

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=C.bg1)
        header.pack(fill="x", padx=24, pady=(20, 6))

        left = tk.Frame(header, bg=C.bg1)
        left.pack(side="left")
        RetinaGlyph(left, size=34).pack(side="left", padx=(0, 10))
        title_box = tk.Frame(left, bg=C.bg1)
        title_box.pack(side="left")
        tk.Label(title_box, text="DR Screening Station", bg=C.bg1, fg=C.ink,
                font=(C.font_family, 18, "bold")).pack(anchor="w")
        status_row = tk.Frame(title_box, bg=C.bg1)
        status_row.pack(anchor="w")
        self.status_dot = StatusDot(status_row, size=10)
        self.status_dot.pack(side="left", padx=(0, 6))
        self.model_label = tk.Label(status_row, text="", bg=C.bg1, fg=C.ink_dim,
                                    font=(C.font_family, 10))
        self.model_label.pack(side="left")

        right = tk.Frame(header, bg=C.bg1)
        right.pack(side="right")
        CanvasButton(right, "Sign out", command=self.app.show_login, variant="ghost",
                    width=110, height=36, font=(C.font_family, 11, "bold")).pack(side="right")
        CanvasButton(right, "⚙ Settings", command=self.app.show_settings, variant="ghost",
                    width=110, height=36, font=(C.font_family, 11, "bold")).pack(side="right",
                                                                                 padx=(0, 10))
        CanvasButton(right, "📋 Recent Screenings", command=self.app.show_history,
                    variant="ghost", width=180, height=36,
                    font=(C.font_family, 11, "bold")).pack(side="right", padx=(0, 10))
        tk.Label(right, text=f"Operator  ·  {self.app.operator.username}", bg=C.bg1,
                fg=C.ink_dim, font=(C.font_family, 11)).pack(side="right", padx=14)

    def _build_input_card(self, parent) -> tk.Frame:
        card = self._card(parent)
        pad = tk.Frame(card.body, bg=C.surface)
        pad.pack(fill="both", expand=True, padx=20, pady=14)

        tk.Label(pad, text="Patient", bg=C.surface, fg=C.ink,
                font=(C.font_family, 14, "bold")).pack(anchor="w", pady=(0, 10))

        self.name = tk.StringVar()
        self.phone = tk.StringVar()
        self.age = tk.StringVar()
        self.sex = tk.StringVar()
        self.send_sms = tk.BooleanVar(value=False)

        row1 = tk.Frame(pad, bg=C.surface)
        row1.pack(fill="x")
        self._field(row1, "FULL NAME", ttk.Entry(row1, textvariable=self.name)).pack(fill="x")

        row2 = tk.Frame(pad, bg=C.surface)
        row2.pack(fill="x", pady=(10, 0))
        col_a = tk.Frame(row2, bg=C.surface)
        col_a.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._field(col_a, "MOBILE NUMBER", ttk.Entry(col_a, textvariable=self.phone)).pack(
            fill="x")
        col_b = tk.Frame(row2, bg=C.surface)
        col_b.pack(side="left", padx=(0, 8))
        self._field(col_b, "AGE", ttk.Entry(col_b, textvariable=self.age, width=6)).pack()
        col_c = tk.Frame(row2, bg=C.surface)
        col_c.pack(side="left")
        self._field(col_c, "SEX", ttk.Combobox(col_c, textvariable=self.sex,
                                               values=("M", "F", "O"), width=4,
                                               state="readonly")).pack()

        ttk.Checkbutton(pad, text="Send SMS report to patient", variable=self.send_sms,
                        style="Card.TCheckbutton").pack(anchor="w", pady=(10, 10))

        holder = tk.Frame(pad, width=PREVIEW_SIZE[0], height=PREVIEW_SIZE[1], bg=C.bg2,
                          highlightbackground=C.border_soft, highlightthickness=1)
        holder.pack(fill="x")
        holder.pack_propagate(False)
        self.preview = tk.Label(holder, bg=C.bg2, fg=C.ink_faint,
                                text="No image selected\n\nClick “Choose fundus image” below",
                                font=(C.font_family, 11), justify="center")
        self.preview.pack(fill="both", expand=True)
        self._original_image: Image.Image | None = None
        self._resize_job: str | None = None
        holder.bind("<Configure>", self._on_preview_box_resized)
        self.file_label = tk.Label(pad, text="", bg=C.surface, fg=C.ink_dim,
                                   font=(C.font_family, 10))
        self.file_label.pack(anchor="w", pady=(6, 2))
        self.quality_label = tk.Label(pad, text="", bg=C.surface, fg=C.gold,
                                      font=(C.font_family, 10), justify="left", anchor="w",
                                      wraplength=440)
        self.quality_label.pack(anchor="w", fill="x", pady=(0, 8))

        btn_row = tk.Frame(pad, bg=C.surface)
        btn_row.pack(fill="x")
        CanvasButton(btn_row, "Choose fundus image…", command=self.choose_image,
                    variant="ghost", width=196, height=46, responsive=True).pack(
            side="left", fill="x", expand=True, padx=(0, 10))
        self.analyze_btn = CanvasButton(btn_row, "Analyze", command=self.analyze,
                                        variant="primary", width=120, height=46)
        self.analyze_btn.pack(side="right")
        self.analyze_btn.set_enabled(False)
        card.fit_to_content()
        return card

    @staticmethod
    def _field(parent, label: str, widget: tk.Widget) -> tk.Frame:
        wrap = tk.Frame(parent, bg=C.surface)
        tk.Label(wrap, text=label, bg=C.surface, fg=C.ink_faint,
                font=(C.font_family, 9, "bold")).pack(anchor="w")
        widget.pack(fill="x", pady=(4, 0))
        return wrap

    def _build_result_card(self, parent) -> tk.Frame:
        card = self._card(parent)
        pad = tk.Frame(card.body, bg=C.surface)
        pad.pack(fill="both", expand=True, padx=20, pady=18)
        self._wrap_labels: list[tk.Label] = []
        pad.bind("<Configure>", self._on_result_card_resized)

        top = tk.Frame(pad, bg=C.surface)
        top.pack(fill="x")
        tk.Label(top, text="Result", bg=C.surface, fg=C.ink,
                font=(C.font_family, 14, "bold")).pack(side="left")
        self.report_btn = CanvasButton(top, "View full report ↗", command=self.view_report,
                                       variant="ghost", width=170, height=32,
                                       font=(C.font_family, 10, "bold"))
        self.report_btn.pack(side="right")
        self.report_btn.set_enabled(False)

        self.grade_label = tk.Label(pad, text="—", font=(C.font_family, 28, "bold"),
                                    bg=C.surface, fg=C.ink_faint, anchor="w")
        self.grade_label.pack(fill="x", pady=(10, 0))
        self.confidence_label = tk.Label(pad, text="Choose an image and press Analyze.",
                                         bg=C.surface, fg=C.ink_dim, font=(C.font_family, 11),
                                         anchor="w")
        self.confidence_label.pack(anchor="w", pady=(2, 12))

        self.referral_banner = Pill(pad, "", fill=C.bg2, text_color=C.ink_faint, bg=C.surface,
                                    width=440, height=38, font=(C.font_family, 12, "bold"),
                                    responsive=True)
        self.referral_banner.pack(fill="x")
        self.advice_label = tk.Label(pad, text="", bg=C.surface, fg=C.ink_dim,
                                     font=(C.font_family, 11), justify="left", anchor="w")
        self.advice_label.pack(anchor="w", fill="x", pady=(10, 16))
        self._wrap_labels.append(self.advice_label)

        self.bars: dict[Grade, tuple[AnimatedBar, tk.Label]] = {}
        grid = tk.Frame(pad, bg=C.surface)
        grid.pack(fill="x")
        for g in Grade:
            row = tk.Frame(grid, bg=C.surface)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f"{int(g)}  {g.label}", bg=C.surface, fg=C.ink_dim,
                    font=(C.font_family, 11), width=22, anchor="w").pack(side="left")
            bar = AnimatedBar(row, width=240, height=10, track=C.bg2)
            bar.pack(side="left", fill="x", expand=True, padx=8)
            pct = tk.Label(row, text="0%", bg=C.surface, fg=C.ink_faint,
                          font=(C.font_family, 10), width=5, anchor="e")
            pct.pack(side="left")
            self.bars[g] = (bar, pct)

        self.warning_label = tk.Label(pad, text="", bg=C.surface, fg=C.gold,
                                      font=(C.font_family, 10), justify="left", anchor="w")
        self.warning_label.pack(anchor="w", fill="x", pady=(14, 0))
        self._wrap_labels.append(self.warning_label)
        tk.Frame(pad, bg=C.surface).pack(fill="both", expand=True)  # spacer
        self.status_label = tk.Label(pad, text="", bg=C.surface, fg=C.ink_dim,
                                     font=(C.font_family, 10), justify="left", anchor="w")
        self.status_label.pack(anchor="w", fill="x")
        self._wrap_labels.append(self.status_label)
        disclaimer = tk.Label(pad, text="AI-assisted screening aid — not a diagnosis. Confirm "
                                       "with an ophthalmologist.", bg=C.surface,
                             fg=C.ink_faint, font=(C.font_family, 9, "italic"),
                             justify="left", anchor="w")
        disclaimer.pack(anchor="w", fill="x", pady=(6, 0))
        self._wrap_labels.append(disclaimer)
        card.fit_to_content()
        return card

    def _on_result_card_resized(self, event: tk.Event) -> None:
        wrap = max(event.width - 4, 120)
        for label in self._wrap_labels:
            label.configure(wraplength=wrap)

    # -- actions -------------------------------------------------------------------
    def choose_image(self) -> None:
        patterns = " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS))
        path = filedialog.askopenfilename(
            title="Select a retinal fundus image",
            filetypes=[("Images", patterns), ("All files", "*")])
        if not path:
            return
        try:
            image = load_image(path)
        except Exception as exc:
            messagebox.showerror("Unreadable image", f"Could not open this file:\n{exc}")
            return
        self._original_image = image
        self._render_preview()
        self.image_path = Path(path)
        self.file_label.configure(text=self.image_path.name)
        # Feedback before spending model time: an operator can retake the
        # photo right away instead of waiting for Analyze to tell them.
        warnings = assess_quality(image).warnings
        self.quality_label.configure(
            text="\n".join(f"⚠ {w}" for w in warnings) if warnings else "✓ Image looks gradable",
            fg=C.gold if warnings else C.success)
        self._update_analyze_state()

    def _render_preview(self) -> None:
        """(Re)draw the loaded image scaled to whatever size the preview box
        currently is — called on load and again whenever the window resizes."""
        if self._original_image is None:
            return
        box = (max(self.preview.winfo_width(), 40), max(self.preview.winfo_height(), 40))
        thumb = self._original_image.copy()
        thumb.thumbnail(box)
        self._preview_ref = ImageTk.PhotoImage(thumb)
        self.preview.configure(image=self._preview_ref, text="")

    def _on_preview_box_resized(self, _event: tk.Event) -> None:
        # Debounce: a live window drag fires many <Configure> events per second;
        # only re-render once they settle, so resizing never feels laggy.
        if self._resize_job is not None:
            self.after_cancel(self._resize_job)
        self._resize_job = self.after(80, self._render_preview)

    def analyze(self) -> None:
        service = self.app.service
        if service is None or self.image_path is None or self._busy:
            return
        try:
            patient = PatientInfo(
                full_name=self.name.get(),
                phone=service.normalize_phone(self.phone.get().strip() or None),
                age=int(self.age.get()) if self.age.get().strip() else None,
                sex=self.sex.get() or None,
            )
            if self.send_sms.get() and not patient.phone:
                raise ValueError("Enter a mobile number to send the SMS report.")
        except ValueError as exc:
            messagebox.showwarning("Check patient details", str(exc))
            return

        self._set_busy(True, "Analyzing image…")
        image_path, operator, notify = self.image_path, self.app.operator, self.send_sms.get()
        self.app.run_async(
            lambda: service.screen(image_path, patient, operator, send_sms=notify),
            self._show_outcome, self._show_error)

    def _show_outcome(self, outcome) -> None:
        self._set_busy(False)
        p = outcome.prediction
        color = grade_color(int(p.grade))
        self.grade_label.configure(text=p.grade.label, fg=color)
        self.confidence_label.configure(
            text=f"Class {int(p.grade)} of 4  ·  confidence {p.confidence:.1%}  ·  "
                 f"P(referable) {p.referral_probability:.1%}")
        if p.referable:
            self.referral_banner.set("⬤  REFER TO OPHTHALMOLOGIST", fill=mix(C.bg1, color, 0.28),
                                     text_color=color)
            self.bell()  # audible cue: a referral matters even if the operator looked away
            self._pulse_referral_banner(color)
        else:
            self.referral_banner.set("✓  No referral needed", fill=mix(C.bg1, C.success, 0.22),
                                     text_color=C.success)
        self.advice_label.configure(text=p.grade.advice)
        for g, prob in zip(Grade, p.probabilities, strict=True):
            bar, pct = self.bars[g]
            bar.set_value(prob, color=grade_color(int(g)))
            pct.configure(text=f"{prob:.0%}")
        self.warning_label.configure(text="\n".join(f"⚠ {w}" for w in p.warnings))

        status = f"Saved as screening #{outcome.screening_id}."
        if outcome.sms is not None:
            status += {"sent": " SMS sent.", "dry_run": " SMS dry-run (Twilio not configured).",
                       "failed": f" SMS failed: {outcome.sms.error}"}[outcome.sms.status]
        self.status_label.configure(text=status)
        self._last_screening_id = outcome.screening_id
        self.report_btn.set_enabled(True)

    def _show_error(self, exc: BaseException) -> None:
        self._set_busy(False)
        messagebox.showerror("Analysis failed", str(exc))

    def _pulse_referral_banner(self, color: str, cycle: int = 0) -> None:
        """Flash the referral banner a few times so a referable result is
        hard to miss even if the operator isn't looking at the screen."""
        if cycle >= 6 or not self.referral_banner.winfo_exists():
            return
        bright = cycle % 2 == 0
        fill = mix(C.bg1, color, 0.55 if bright else 0.28)
        self.referral_banner.set(fill=fill, text_color=color)
        self.after(180, self._pulse_referral_banner, color, cycle + 1)

    def view_report(self) -> None:
        if self._last_screening_id is not None:
            self.app.show_report(self._last_screening_id)

    # -- state ---------------------------------------------------------------------
    def refresh_model_status(self) -> None:
        state, text = self.app.model_status()
        self.status_dot.set_state(state)
        self.model_label.configure(text=text, fg=C.danger if state == "error" else C.ink_dim)
        self._update_analyze_state()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        self.status_label.configure(text=message)
        self.configure(cursor="watch" if busy else "")
        self._update_analyze_state()

    def _update_analyze_state(self) -> None:
        ready = self.app.service is not None and self.image_path is not None and not self._busy
        self.analyze_btn.set_enabled(ready)


# ============================================================================
# Full detailed report — native, in-app (not a browser tab)
# ============================================================================

class ReportView(tk.Frame):
    """The complete clinical report for one screening, rendered natively.

    Built straight from :meth:`Database.get_screening_detail`, so it works for
    any past screening (not just the one just analysed) and needs no model —
    opening a report never waits on ResNet-152. An "Export as HTML" action is
    still offered for anyone who wants a portable, printable/emailable file.
    """

    def __init__(self, app: App, screening_id: int):
        super().__init__(app, bg=C.bg1)
        self.app = app
        self.screening_id = screening_id
        self._preview_ref: ImageTk.PhotoImage | None = None
        self._scroll: ScrollableFrame | None = None  # set below; None if we bail out early

        detail = app.db.get_screening_detail(screening_id)
        if detail is None:
            messagebox.showerror("Report unavailable", f"No screening with id {screening_id}.")
            self.after(10, lambda: app.show_screening(app.operator))
            return
        self.detail = detail

        self._build_header()
        scroll = ScrollableFrame(self, bg=C.bg1)
        scroll.pack(fill="both", expand=True)
        self._scroll = scroll

        body = tk.Frame(scroll.body, bg=C.bg1)
        body.pack(fill="both", expand=True, padx=24, pady=(4, 24))
        body.columnconfigure(0, weight=5, uniform="col")
        body.columnconfigure(1, weight=6, uniform="col")

        self._build_patient_card(body).grid(row=0, column=0, sticky="new", padx=(0, 10),
                                            pady=(0, 16))
        self._build_image_card(body).grid(row=0, column=1, sticky="new", padx=(10, 0),
                                          pady=(0, 16))
        self._build_assessment_card(body).grid(row=1, column=0, columnspan=2, sticky="new",
                                               pady=(0, 16))

        row = 2
        history = app.db.patient_history(detail.patient_name, detail.phone, exclude_id=detail.id)
        if history:
            self._build_history_card(body, history).grid(row=row, column=0, columnspan=2,
                                                          sticky="new", pady=(0, 16))
            row += 1
        self._build_technical_card(body).grid(row=row, column=0, columnspan=2, sticky="new",
                                              pady=(0, 16))
        tk.Label(body, text="AI-assisted screening aid — not a diagnosis. Confirm with an "
                           "ophthalmologist.", bg=C.bg1, fg=C.ink_faint,
                font=(C.font_family, 10, "italic")).grid(row=row + 1, column=0, columnspan=2,
                                                         sticky="w")
    _SHORTCUTS = ("<Control-e>", "<Command-e>", "<Escape>")

    def activate(self) -> None:
        self.app.bind("<Control-e>", lambda _e: self.export_html())
        self.app.bind("<Command-e>", lambda _e: self.export_html())
        self.app.bind("<Escape>", lambda _e: self.app.show_screening(self.app.operator))
        if self._scroll is not None:
            self._scroll.enable_wheel_scroll()

    def deactivate(self) -> None:
        for seq in self._SHORTCUTS:
            self.app.unbind(seq)
        if self._scroll is not None:
            self._scroll.disable_wheel_scroll()

    def _card(self, parent) -> GlassPanel:
        return GlassPanel(parent)

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=C.bg1)
        header.pack(fill="x", padx=24, pady=(20, 6))
        left = tk.Frame(header, bg=C.bg1)
        left.pack(side="left")
        CanvasButton(left, "← Back", command=lambda: self.app.show_screening(self.app.operator),
                    variant="ghost", width=90, height=36,
                    font=(C.font_family, 11, "bold")).pack(side="left", padx=(0, 14))
        tk.Label(left, text=f"Screening Report #{self.screening_id:06d}", bg=C.bg1, fg=C.ink,
                font=(C.font_family, 18, "bold")).pack(side="left")

        right = tk.Frame(header, bg=C.bg1)
        right.pack(side="right")
        self.export_btn = CanvasButton(right, "Export as HTML ↗", command=self.export_html,
                                       variant="ghost", width=170, height=36,
                                       font=(C.font_family, 11, "bold"))
        self.export_btn.pack(side="right")
        self.export_status = tk.Label(header, text="", bg=C.bg1, fg=C.ink_dim,
                                      font=(C.font_family, 10))
        self.export_status.pack(side="right", padx=12)

    def _build_patient_card(self, parent) -> tk.Frame:
        d = self.detail
        card = self._card(parent)
        pad = tk.Frame(card.body, bg=C.surface)
        pad.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(pad, text="Patient", bg=C.surface, fg=C.ink,
                font=(C.font_family, 14, "bold")).pack(anchor="w", pady=(0, 12))
        rows = [("Name", d.patient_name), ("Mobile", d.phone or "—"),
               ("Age", str(d.age) if d.age is not None else "—"),
               ("Sex", {"M": "Male", "F": "Female", "O": "Other"}.get(d.sex or "", "—")),
               ("Operator", d.operator_username or "—"),
               ("Date", f"{d.created_at:%d %b %Y, %H:%M}")]
        for label, value in rows:
            row = tk.Frame(pad, bg=C.surface)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label.upper(), bg=C.surface, fg=C.ink_faint,
                    font=(C.font_family, 9, "bold"), width=10, anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=C.surface, fg=C.ink,
                    font=(C.font_family, 12, "bold"), anchor="w").pack(side="left")
        card.fit_to_content()
        return card

    def _build_image_card(self, parent) -> tk.Frame:
        card = self._card(parent)
        pad = tk.Frame(card.body, bg=C.surface)
        pad.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(pad, text="Fundus image", bg=C.surface, fg=C.ink,
                font=(C.font_family, 14, "bold")).pack(anchor="w", pady=(0, 12))
        holder = tk.Frame(pad, height=220, bg=C.bg2, highlightbackground=C.border_soft,
                          highlightthickness=1)
        holder.pack(fill="x")
        holder.pack_propagate(False)
        img_label = tk.Label(holder, bg=C.bg2, fg=C.ink_faint, text="Image not available",
                            font=(C.font_family, 11))
        img_label.pack(fill="both", expand=True)
        try:
            image = load_image(self.detail.image_path)
            image.thumbnail((520, 220))
            self._preview_ref = ImageTk.PhotoImage(image)
            img_label.configure(image=self._preview_ref, text="")
        except Exception:
            log.warning("could not load archived image %s", self.detail.image_path)
        tk.Label(pad, text=f"SHA-256 {self.detail.image_sha256 or '—'}", bg=C.surface,
                fg=C.ink_faint, font=(C.mono_family, 9), wraplength=440,
                justify="left").pack(anchor="w", pady=(8, 0))
        card.fit_to_content()
        return card

    def _build_assessment_card(self, parent) -> tk.Frame:
        d = self.detail
        grade = Grade(d.grade)
        color = grade_color(d.grade)
        card = self._card(parent)
        pad = tk.Frame(card.body, bg=C.surface)
        pad.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(pad, text="AI assessment", bg=C.surface, fg=C.ink,
                font=(C.font_family, 14, "bold")).pack(anchor="w")
        tk.Label(pad, text=grade.label, font=(C.font_family, 30, "bold"), bg=C.surface,
                fg=color, anchor="w").pack(fill="x", pady=(10, 0))
        tk.Label(pad, text=f"Class {d.grade} of 4  ·  confidence {d.confidence:.1%}  ·  "
                          f"P(referable) {d.referral_probability:.1%}", bg=C.surface,
                fg=C.ink_dim, font=(C.font_family, 11), anchor="w").pack(anchor="w",
                                                                         pady=(2, 12))
        banner = Pill(pad, "", fill=C.bg2, text_color=C.ink_faint, bg=C.surface, width=440,
                     height=38, font=(C.font_family, 12, "bold"), responsive=True)
        banner.pack(fill="x")
        if d.referable:
            banner.set("⬤  REFER TO OPHTHALMOLOGIST", fill=mix(C.bg1, color, 0.28),
                      text_color=color)
        else:
            banner.set("✓  No referral needed", fill=mix(C.bg1, C.success, 0.22),
                      text_color=C.success)
        advice = tk.Label(pad, text=grade.advice, bg=C.surface, fg=C.ink_dim,
                         font=(C.font_family, 11), justify="left", anchor="w")
        advice.pack(anchor="w", fill="x", pady=(10, 16))
        pad.bind("<Configure>", lambda e: advice.configure(wraplength=max(e.width - 4, 120)))

        grid = tk.Frame(pad, bg=C.surface)
        grid.pack(fill="x")
        for g in Grade:
            row = tk.Frame(grid, bg=C.surface)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=f"{int(g)}  {g.label}", bg=C.surface, fg=C.ink_dim,
                    font=(C.font_family, 11), width=22, anchor="w").pack(side="left")
            bar = AnimatedBar(row, width=300, height=10, track=C.bg2)
            bar.pack(side="left", fill="x", expand=True, padx=8)
            prob = d.probabilities[int(g)]
            bar.set_value(prob, color=grade_color(int(g)), animate=False)
            tk.Label(row, text=f"{prob:.0%}", bg=C.surface, fg=C.ink_faint,
                    font=(C.font_family, 10), width=5, anchor="e").pack(side="left")
        card.fit_to_content()
        return card

    def _build_history_card(self, parent, history: list) -> tk.Frame:
        card = self._card(parent)
        pad = tk.Frame(card.body, bg=C.surface)
        pad.pack(fill="both", expand=True, padx=20, pady=(14, 16))
        tk.Label(pad, text=f"Previous screenings for {self.detail.patient_name}", bg=C.surface,
                fg=C.ink, font=(C.font_family, 13, "bold")).pack(anchor="w", pady=(0, 8))
        for r in history:
            row = tk.Frame(pad, bg=C.surface)
            row.pack(fill="x", pady=4)
            tk.Label(row, text=f"{r.created_at:%d %b %Y}", bg=C.surface, fg=C.ink_dim,
                    font=(C.font_family, 10), width=14, anchor="w").pack(side="left")
            tk.Label(row, text=Grade(r.grade).label, bg=C.surface, fg=grade_color(r.grade),
                    font=(C.font_family, 11, "bold"), width=22, anchor="w").pack(side="left")
            tk.Label(row, text=f"{r.confidence:.0%}", bg=C.surface, fg=C.ink_faint,
                    font=(C.font_family, 10), width=6, anchor="w").pack(side="left")
            tk.Label(row, text=self._trend_note(r.grade, self.detail.grade), bg=C.surface,
                    fg=C.ink_faint, font=(C.font_family, 10)).pack(side="left")
        card.fit_to_content()
        return card

    @staticmethod
    def _trend_note(previous_grade: int, current_grade: int) -> str:
        if current_grade > previous_grade:
            return "↑ worse than this visit"
        if current_grade < previous_grade:
            return "↓ better than this visit"
        return "→ unchanged since this visit"

    def _build_technical_card(self, parent) -> tk.Frame:
        d = self.detail
        card = self._card(parent)
        pad = tk.Frame(card.body, bg=C.surface)
        pad.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(pad, text="Technical details", bg=C.surface, fg=C.ink,
                font=(C.font_family, 14, "bold")).pack(anchor="w", pady=(0, 10))
        rows = [("Model architecture", "ResNet-152 (PyTorch)"),
               ("Model version", d.model_version),
               ("Referral threshold",
                f"P(grade ≥ Moderate) ≥ {self.app.settings.referral_threshold:.0%}"),
               ("SMS status", d.sms_status or "not sent")]
        for label, value in rows:
            row = tk.Frame(pad, bg=C.surface)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, bg=C.surface, fg=C.ink_dim, font=(C.font_family, 11),
                    width=22, anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=C.surface, fg=C.ink,
                    font=(C.font_family, 11, "bold"), anchor="w").pack(side="left")
        card.fit_to_content()
        return card

    def export_html(self) -> None:
        from drscreen.reporting import ReportContext, save_report

        self.export_btn.set_enabled(False)
        self.export_status.configure(text="Preparing export…")

        def build() -> Path:
            ctx = ReportContext(clinic_name=self.app.settings.clinic_name,
                               referral_threshold=self.app.settings.referral_threshold)
            return save_report(self.detail, ctx, self.app.settings.report_dir)

        def done(path: Path) -> None:
            self.export_btn.set_enabled(True)
            self.export_status.configure(text=f"Exported to {path.name}")
            webbrowser.open(path.as_uri())

        def failed(exc: BaseException) -> None:
            self.export_btn.set_enabled(True)
            self.export_status.configure(text="")
            messagebox.showerror("Could not export report", str(exc))

        self.app.run_async(build, done, failed)


# ============================================================================
# Settings — the frequently-changed knobs, editable without hand-editing .env
# ============================================================================

class SettingsView(tk.Frame):
    """Clinic name, referral threshold, default country code and SMS on/off —
    the settings an operator plausibly needs to change — persisted to
    ``.env`` so they survive a restart. Credentials (Twilio/Fast2SMS API
    keys) are shown as configured/not-configured only: those stay a
    deliberate file edit rather than a casual GUI text box.
    """

    def __init__(self, app: App):
        super().__init__(app, bg=C.bg1)
        self.app = app
        s = app.settings

        header = tk.Frame(self, bg=C.bg1)
        header.pack(fill="x", padx=24, pady=(20, 6))
        CanvasButton(header, "← Back", command=lambda: app.show_screening(app.operator),
                    variant="ghost", width=90, height=36,
                    font=(C.font_family, 11, "bold")).pack(side="left", padx=(0, 14))
        tk.Label(header, text="Settings", bg=C.bg1, fg=C.ink,
                font=(C.font_family, 18, "bold")).pack(side="left")

        scroll = ScrollableFrame(self, bg=C.bg1)
        scroll.pack(fill="both", expand=True)
        self._scroll = scroll
        body = tk.Frame(scroll.body, bg=C.bg1)
        body.pack(fill="both", expand=True, padx=24, pady=(4, 24))

        card = GlassPanel(body)
        card.pack(fill="x")
        pad = tk.Frame(card.body, bg=C.surface)
        pad.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(pad, text="Clinic", bg=C.surface, fg=C.ink,
                font=(C.font_family, 14, "bold")).pack(anchor="w", pady=(0, 12))

        self.clinic_name = tk.StringVar(value=s.clinic_name)
        self._field(pad, "CLINIC NAME (shown on reports and SMS)", self.clinic_name)
        self.country_code = tk.StringVar(value=s.default_country_code)
        self._field(pad, "DEFAULT COUNTRY CODE", self.country_code)
        self.threshold = tk.StringVar(value=f"{s.referral_threshold:.2f}")
        self._field(pad, "REFERRAL THRESHOLD — P(grade ≥ Moderate) to flag referral, 0-1",
                   self.threshold)
        self.sms_enabled = tk.BooleanVar(value=s.sms_enabled)
        ttk.Checkbutton(pad, text="SMS reports enabled", variable=self.sms_enabled,
                       style="Card.TCheckbutton").pack(anchor="w", pady=(6, 0))

        self.message = tk.Label(pad, text="", bg=C.surface, fg=C.danger,
                               font=(C.font_family, 11), anchor="w", justify="left")
        self.message.pack(anchor="w", fill="x", pady=(14, 4))
        CanvasButton(pad, "Save changes", command=self.save, variant="primary",
                    width=180, height=42).pack(anchor="w")
        card.fit_to_content()

        info_card = GlassPanel(body)
        info_card.pack(fill="x", pady=(16, 0))
        info_pad = tk.Frame(info_card.body, bg=C.surface)
        info_pad.pack(fill="both", expand=True, padx=20, pady=18)
        tk.Label(info_pad, text="Current configuration (read-only here — edit .env "
                              "directly for credentials)", bg=C.surface, fg=C.ink,
                font=(C.font_family, 14, "bold"), wraplength=560,
                justify="left").pack(anchor="w", pady=(0, 12))
        rows = [
            ("Model path", str(s.model_path)),
            ("Device", s.device),
            ("Database", _redact_url(s.database_url)),
            ("Twilio", "configured" if s.twilio.configured else "not configured"),
            ("Fast2SMS", "configured" if s.fast2sms.configured else "not configured "
                        "(sign up free at fast2sms.com)"),
        ]
        for label, value in rows:
            row = tk.Frame(info_pad, bg=C.surface)
            row.pack(fill="x", pady=3)
            tk.Label(row, text=label, bg=C.surface, fg=C.ink_dim, font=(C.font_family, 11),
                    width=16, anchor="w").pack(side="left")
            tk.Label(row, text=value, bg=C.surface, fg=C.ink, font=(C.font_family, 11, "bold"),
                    anchor="w", wraplength=380, justify="left").pack(side="left")
        info_card.fit_to_content()

    def activate(self) -> None:
        self._scroll.enable_wheel_scroll()

    def deactivate(self) -> None:
        self._scroll.disable_wheel_scroll()

    @staticmethod
    def _field(parent, label: str, var: tk.StringVar) -> None:
        tk.Label(parent, text=label, bg=C.surface, fg=C.ink_faint,
                font=(C.font_family, 9, "bold"), wraplength=560,
                justify="left").pack(anchor="w", pady=(8, 0))
        ttk.Entry(parent, textvariable=var).pack(fill="x", pady=(4, 0))

    def save(self) -> None:
        import dataclasses

        from drscreen.config import update_env

        clinic_name = self.clinic_name.get().strip()
        country_code = self.country_code.get().strip()
        if not clinic_name:
            self.message.configure(text="Clinic name can't be empty.")
            return
        if not country_code.startswith("+") or not country_code[1:].isdigit():
            self.message.configure(text="Country code must look like +91.")
            return
        try:
            threshold = float(self.threshold.get())
            if not 0.0 < threshold < 1.0:
                raise ValueError
        except ValueError:
            self.message.configure(text="Referral threshold must be a number between 0 and 1.")
            return

        update_env({
            "DRS_CLINIC_NAME": clinic_name,
            "DRS_DEFAULT_COUNTRY_CODE": country_code,
            "DRS_REFERRAL_THRESHOLD": f"{threshold:.4f}",
            "DRS_SMS_ENABLED": "true" if self.sms_enabled.get() else "false",
        })

        # Apply immediately to the running app, not just to the next launch.
        self.app.settings = dataclasses.replace(
            self.app.settings, clinic_name=clinic_name, default_country_code=country_code,
            referral_threshold=threshold, sms_enabled=self.sms_enabled.get())
        if self.app.service is not None:
            self.app.service.settings = self.app.settings
            self.app.service.predictor.referral_threshold = threshold
            from drscreen.notify import build_sender
            self.app.service.sms = build_sender(self.app.settings)

        self.message.configure(fg=C.success, text="Saved — applied immediately.")


# ============================================================================
# Recent screenings — its own page, reachable from a header button, so the
# main screening workflow (Patient + Result) never depends on scrolling past
# a history table to be usable.
# ============================================================================

class HistoryView(tk.Frame):
    def __init__(self, app: App):
        super().__init__(app, bg=C.bg1)
        self.app = app
        self._scroll: ScrollableFrame | None = None

        header = tk.Frame(self, bg=C.bg1)
        header.pack(fill="x", padx=24, pady=(20, 6))
        CanvasButton(header, "← Back", command=lambda: app.show_screening(app.operator),
                    variant="ghost", width=90, height=36,
                    font=(C.font_family, 11, "bold")).pack(side="left", padx=(0, 14))
        tk.Label(header, text="Recent Screenings", bg=C.bg1, fg=C.ink,
                font=(C.font_family, 18, "bold")).pack(side="left")
        CanvasButton(header, "Export CSV ⭳", command=self.export_csv, variant="ghost",
                    width=130, height=36, font=(C.font_family, 11, "bold")).pack(side="right")

        scroll = ScrollableFrame(self, bg=C.bg1)
        scroll.pack(fill="both", expand=True)
        self._scroll = scroll
        body = tk.Frame(scroll.body, bg=C.bg1)
        body.pack(fill="both", expand=True, padx=24, pady=(4, 24))

        card = GlassPanel(body)
        card.pack(fill="both", expand=True)
        pad = tk.Frame(card.body, bg=C.surface)
        pad.pack(fill="both", expand=True, padx=20, pady=18)

        filters = tk.Frame(pad, bg=C.surface)
        filters.pack(fill="x", pady=(0, 10))
        tk.Label(filters, text="Search patient", bg=C.surface, fg=C.ink_faint,
                font=(C.font_family, 9, "bold")).pack(side="left", padx=(0, 6))
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_a: self.refresh())
        self.search_entry = ttk.Entry(filters, textvariable=self.search_var, width=22)
        self.search_entry.pack(side="left")
        self.referrals_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(filters, text="Referrals only", variable=self.referrals_only,
                       command=self.refresh,
                       style="Card.TCheckbutton").pack(side="left", padx=14)

        cols = ("id", "time", "patient", "grade", "confidence", "referral", "sms")
        widths = (44, 140, 260, 200, 90, 80, 90)
        self.table = ttk.Treeview(pad, columns=cols, show="headings", height=16)
        for col, width in zip(cols, widths, strict=True):
            self.table.heading(col, text=col.capitalize())
            self.table.column(col, width=width, anchor="w", stretch=col == "patient")
        self.table.tag_configure("refer", foreground=C.grade4)
        self.table.tag_configure("safe", foreground=C.ink_dim)
        self.table.bind("<Double-1>", self._open_selected)
        self.table.pack(fill="both", expand=True, pady=(4, 0))
        tk.Label(pad, text="Double-click a row to open its full report.", bg=C.surface,
                fg=C.ink_faint, font=(C.font_family, 9, "italic")).pack(anchor="w", pady=(8, 0))
        card.fit_to_content()

        self.refresh()

    _SHORTCUTS = ("<Escape>", "<Control-f>", "<Command-f>")

    def activate(self) -> None:
        self.app.bind("<Escape>", lambda _e: self.app.show_screening(self.app.operator))
        self.app.bind("<Control-f>", lambda _e: self.search_entry.focus_set())
        self.app.bind("<Command-f>", lambda _e: self.search_entry.focus_set())
        if self._scroll is not None:
            self._scroll.enable_wheel_scroll()

    def deactivate(self) -> None:
        for seq in self._SHORTCUTS:
            self.app.unbind(seq)
        if self._scroll is not None:
            self._scroll.disable_wheel_scroll()

    def refresh(self) -> None:
        self.table.delete(*self.table.get_children())
        query = self.search_var.get().strip().lower()
        for r in self._filtered_rows(query):
            self.table.insert("", "end", tags=("refer" if r.referable else "safe",), values=(
                r.id, f"{r.created_at:%Y-%m-%d %H:%M}", r.patient_name, Grade(r.grade).label,
                f"{r.confidence:.1%}", "Yes" if r.referable else "No", r.sms_status or "—"))

    def _filtered_rows(self, query: str):
        rows = self.app.db.recent_screenings(500)
        if self.referrals_only.get():
            rows = [r for r in rows if r.referable]
        if query:
            rows = [r for r in rows if query in r.patient_name.lower()]
        return rows[:200]

    def _open_selected(self, _event: tk.Event) -> None:
        selection = self.table.selection()
        if not selection:
            return
        screening_id = int(self.table.item(selection[0], "values")[0])
        self.app.show_report(screening_id)

    def export_csv(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Export screening history as CSV", defaultextension=".csv",
            initialfile="drscreen_history.csv", filetypes=[("CSV", "*.csv")])
        if not path:
            return
        try:
            Path(path).write_text(self.app.db.export_csv(2000), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Export failed", str(exc))
            return
        messagebox.showinfo("Exported", f"History exported to {path}")


def _redact_url(url: str) -> str:
    from sqlalchemy.engine import make_url

    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return url


def run(settings: Settings) -> int:
    try:
        db = Database(settings.database_url)
        db.create_schema()
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Database unavailable",
                             f"Could not connect to the database:\n{exc}\n\n"
                             "Check DRS_DATABASE_URL in your .env file.")
        root.destroy()
        return 1
    App(settings, db).mainloop()
    return 0

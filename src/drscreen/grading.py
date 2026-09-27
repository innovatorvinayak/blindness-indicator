"""The 5-point DR severity scale used by APTOS 2019 (International Clinical DR scale)."""

from __future__ import annotations

from enum import IntEnum


class Grade(IntEnum):
    NO_DR = 0
    MILD = 1
    MODERATE = 2
    SEVERE = 3
    PROLIFERATIVE = 4

    @property
    def label(self) -> str:
        return _LABELS[self]

    @property
    def advice(self) -> str:
        return _ADVICE[self]

    @property
    def color(self) -> str:
        """Display colour (hex) used by the GUI."""
        return _COLORS[self]

    @property
    def is_referable(self) -> bool:
        """Referable DR is conventionally defined as moderate NPDR or worse."""
        return self >= Grade.MODERATE

    def __str__(self) -> str:
        return f"{self.label} (Class {int(self)})"


_LABELS = {
    Grade.NO_DR: "No Diabetic Retinopathy",
    Grade.MILD: "Mild DR",
    Grade.MODERATE: "Moderate DR",
    Grade.SEVERE: "Severe DR",
    Grade.PROLIFERATIVE: "Proliferative DR",
}

# Follow-up intervals loosely follow ICO/AAO screening guidance. They are
# suggestions for the screening operator, not a diagnosis.
_ADVICE = {
    Grade.NO_DR: "No signs of DR detected. Routine re-screening in 12 months.",
    Grade.MILD: "Early changes detected. Re-screen in 6-12 months and keep blood sugar controlled.",
    Grade.MODERATE: "Referable DR. Consult an ophthalmologist within 3 months.",
    Grade.SEVERE: "Advanced DR. Urgent ophthalmologist referral within 4 weeks.",
    Grade.PROLIFERATIVE: "Sight-threatening DR. See an ophthalmologist immediately.",
}

_COLORS = {
    Grade.NO_DR: "#1e8e3e",
    Grade.MILD: "#7cb342",
    Grade.MODERATE: "#f9a825",
    Grade.SEVERE: "#ef6c00",
    Grade.PROLIFERATIVE: "#c62828",
}

NUM_GRADES = len(Grade)

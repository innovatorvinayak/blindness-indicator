"""Is this actually a fundus photograph?

The classifier will happily grade a photo of a car park — softmax always
returns *something*, and that something looks like a real clinical result to
an operator. So anything uploaded is screened here first.

Two tiers, because one is not enough:

1. **Heuristics (always on, instant, offline).** These reject the obvious
   negatives — screenshots, documents, blank frames, blue/green scenes — and
   are deliberately *permissive* in the warm-and-textured band. A false
   reject blocks a real patient's screening, which is worse than passing a
   doubtful image to tier 2.

2. **A vision model via Ollama (optional).** Colour statistics genuinely
   cannot separate a desaturated fundus photograph from, say, a warm-lit
   close-up of skin — the bundled ``eye3.png`` is less red-dominant than a
   plain skin tone. Only something that understands image *content* can
   settle that, so :mod:`drscreen.vision` is asked to confirm when it is
   configured. When it isn't, the heuristic verdict stands and the result
   says the confirmation was skipped.

Thresholds are calibrated against the bundled ``sampleimages/`` — which are
awkward on purpose, several being screenshots with white plot borders and
axis labels — and against a set of negatives. See ``tests/test_retina.py``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image

# Weighted-signal score a borderline image must reach to be accepted.
ACCEPT_SCORE = 0.55

# Below this luminance spread there is no anatomy in the frame at all — no
# vessels, no disc, just a flat wash of colour. A retina is never flat, so
# this is a hard gate rather than one more weighted signal (without it, a
# plain skin-coloured rectangle scores like a fundus on colour alone).
MIN_STRUCTURE = 0.02


@dataclass(frozen=True)
class RetinaCheck:
    """Verdict plus the measurements behind it, so the UI can explain itself."""

    is_fundus: bool
    score: float
    reasons: tuple[str, ...]
    red_dominance: float
    blue_ratio: float
    warm_hue_fraction: float
    lit_fraction: float
    structure: float

    def to_dict(self) -> dict:
        return {
            "is_fundus": self.is_fundus,
            "score": round(self.score, 3),
            "reasons": list(self.reasons),
            "metrics": {
                "red_dominance": round(self.red_dominance, 3),
                "blue_ratio": round(self.blue_ratio, 3),
                "warm_hue_fraction": round(self.warm_hue_fraction, 3),
                "lit_fraction": round(self.lit_fraction, 3),
                "structure": round(self.structure, 4),
            },
        }


def check_fundus(image: Image.Image) -> RetinaCheck:
    """Decide whether ``image`` looks like a retinal fundus photograph."""
    thumb = image.convert("RGB").resize((256, 256), Image.BILINEAR)
    rgb = np.asarray(thumb, dtype=np.float32) / 255.0
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]

    luma = 0.299 * r + 0.587 * g + 0.114 * b
    # Ignore the dark surround outside the camera aperture; the colour of
    # "nothing" says nothing about whether this is a retina.
    lit = luma > 0.12
    lit_fraction = float(lit.mean())

    def verdict(reason: str) -> RetinaCheck:
        return RetinaCheck(False, 0.0, (reason,), 0.0, 0.0, 0.0, lit_fraction, 0.0)

    if lit_fraction < 0.05:
        return verdict("The image is almost entirely black — no retinal field is visible.")

    r_m, g_m, b_m = float(r[lit].mean()), float(g[lit].mean()), float(b[lit].mean())
    red_dominance = r_m - 0.5 * (g_m + b_m)
    blue_ratio = b_m / max(r_m, 1e-6)

    # Warm pixels: red clearly strongest, and blue no higher than green —
    # the R > G > B ordering a retina holds even when badly white-balanced.
    warm = lit & (r > g + 0.02) & (g >= b - 0.03)
    warm_hue_fraction = float(warm.sum() / max(lit.sum(), 1))

    # Structure: luminance spread across the lit field. Vessels, the optic
    # disc and the macula all contribute; a flat colour patch scores ~0.
    structure = float(luma[lit].std())

    if structure < MIN_STRUCTURE:
        return verdict(
            "The image is a flat wash of colour with no visible anatomy — no vessels, "
            "optic disc or macula. A retinal photograph always shows vascular structure."
        )

    scores = {
        "warm_hue": _ramp(warm_hue_fraction, 0.35, 0.80),
        "red_dominance": _ramp(red_dominance, 0.02, 0.20),
        "blue_starvation": _ramp(1.0 - blue_ratio, 0.10, 0.60),
        "lit_field": _ramp(lit_fraction, 0.10, 0.35),
    }
    # Hue is the most reliable single cue across both vivid and washed-out
    # fundus images; raw redness varies far too much between cameras to lead.
    weights = {"warm_hue": 0.45, "red_dominance": 0.22,
               "blue_starvation": 0.13, "lit_field": 0.20}
    score = sum(scores[k] * weights[k] for k in scores)

    reasons: list[str] = []
    if scores["warm_hue"] < 0.5:
        reasons.append(
            "The colours are spread across the spectrum rather than clustered in the "
            "red-orange range a retina shows. This does not look like a fundus photograph."
        )
    if scores["red_dominance"] < 0.35 and scores["blue_starvation"] < 0.35:
        reasons.append(
            "The image is not red-dominant. Fundus photographs are lit through "
            "blood-filled tissue and look distinctly red, orange or amber."
        )
    if scores["lit_field"] < 0.5:
        reasons.append("Too little of the frame is lit to contain a usable retinal field.")

    is_fundus = score >= ACCEPT_SCORE
    if not is_fundus and not reasons:
        reasons.append("The image does not resemble a retinal fundus photograph.")

    return RetinaCheck(is_fundus, score, tuple(reasons), red_dominance, blue_ratio,
                       warm_hue_fraction, lit_fraction, structure)


def _ramp(value: float, low: float, high: float) -> float:
    """Map ``value`` onto 0..1, flat below ``low`` and above ``high``."""
    if high <= low:
        return 1.0 if value >= high else 0.0
    return float(min(1.0, max(0.0, (value - low) / (high - low))))

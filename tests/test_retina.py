"""The fundus gate must never block a real patient, and must catch the
obvious mistakes. Both directions are asserted against real sample images
and synthetic negatives."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw

from drscreen.retina import ACCEPT_SCORE, check_fundus

SAMPLES = sorted(
    p for p in (Path(__file__).resolve().parents[1] / "sampleimages").glob("*")
    if p.suffix.lower() in {".png", ".jpg", ".jpeg"}
)


@pytest.mark.skipif(not SAMPLES, reason="sampleimages/ not present")
@pytest.mark.parametrize("path", SAMPLES, ids=lambda p: p.name)
def test_real_fundus_images_are_accepted(path: Path):
    """A false reject blocks a real screening, so this is the critical direction.

    The samples deliberately include awkward cases: screenshots with white
    plot borders and axis labels, and desaturated captures (eye3) that are
    less red-dominant than plain skin.
    """
    check = check_fundus(Image.open(path))
    assert check.is_fundus, f"{path.name} rejected (score {check.score:.3f}): {check.reasons}"


def _solid(color: tuple[int, int, int]) -> Image.Image:
    return Image.new("RGB", (400, 400), color)


def test_blank_and_flat_images_are_rejected():
    for name, image in {
        "white": _solid((255, 255, 255)),
        "black": _solid((0, 0, 0)),
        "blue": _solid((110, 160, 230)),
        "green": _solid((70, 140, 60)),
        # Red-dominant and warm, but with no anatomy — colour alone would
        # let this through, which is why structure is a hard gate.
        "flat skin tone": _solid((224, 172, 140)),
    }.items():
        assert not check_fundus(image).is_fundus, f"{name} wrongly accepted"


def test_document_and_ui_screenshots_are_rejected():
    doc = _solid((250, 250, 248))
    draw = ImageDraw.Draw(doc)
    for i in range(12):
        draw.rectangle([40, 30 + i * 28, 360, 44 + i * 28], fill=(40, 40, 45))
    assert not check_fundus(doc).is_fundus

    ui = _solid((18, 22, 32))
    draw = ImageDraw.Draw(ui)
    for i in range(8):
        draw.rectangle([30, 30 + i * 44, 370, 60 + i * 44],
                       fill=(34, 211, 238) if i % 3 else (139, 92, 246))
    assert not check_fundus(ui).is_fundus


def test_rejection_explains_itself():
    check = check_fundus(_solid((110, 160, 230)))
    assert not check.is_fundus
    assert check.reasons, "a rejection must tell the operator why"
    assert all(isinstance(r, str) and r for r in check.reasons)


def test_metrics_are_serialisable():
    payload = check_fundus(_solid((224, 172, 140))).to_dict()
    assert payload["is_fundus"] is False
    assert set(payload["metrics"]) == {
        "red_dominance", "blue_ratio", "warm_hue_fraction", "lit_fraction", "structure",
    }


@pytest.mark.skipif(not SAMPLES, reason="sampleimages/ not present")
def test_real_images_clear_the_threshold_with_margin():
    """Guards against a future tweak quietly moving a real image to the edge."""
    scores = [check_fundus(Image.open(p)).score for p in SAMPLES]
    assert min(scores) > ACCEPT_SCORE, f"weakest sample only scored {min(scores):.3f}"


def test_pure_noise_is_rejected():
    rng = np.random.default_rng(0)
    noise = rng.integers(0, 255, (400, 400, 3), dtype=np.uint8)
    assert not check_fundus(Image.fromarray(noise)).is_fundus

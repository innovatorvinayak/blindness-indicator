from __future__ import annotations

import math

import pytest
import torch
from PIL import Image

from drscreen.grading import Grade
from drscreen.inference import Predictor
from drscreen.model import (
    CheckpointError,
    ModelMetadata,
    build_model,
    convert_legacy_checkpoint,
    load_checkpoint,
    set_trainable,
)
from drscreen.preprocessing import eval_transform, load_image
from tests.conftest import SAMPLE_DIR, TEST_ARCH


def test_head_is_compatible_with_published_resnet152_weights():
    """The original classifier.pt uses keys fc.0.* and fc.2.* — they must not move."""
    keys = {k for k in build_model("resnet152").state_dict() if k.startswith("fc.")}
    assert keys == {"fc.0.weight", "fc.0.bias", "fc.2.weight", "fc.2.bias"}


def test_set_trainable_freezes_stem_and_layer1(tiny_model):
    model = build_model(TEST_ARCH)
    set_trainable(model)
    assert not any(p.requires_grad for p in model.conv1.parameters())
    assert not any(p.requires_grad for p in model.layer1.parameters())
    assert all(p.requires_grad for p in model.layer4.parameters())
    assert all(p.requires_grad for p in model.fc.parameters())


def test_checkpoint_roundtrip_preserves_weights_and_metadata(checkpoint, tiny_model):
    model, meta = load_checkpoint(checkpoint)
    assert meta.arch == TEST_ARCH and meta.image_size == 64 and meta.version == "test-v1"
    for (k, a), b in zip(model.state_dict().items(), tiny_model.state_dict().values(),
                         strict=True):
        assert torch.equal(a, b), k


def test_missing_checkpoint_gives_actionable_error(tmp_path):
    with pytest.raises(CheckpointError, match="DRS_MODEL_PATH"):
        load_checkpoint(tmp_path / "nope.pt")


def test_legacy_pickled_checkpoint_is_refused_then_convertible(tmp_path, tiny_model):
    """Reproduces the original Kaggle save format, which pickles the whole module."""
    legacy = tmp_path / "classifier.pt"
    torch.save({"epoch": 99, "model": tiny_model, "model_state_dict": tiny_model.state_dict(),
                "optimizer_state_dict": {}, "loss": 0.1}, legacy)

    with pytest.raises(CheckpointError, match="convert-weights"):
        load_checkpoint(legacy)

    converted = tmp_path / "classifier_v2.pt"
    # Legacy metadata assumes resnet152; patch it for the tiny test model.
    import drscreen.model as m
    original = m.LEGACY_METADATA
    m.LEGACY_METADATA = ModelMetadata(arch=TEST_ARCH, channel_order="BGR", version="legacy")
    try:
        meta = convert_legacy_checkpoint(legacy, converted)
    finally:
        m.LEGACY_METADATA = original
    assert meta.channel_order == "BGR"
    _, loaded = load_checkpoint(converted)
    assert loaded.channel_order == "BGR" and loaded.version == "legacy"


def test_bgr_transform_swaps_channels():
    img = Image.new("RGB", (8, 8), (255, 0, 0))
    rgb = eval_transform(8, "RGB")(img)
    bgr = eval_transform(8, "BGR")(img)
    assert rgb[0].mean() > rgb[2].mean()
    assert bgr[2].mean() > bgr[0].mean()


def test_rgba_images_are_flattened_onto_black():
    rgba = Image.new("RGBA", (10, 10), (255, 255, 255, 0))
    assert load_image(rgba).getpixel((0, 0)) == (0, 0, 0)


def test_prediction_is_deterministic_and_well_formed(checkpoint, fundus_image):
    predictor = Predictor.from_checkpoint(checkpoint, device="cpu")
    a, b = predictor.predict(fundus_image), predictor.predict(fundus_image)
    assert a.probabilities == b.probabilities
    assert math.isclose(sum(a.probabilities), 1.0, rel_tol=1e-5)
    assert isinstance(a.grade, Grade)
    assert a.confidence == max(a.probabilities)
    assert a.referral_probability == pytest.approx(sum(a.probabilities[2:]))
    assert a.image_sha256 and len(a.image_sha256) == 64
    assert a.to_dict()["label"] == a.grade.label


def test_referral_threshold_controls_flag(checkpoint, fundus_image):
    model, meta = load_checkpoint(checkpoint)
    strict = Predictor(model, meta, referral_threshold=1e-9).predict(fundus_image)
    lax = Predictor(model, meta, referral_threshold=1.0 - 1e-9).predict(fundus_image)
    assert strict.referable is True
    assert lax.referable is False


@pytest.mark.skipif(not SAMPLE_DIR.exists(), reason="sample images not present")
def test_all_bundled_sample_images_run_end_to_end(checkpoint):
    predictor = Predictor.from_checkpoint(checkpoint, device="cpu", tta=False)
    files = sorted(SAMPLE_DIR.iterdir())
    preds = predictor.predict_batch(files, batch_size=4)
    assert len(preds) == len(files) == 20
    assert all(0 <= int(p.grade) <= 4 for p in preds)

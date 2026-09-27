from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import torch
from PIL import Image

from drscreen.config import Settings
from drscreen.model import ModelMetadata, build_model, save_checkpoint

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "sampleimages"

# resnet18 keeps the suite fast; every code path is architecture-agnostic.
TEST_ARCH = "resnet18"


@pytest.fixture(scope="session")
def tiny_model() -> torch.nn.Module:
    torch.manual_seed(0)
    return build_model(TEST_ARCH).eval()


@pytest.fixture(scope="session")
def checkpoint(tmp_path_factory, tiny_model) -> Path:
    path = tmp_path_factory.mktemp("models") / "tiny.pt"
    meta = ModelMetadata(arch=TEST_ARCH, image_size=64, version="test-v1")
    return save_checkpoint(path, tiny_model, meta)


@pytest.fixture
def fundus_image(tmp_path) -> Path:
    """A synthetic fundus-like image: bright disc on a black background."""
    yy, xx = np.mgrid[:256, :256]
    disc = ((yy - 128) ** 2 + (xx - 128) ** 2) < 110**2
    rgb = np.zeros((256, 256, 3), dtype=np.uint8)
    rgb[disc] = (180, 80, 40)
    rgb[(yy - 110) ** 2 + (xx - 160) ** 2 < 15**2] = (250, 220, 150)  # optic disc
    path = tmp_path / "fundus.png"
    Image.fromarray(rgb).save(path)
    return path


@pytest.fixture
def settings(tmp_path, checkpoint) -> Settings:
    return Settings(
        model_path=checkpoint,
        device="cpu",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        image_store=tmp_path / "images",
        clinic_name="Test Clinic",
    )

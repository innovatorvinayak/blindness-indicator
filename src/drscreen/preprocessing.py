"""Image loading and tensor transforms shared by training, evaluation and inference.

Keeping a single definition here is what prevents train/serve skew. The original
project trained on images read with ``cv2.imread`` (BGR channel order) but served
predictions on PIL images (RGB), so the deployed model saw colour-swapped inputs.
The channel order a checkpoint was trained with is now recorded in its metadata and
honoured here.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Literal

import numpy as np
import torch
from PIL import Image, ImageFile, ImageOps
from torchvision import transforms as T

ImageFile.LOAD_TRUNCATED_IMAGES = True

ChannelOrder = Literal["RGB", "BGR"]
ImageSource = str | Path | bytes | BinaryIO | Image.Image

IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)
SUPPORTED_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"})
MIN_IMAGE_SIDE = 128


def load_image(source: ImageSource) -> Image.Image:
    """Load any supported image source as an RGB PIL image.

    Transparent pixels are composited onto black, which matches the dark
    background around a fundus photograph.
    """
    if isinstance(source, Image.Image):
        image = source
    elif isinstance(source, bytes):
        image = Image.open(io.BytesIO(source))
    else:
        image = Image.open(source)
    image = ImageOps.exif_transpose(image)
    image.load()

    if image.mode in ("RGBA", "LA", "P"):
        image = image.convert("RGBA")
        background = Image.new("RGBA", image.size, (0, 0, 0, 255))
        image = Image.alpha_composite(background, image)
    return image.convert("RGB")


@dataclass(frozen=True)
class QualityReport:
    width: int
    height: int
    mean_brightness: float
    warnings: tuple[str, ...]

    @property
    def gradable(self) -> bool:
        return not self.warnings


def assess_quality(image: Image.Image) -> QualityReport:
    """Cheap heuristics that catch obviously ungradable uploads before inference."""
    width, height = image.size
    gray = np.asarray(image.convert("L"), dtype=np.float32)
    mean = float(gray.mean())
    warnings: list[str] = []
    if min(width, height) < MIN_IMAGE_SIDE:
        warnings.append(f"Low resolution ({width}x{height}); results may be unreliable.")
    if mean < 12:
        warnings.append("Image is very dark; it may be under-exposed or not a fundus photo.")
    elif mean > 200:
        warnings.append("Image is very bright; it may be over-exposed or not a fundus photo.")
    if float(gray.std()) < 8:
        warnings.append("Image has almost no contrast; check that the correct file was chosen.")
    return QualityReport(width, height, mean, tuple(warnings))


class _ToChannelOrder(torch.nn.Module):
    def __init__(self, order: ChannelOrder):
        super().__init__()
        if order not in ("RGB", "BGR"):
            raise ValueError(f"Unsupported channel order: {order!r}")
        self.order = order

    def forward(self, tensor: torch.Tensor) -> torch.Tensor:
        return tensor.flip(-3) if self.order == "BGR" else tensor


def eval_transform(image_size: int = 224, channel_order: ChannelOrder = "RGB") -> T.Compose:
    """Deterministic transform used for validation and inference.

    (The legacy code applied ``RandomHorizontalFlip`` at inference time, which made
    predictions for the same image non-deterministic.)
    """
    return T.Compose([
        T.Resize((image_size, image_size), antialias=True),
        T.ToTensor(),
        _ToChannelOrder(channel_order),
        T.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])


def train_transform(image_size: int = 224, channel_order: ChannelOrder = "RGB") -> T.Compose:
    """Augmentations that respect fundus geometry: the retina has no canonical rotation."""
    return T.Compose([
        T.RandomResizedCrop(image_size, scale=(0.85, 1.0), ratio=(0.9, 1.1), antialias=True),
        T.RandomHorizontalFlip(),
        T.RandomVerticalFlip(),
        T.RandomRotation(180),
        T.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.1),
        T.ToTensor(),
        _ToChannelOrder(channel_order),
        T.Normalize(IMAGENET_MEAN, IMAGENET_STD),
    ])


def iter_image_files(paths: list[Path]) -> list[Path]:
    """Expand files and directories into a sorted list of supported image files."""
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(
                p for p in sorted(path.iterdir())
                if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS
            )
        elif path.is_file():
            found.append(path)
        else:
            raise FileNotFoundError(path)
    return found

"""Single-image and batch prediction."""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import torch
from PIL import Image
from torch import nn

from drscreen.grading import Grade
from drscreen.model import ModelMetadata, load_checkpoint, resolve_device
from drscreen.preprocessing import ImageSource, assess_quality, eval_transform, load_image


@dataclass(frozen=True)
class Prediction:
    grade: Grade
    probabilities: tuple[float, ...]
    referral_probability: float
    referable: bool
    model_version: str
    warnings: tuple[str, ...] = ()
    image_sha256: str | None = None
    source: str | None = None

    @property
    def confidence(self) -> float:
        return self.probabilities[self.grade]

    @property
    def expected_grade(self) -> float:
        """Probability-weighted severity; a useful ordinal score for ranking/triage."""
        return sum(i * p for i, p in enumerate(self.probabilities))

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "grade": int(self.grade),
            "label": self.grade.label,
            "confidence": round(self.confidence, 4),
            "probabilities": {
                g.label: round(p, 4) for g, p in zip(Grade, self.probabilities, strict=True)
            },
            "referral_probability": round(self.referral_probability, 4),
            "referable": self.referable,
            "expected_grade": round(self.expected_grade, 3),
            "advice": self.grade.advice,
            "warnings": list(self.warnings),
            "model_version": self.model_version,
            "image_sha256": self.image_sha256,
        }


class Predictor:
    """Thread-safe wrapper around a loaded model.

    ``tta`` averages the prediction over the image and its horizontal mirror, which
    reduces variance at 2x the compute. The referral decision is made on
    P(grade >= Moderate) rather than on the arg-max grade, so the operating point can
    be tuned towards sensitivity (see ``drscreen evaluate --sweep``).
    """

    def __init__(self, model: nn.Module, metadata: ModelMetadata,
                 device: torch.device | str = "cpu", *, tta: bool = True,
                 referral_threshold: float = 0.5):
        self.device = torch.device(device)
        self.model = model.to(self.device).eval()
        self.metadata = metadata
        self.tta = tta
        self.referral_threshold = referral_threshold
        self.transform = eval_transform(metadata.image_size, metadata.channel_order)
        self._lock = threading.Lock()

    @classmethod
    def from_checkpoint(cls, path: str | Path, device: str = "auto", **kwargs) -> Predictor:
        resolved = resolve_device(device)
        model, metadata = load_checkpoint(path, resolved)
        return cls(model, metadata, resolved, **kwargs)

    def predict(self, source: ImageSource) -> Prediction:
        return self.predict_batch([source])[0]

    def predict_batch(self, sources: Sequence[ImageSource], batch_size: int = 8
                      ) -> list[Prediction]:
        results: list[Prediction] = []
        for start in range(0, len(sources), batch_size):
            chunk = sources[start:start + batch_size]
            images = [load_image(s) for s in chunk]
            probs = self.predict_proba(images)
            for source, image, row in zip(chunk, images, probs.tolist(), strict=True):
                results.append(self._to_prediction(source, image, row))
        return results

    def predict_proba(self, images: Iterable[Image.Image]) -> torch.Tensor:
        batch = torch.stack([self.transform(img) for img in images]).to(self.device)
        with self._lock, torch.inference_mode():
            probs = self.model(batch).softmax(dim=1)
            if self.tta:
                probs = (probs + self.model(batch.flip(-1)).softmax(dim=1)) / 2
        return probs.float().cpu()

    def _to_prediction(self, source: ImageSource, image: Image.Image,
                       probs: list[float]) -> Prediction:
        grade = Grade(max(range(len(probs)), key=probs.__getitem__))
        referral_probability = sum(probs[Grade.MODERATE:])
        return Prediction(
            grade=grade,
            probabilities=tuple(probs),
            referral_probability=referral_probability,
            referable=referral_probability >= self.referral_threshold,
            model_version=self.metadata.version,
            warnings=assess_quality(image).warnings,
            image_sha256=_sha256(source),
            source=str(source) if isinstance(source, (str, Path)) else None,
        )


def _sha256(source: ImageSource) -> str | None:
    if isinstance(source, bytes):
        return hashlib.sha256(source).hexdigest()
    if isinstance(source, (str, Path)):
        digest = hashlib.sha256()
        with open(source, "rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                digest.update(block)
        return digest.hexdigest()
    return None

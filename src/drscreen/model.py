"""Network definition and checkpoint I/O.

The classifier head keeps the exact layer indices of the original project
(``fc.0`` Linear -> ``fc.1`` ReLU -> ``fc.2`` Linear), so the published APTOS
``classifier.pt`` weights load unchanged. The trailing ``LogSoftmax`` was dropped:
it has no parameters, and emitting raw logits lets training use ``CrossEntropyLoss``
with label smoothing and class weights.
"""

from __future__ import annotations

import logging
import pickle
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from torch import nn
from torchvision import models

from drscreen.grading import NUM_GRADES
from drscreen.preprocessing import ChannelOrder

log = logging.getLogger(__name__)

CHECKPOINT_FORMAT = "drscreen/v1"
# Backbone stages fine-tuned by default; the stem and layer1 learn generic edges and
# stay frozen, as in the original training run.
DEFAULT_TRAINABLE = ("layer2", "layer3", "layer4", "fc")


class CheckpointError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelMetadata:
    arch: str = "resnet152"
    num_classes: int = NUM_GRADES
    image_size: int = 224
    channel_order: ChannelOrder = "RGB"
    version: str = "unversioned"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metrics: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ModelMetadata:
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)


# The original Kaggle-trained weights: ResNet-152, 224px, fed BGR tensors by cv2.
LEGACY_METADATA = ModelMetadata(
    arch="resnet152", image_size=224, channel_order="BGR",
    version="aptos2019-legacy", created_at="2019-09-01T00:00:00+00:00",
)


def build_model(arch: str = "resnet152", num_classes: int = NUM_GRADES,
                pretrained: bool = False) -> nn.Module:
    """Build a ResNet backbone with the project's two-layer classification head."""
    if not arch.startswith("resnet"):
        raise ValueError(f"Only ResNet backbones are supported, got {arch!r}")
    weights = "DEFAULT" if pretrained else None
    model = models.get_model(arch, weights=weights)
    in_features = model.fc.in_features
    model.fc = nn.Sequential(
        nn.Linear(in_features, 512),
        nn.ReLU(inplace=True),
        nn.Linear(512, num_classes),
    )
    return model


def set_trainable(model: nn.Module, stages: tuple[str, ...] = DEFAULT_TRAINABLE) -> int:
    """Freeze every top-level child not listed in ``stages``. Returns #trainable params."""
    for name, child in model.named_children():
        for param in child.parameters():
            param.requires_grad = name in stages
    return sum(p.numel() for p in model.parameters() if p.requires_grad)


def resolve_device(preference: str = "auto") -> torch.device:
    if preference != "auto":
        return torch.device(preference)
    if torch.cuda.is_available():
        return torch.device("cuda")
    if torch.backends.mps.is_available():
        return torch.device("mps")
    return torch.device("cpu")


def save_checkpoint(path: str | Path, model: nn.Module, metadata: ModelMetadata,
                    **extra: Any) -> Path:
    """Write a checkpoint containing only tensors and plain data (safe to load)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "format": CHECKPOINT_FORMAT,
        "metadata": asdict(metadata),
        "model_state_dict": model.state_dict(),
        **extra,
    }
    tmp = path.with_suffix(path.suffix + ".tmp")
    torch.save(payload, tmp)
    tmp.replace(path)  # atomic: a crash mid-save never corrupts the previous best model
    return path


def load_checkpoint(path: str | Path, device: torch.device | str = "cpu"
                    ) -> tuple[nn.Module, ModelMetadata]:
    """Load a checkpoint with ``weights_only=True`` (no arbitrary code execution).

    Legacy checkpoints that pickled the whole ``nn.Module`` cannot be loaded safely;
    convert them once with ``drscreen convert-weights``.
    """
    path = Path(path)
    if not path.is_file():
        raise CheckpointError(
            f"Model weights not found at {path}. Download classifier.pt (see README) "
            "or set DRS_MODEL_PATH."
        )
    try:
        payload = torch.load(path, map_location="cpu", weights_only=True)
    except pickle.UnpicklingError as exc:
        raise CheckpointError(
            f"{path.name} is a legacy checkpoint that embeds pickled Python objects and "
            "cannot be loaded safely. Convert it once with:\n"
            f"  drscreen convert-weights {path} {path.with_name('classifier_v2.pt')} --trust"
        ) from exc
    return _model_from_payload(payload, device)


def convert_legacy_checkpoint(src: str | Path, dst: str | Path) -> ModelMetadata:
    """Re-save a trusted legacy checkpoint in the safe, metadata-carrying format.

    This unpickles ``src`` with ``weights_only=False``: only call it on a file whose
    origin you trust.
    """
    payload = torch.load(Path(src), map_location="cpu", weights_only=False)
    state_dict = _extract_state_dict(payload)
    metadata = ModelMetadata.from_dict(payload.get("metadata", {})) \
        if isinstance(payload, dict) and payload.get("format") == CHECKPOINT_FORMAT \
        else LEGACY_METADATA
    model = build_model(metadata.arch, metadata.num_classes)
    _load_state_dict(model, state_dict)
    save_checkpoint(dst, model, metadata)
    return metadata


def _model_from_payload(payload: Any, device: torch.device | str
                        ) -> tuple[nn.Module, ModelMetadata]:
    is_v1 = isinstance(payload, dict) and payload.get("format") == CHECKPOINT_FORMAT
    metadata = ModelMetadata.from_dict(payload["metadata"]) if is_v1 else LEGACY_METADATA
    model = build_model(metadata.arch, metadata.num_classes)
    _load_state_dict(model, _extract_state_dict(payload))
    model.to(device).eval()
    return model, metadata


def _extract_state_dict(payload: Any) -> dict[str, torch.Tensor]:
    if isinstance(payload, dict):
        if "model_state_dict" in payload:
            state = payload["model_state_dict"]
        elif "state_dict" in payload:
            state = payload["state_dict"]
        elif all(isinstance(v, torch.Tensor) for v in payload.values()):
            state = payload
        else:
            raise CheckpointError("Checkpoint does not contain a model state_dict")
    elif isinstance(payload, nn.Module):
        state = payload.state_dict()
    else:
        raise CheckpointError(f"Unrecognised checkpoint payload: {type(payload).__name__}")
    # Strip the prefix added when a model is saved from nn.DataParallel.
    return {k.removeprefix("module."): v for k, v in state.items()}


def _load_state_dict(model: nn.Module, state_dict: dict[str, torch.Tensor]) -> None:
    try:
        model.load_state_dict(state_dict, strict=True)
    except RuntimeError as exc:
        raise CheckpointError(f"Weights do not match the model architecture: {exc}") from exc

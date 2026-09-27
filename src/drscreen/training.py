"""Reproducible fine-tuning of the ResNet classifier on APTOS 2019."""

from __future__ import annotations

import json
import logging
import random
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader

from drscreen.data import FundusDataset, class_weights, read_labels, stratified_split
from drscreen.metrics import quadratic_weighted_kappa
from drscreen.model import (
    DEFAULT_TRAINABLE,
    ModelMetadata,
    build_model,
    load_checkpoint,
    resolve_device,
    save_checkpoint,
    set_trainable,
)
from drscreen.preprocessing import eval_transform, train_transform

log = logging.getLogger(__name__)


@dataclass
class TrainConfig:
    csv: Path
    image_dir: Path
    output: Path = Path("models/classifier_v2.pt")
    arch: str = "resnet152"
    image_size: int = 224
    epochs: int = 30
    batch_size: int = 32
    lr: float = 3e-4
    weight_decay: float = 1e-4
    label_smoothing: float = 0.05
    valid_fraction: float = 0.2
    patience: int = 6
    seed: int = 42
    workers: int = 4
    device: str = "auto"
    pretrained: bool = True
    init_from: Path | None = None  # fine-tune further from an existing checkpoint
    trainable: tuple[str, ...] = DEFAULT_TRAINABLE
    limit: int | None = None  # use only N samples (smoke tests / debugging)
    version: str = field(default_factory=lambda: time.strftime("v%Y%m%d-%H%M"))


def seed_everything(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def train(cfg: TrainConfig) -> dict:
    seed_everything(cfg.seed)
    device = resolve_device(cfg.device)
    samples = read_labels(cfg.csv, cfg.image_dir)
    if cfg.limit:
        samples = random.Random(cfg.seed).sample(samples, min(cfg.limit, len(samples)))
    train_set, valid_set = stratified_split(samples, cfg.valid_fraction, cfg.seed)
    log.info("train=%d valid=%d device=%s", len(train_set), len(valid_set), device)

    if cfg.init_from:
        # Keep the parent checkpoint's input contract (arch, size, channel order).
        model, parent = load_checkpoint(cfg.init_from)
        arch, image_size, channel_order = parent.arch, parent.image_size, parent.channel_order
    else:
        model = build_model(cfg.arch, pretrained=cfg.pretrained)
        arch, image_size, channel_order = cfg.arch, cfg.image_size, "RGB"
    n_trainable = set_trainable(model, cfg.trainable)
    model.to(device)
    log.info("trainable parameters: %s", f"{n_trainable:,}")

    loader_kwargs = {"batch_size": cfg.batch_size, "num_workers": cfg.workers,
                     "pin_memory": device.type == "cuda",
                     "persistent_workers": cfg.workers > 0}
    train_loader = DataLoader(FundusDataset(train_set, train_transform(image_size, channel_order)),
                              shuffle=True, drop_last=len(train_set) > cfg.batch_size,
                              **loader_kwargs)
    valid_loader = DataLoader(FundusDataset(valid_set, eval_transform(image_size, channel_order)),
                              shuffle=False, **loader_kwargs)

    criterion = nn.CrossEntropyLoss(weight=class_weights(train_set).to(device),
                                    label_smoothing=cfg.label_smoothing)
    optimizer = torch.optim.AdamW((p for p in model.parameters() if p.requires_grad),
                                  lr=cfg.lr, weight_decay=cfg.weight_decay)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(
        optimizer, max_lr=cfg.lr, epochs=cfg.epochs, steps_per_epoch=len(train_loader))
    use_amp = device.type == "cuda"
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)

    history: list[dict] = []
    best_kappa, stale = -1.0, 0
    for epoch in range(1, cfg.epochs + 1):
        started = time.perf_counter()
        model.train()
        running = 0.0
        for images, labels in train_loader:
            images, labels = images.to(device, non_blocking=True), labels.to(device)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device.type, enabled=use_amp):
                loss = criterion(model(images), labels)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            scaler.step(optimizer)
            scaler.update()
            scheduler.step()
            running += loss.item() * labels.size(0)

        val = _validate(model, valid_loader, criterion, device)
        row = {"epoch": epoch, "train_loss": running / len(train_set), **val,
               "seconds": round(time.perf_counter() - started, 1)}
        history.append(row)
        log.info("epoch %d/%d train_loss=%.4f val_loss=%.4f acc=%.4f qwk=%.4f",
                 epoch, cfg.epochs, row["train_loss"], val["val_loss"],
                 val["val_accuracy"], val["val_qwk"])

        # Model selection on QWK (the competition metric), not raw accuracy.
        if val["val_qwk"] > best_kappa:
            best_kappa, stale = val["val_qwk"], 0
            metadata = ModelMetadata(
                arch=arch, image_size=image_size, channel_order=channel_order,
                version=cfg.version,
                metrics={k: round(v, 4) for k, v in val.items()} | {"epoch": epoch},
            )
            save_checkpoint(cfg.output, model, metadata, epoch=epoch)
            log.info("saved new best model to %s", cfg.output)
        else:
            stale += 1
            if stale >= cfg.patience:
                log.info("early stopping: no QWK improvement for %d epochs", cfg.patience)
                break

    summary = {"config": {k: str(v) for k, v in asdict(cfg).items()},
               "best_val_qwk": best_kappa, "history": history}
    cfg.output.with_suffix(".history.json").write_text(json.dumps(summary, indent=2))
    return summary


@torch.inference_mode()
def _validate(model: nn.Module, loader: DataLoader, criterion: nn.Module,
              device: torch.device) -> dict[str, float]:
    model.eval()
    total_loss, y_true, y_pred = 0.0, [], []
    for images, labels in loader:
        images, labels = images.to(device), labels.to(device)
        logits = model(images)
        total_loss += criterion(logits, labels).item() * labels.size(0)
        y_true.extend(labels.tolist())
        y_pred.extend(logits.argmax(1).tolist())
    n = max(len(y_true), 1)
    return {
        "val_loss": total_loss / n,
        "val_accuracy": sum(t == p for t, p in zip(y_true, y_pred, strict=True)) / n,
        "val_qwk": quadratic_weighted_kappa(y_true, y_pred),
    }

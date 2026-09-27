"""APTOS-style dataset: a CSV of ``id_code,diagnosis`` plus a directory of images."""

from __future__ import annotations

import csv
import random
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import torch
from torch.utils.data import Dataset

from drscreen.grading import NUM_GRADES
from drscreen.preprocessing import SUPPORTED_EXTENSIONS, load_image


@dataclass(frozen=True)
class Sample:
    path: Path
    grade: int


def read_labels(csv_path: str | Path, image_dir: str | Path) -> list[Sample]:
    """Read an APTOS ``train.csv`` and resolve each id to an existing image file."""
    image_dir = Path(image_dir)
    by_stem = {p.stem: p for p in image_dir.iterdir() if p.suffix.lower() in SUPPORTED_EXTENSIONS}
    samples: list[Sample] = []
    missing: list[str] = []
    with open(csv_path, newline="") as fh:
        reader = csv.DictReader(fh)
        if not {"id_code", "diagnosis"} <= set(reader.fieldnames or ()):
            raise ValueError(f"{csv_path} must have 'id_code' and 'diagnosis' columns")
        for row in reader:
            grade = int(row["diagnosis"])
            if not 0 <= grade < NUM_GRADES:
                raise ValueError(f"Invalid diagnosis {grade} for {row['id_code']}")
            path = by_stem.get(row["id_code"])
            if path is None:
                missing.append(row["id_code"])
            else:
                samples.append(Sample(path, grade))
    if missing:
        raise FileNotFoundError(
            f"{len(missing)} images listed in {csv_path} are missing from {image_dir} "
            f"(e.g. {missing[:3]})"
        )
    return samples


def stratified_split(samples: list[Sample], valid_fraction: float, seed: int
                     ) -> tuple[list[Sample], list[Sample]]:
    """Deterministic, class-balanced train/validation split.

    A fixed seed matters: the original notebook reshuffled on every run while resuming
    from earlier checkpoints, so validation images leaked into training and inflated
    the reported accuracy.
    """
    rng = random.Random(seed)
    by_grade: dict[int, list[Sample]] = defaultdict(list)
    for s in samples:
        by_grade[s.grade].append(s)
    train, valid = [], []
    for grade in sorted(by_grade):
        group = sorted(by_grade[grade], key=lambda s: s.path.name)
        rng.shuffle(group)
        n_valid = max(1, round(len(group) * valid_fraction)) if len(group) > 1 else 0
        valid.extend(group[:n_valid])
        train.extend(group[n_valid:])
    return train, valid


def class_weights(samples: list[Sample], power: float = 0.5) -> torch.Tensor:
    """Inverse-frequency class weights, softened by ``power`` (0.5 = inverse sqrt).

    APTOS is heavily skewed towards grade 0; unweighted training under-calls the rare
    severe grades, which is exactly the false-negative failure we must avoid.
    """
    counts = Counter(s.grade for s in samples)
    freq = torch.tensor([counts.get(g, 0) for g in range(NUM_GRADES)], dtype=torch.float32)
    weights = (freq.sum() / freq.clamp(min=1)) ** power
    return weights / weights.mean()


class FundusDataset(Dataset):
    def __init__(self, samples: list[Sample], transform: Callable):
        self.samples = samples
        self.transform = transform

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, index: int) -> tuple[torch.Tensor, int]:
        sample = self.samples[index]
        return self.transform(load_image(sample.path)), sample.grade

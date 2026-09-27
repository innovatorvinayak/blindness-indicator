"""Evaluation metrics, implemented in NumPy to avoid a scikit-learn dependency."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import asdict, dataclass

import numpy as np

from drscreen.grading import NUM_GRADES, Grade


def confusion_matrix(y_true: Sequence[int], y_pred: Sequence[int],
                     num_classes: int = NUM_GRADES) -> np.ndarray:
    matrix = np.zeros((num_classes, num_classes), dtype=np.int64)
    np.add.at(matrix, (np.asarray(y_true), np.asarray(y_pred)), 1)
    return matrix


def quadratic_weighted_kappa(y_true: Sequence[int], y_pred: Sequence[int],
                             num_classes: int = NUM_GRADES) -> float:
    """Cohen's kappa with quadratic weights — the official APTOS 2019 metric.

    Unlike accuracy it penalises a 0-vs-4 mistake far more than a 1-vs-2 one, and it
    is not inflated by the dominant "No DR" class.
    """
    observed = confusion_matrix(y_true, y_pred, num_classes).astype(np.float64)
    n = observed.sum()
    if n == 0:
        return 0.0
    idx = np.arange(num_classes)
    weights = (idx[:, None] - idx[None, :]) ** 2 / (num_classes - 1) ** 2
    expected = np.outer(observed.sum(axis=1), observed.sum(axis=0)) / n
    denominator = (weights * expected).sum()
    return 1.0 if denominator == 0 else float(1 - (weights * observed).sum() / denominator)


@dataclass(frozen=True)
class BinaryMetrics:
    threshold: float
    sensitivity: float  # recall on referable cases: 1 - false-negative rate
    specificity: float
    ppv: float
    npv: float
    false_negatives: int


def referral_metrics(y_true: Sequence[int], referral_probability: Sequence[float],
                     threshold: float) -> BinaryMetrics:
    truth = np.asarray(y_true) >= Grade.MODERATE
    flagged = np.asarray(referral_probability) >= threshold
    tp = int(np.sum(truth & flagged))
    tn = int(np.sum(~truth & ~flagged))
    fp = int(np.sum(~truth & flagged))
    fn = int(np.sum(truth & ~flagged))

    def ratio(a: int, b: int) -> float:
        return a / b if b else float("nan")

    return BinaryMetrics(threshold, ratio(tp, tp + fn), ratio(tn, tn + fp),
                         ratio(tp, tp + fp), ratio(tn, tn + fn), fn)


def classification_report(y_true: Sequence[int], y_pred: Sequence[int],
                          referral_probability: Sequence[float] | None = None,
                          threshold: float = 0.5) -> dict:
    matrix = confusion_matrix(y_true, y_pred)
    support = matrix.sum(axis=1)
    predicted = matrix.sum(axis=0)
    diag = np.diag(matrix)
    per_class = {
        g.label: {
            "precision": float(diag[g] / predicted[g]) if predicted[g] else float("nan"),
            "recall": float(diag[g] / support[g]) if support[g] else float("nan"),
            "support": int(support[g]),
        }
        for g in Grade
    }
    report = {
        "n": int(matrix.sum()),
        "accuracy": float(diag.sum() / max(matrix.sum(), 1)),
        "quadratic_weighted_kappa": quadratic_weighted_kappa(y_true, y_pred),
        "per_class": per_class,
        "confusion_matrix": matrix.tolist(),
    }
    if referral_probability is not None:
        report["referral"] = asdict(referral_metrics(y_true, referral_probability, threshold))
    return report

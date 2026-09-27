from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from drscreen.data import Sample, class_weights, read_labels, stratified_split
from drscreen.metrics import (
    classification_report,
    confusion_matrix,
    quadratic_weighted_kappa,
    referral_metrics,
)


def test_qwk_perfect_and_reversed():
    y = [0, 1, 2, 3, 4] * 4
    assert quadratic_weighted_kappa(y, y) == pytest.approx(1.0)
    assert quadratic_weighted_kappa(y, [4 - v for v in y]) == pytest.approx(-1.0)


def test_qwk_matches_reference_value():
    # Reference: sklearn.metrics.cohen_kappa_score(..., weights="quadratic") == 0.9
    y_true = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
    y_pred = [0, 1, 1, 2, 2, 3, 3, 4, 4, 4]
    assert quadratic_weighted_kappa(y_true, y_pred) == pytest.approx(0.9)


def test_confusion_matrix_counts():
    m = confusion_matrix([0, 0, 4], [0, 1, 4])
    assert m[0, 0] == 1 and m[0, 1] == 1 and m[4, 4] == 1 and m.sum() == 3


def test_referral_metrics_count_false_negatives():
    y_true = [0, 1, 2, 3, 4]
    p_ref = [0.1, 0.6, 0.4, 0.9, 0.9]
    m = referral_metrics(y_true, p_ref, 0.5)
    assert m.false_negatives == 1  # the grade-2 case at p=0.4
    assert m.sensitivity == pytest.approx(2 / 3)
    assert m.specificity == pytest.approx(1 / 2)


def test_classification_report_shape():
    r = classification_report([0, 1, 2], [0, 1, 1], [0.1, 0.2, 0.3])
    assert r["n"] == 3 and r["accuracy"] == pytest.approx(2 / 3)
    assert set(r) >= {"per_class", "confusion_matrix", "referral", "quadratic_weighted_kappa"}


def _samples(counts: dict[int, int]) -> list[Sample]:
    return [Sample(Path(f"{g}_{i}.png"), g) for g, n in counts.items() for i in range(n)]


def test_stratified_split_is_deterministic_and_balanced():
    samples = _samples({0: 50, 1: 10, 2: 20, 3: 5, 4: 5})
    train_a, valid_a = stratified_split(samples, 0.2, seed=1)
    train_b, valid_b = stratified_split(samples, 0.2, seed=1)
    assert valid_a == valid_b and train_a == train_b
    assert not set(train_a) & set(valid_a)
    assert {s.grade for s in valid_a} == {0, 1, 2, 3, 4}
    assert len(valid_a) == 18


def test_class_weights_upweight_rare_grades():
    w = class_weights(_samples({0: 100, 1: 10, 2: 40, 3: 5, 4: 5}))
    assert w[3] > w[1] > w[2] > w[0]


def test_read_labels_resolves_images_and_reports_missing(tmp_path):
    for name in ("a", "b"):
        Image.new("RGB", (4, 4)).save(tmp_path / f"{name}.png")
    csv = tmp_path / "train.csv"
    csv.write_text("id_code,diagnosis\na,0\nb,3\n")
    samples = read_labels(csv, tmp_path)
    assert [(s.path.name, s.grade) for s in samples] == [("a.png", 0), ("b.png", 3)]

    csv.write_text("id_code,diagnosis\na,0\nmissing,1\n")
    with pytest.raises(FileNotFoundError, match="1 images"):
        read_labels(csv, tmp_path)

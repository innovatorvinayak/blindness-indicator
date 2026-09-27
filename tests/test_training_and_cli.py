from __future__ import annotations

import json

import numpy as np
from PIL import Image

from drscreen.cli import main
from drscreen.model import load_checkpoint
from drscreen.training import TrainConfig, train
from tests.conftest import TEST_ARCH


def _make_dataset(root, n_per_grade: int = 4):
    images = root / "train_images"
    images.mkdir()
    rows = ["id_code,diagnosis"]
    rng = np.random.default_rng(0)
    for grade in range(5):
        for i in range(n_per_grade):
            name = f"g{grade}_{i}"
            pixels = rng.integers(0, 255, (48, 48, 3), dtype=np.uint8)
            Image.fromarray(pixels).save(images / f"{name}.png")
            rows.append(f"{name},{grade}")
    csv = root / "train.csv"
    csv.write_text("\n".join(rows) + "\n")
    return csv, images


def test_training_smoke_run_writes_loadable_checkpoint(tmp_path):
    csv, images = _make_dataset(tmp_path)
    out = tmp_path / "trained.pt"
    cfg = TrainConfig(csv=csv, image_dir=images, output=out, arch=TEST_ARCH, image_size=32,
                      epochs=2, batch_size=8, workers=0, device="cpu", pretrained=False)
    summary = train(cfg)

    assert len(summary["history"]) == 2
    _, meta = load_checkpoint(out)
    assert meta.arch == TEST_ARCH and meta.channel_order == "RGB"
    assert {"val_qwk", "val_accuracy", "epoch"} <= set(meta.metrics)
    assert json.loads(out.with_suffix(".history.json").read_text())["history"]


def test_cli_predict_json(checkpoint, fundus_image, capsys, monkeypatch):
    monkeypatch.setenv("DRS_DEVICE", "cpu")
    assert main(["predict", str(fundus_image), "--model", str(checkpoint), "--json"]) == 0
    record = json.loads(capsys.readouterr().out.strip())
    assert record["grade"] in range(5) and "probabilities" in record


def test_cli_evaluate(tmp_path, checkpoint, capsys, monkeypatch):
    monkeypatch.setenv("DRS_DEVICE", "cpu")
    csv, images = _make_dataset(tmp_path, n_per_grade=2)
    report_path = tmp_path / "report.json"
    code = main(["evaluate", "--csv", str(csv), "--images", str(images),
                 "--model", str(checkpoint), "--sweep", "--output", str(report_path)])
    assert code == 0
    report = json.loads(report_path.read_text())
    assert report["n"] == 10 and len(report["sweep"]) == 19
    assert "QWK=" in capsys.readouterr().out


def test_cli_reports_missing_model_cleanly(tmp_path, fundus_image, capsys):
    code = main(["predict", str(fundus_image), "--model", str(tmp_path / "missing.pt")])
    assert code == 1
    assert "Model weights not found" in capsys.readouterr().err

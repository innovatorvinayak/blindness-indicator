# Model card: DR severity classifier

| | |
|---|---|
| **Task** | 5-class Diabetic Retinopathy severity grading from a single colour fundus photograph |
| **Classes** | 0 No DR · 1 Mild · 2 Moderate · 3 Severe · 4 Proliferative DR (International Clinical DR scale) |
| **Architecture** | ResNet-152 (ImageNet-pretrained) with a head of Linear(2048→512) → ReLU → Linear(512→5) |
| **Input** | RGB image resized to 224×224 and normalised with ImageNet statistics |
| **Training data** | APTOS 2019 Blindness Detection (Kaggle): 3,662 labelled images from Aravind Eye Hospital, India |
| **Framework** | PyTorch |

## Intended use

This is a **screening aid** for trained operators at eye camps, primary-care clinics and
NGOs. It helps them triage which patients need an ophthalmologist. It is **not a
diagnostic device**, it is not approved by any regulator, and it must not be the only
basis for a clinical decision.

## Decision rule

The screen shows the arg-max grade. The **referral flag** is set separately, when
`P(grade ≥ Moderate) ≥ DRS_REFERRAL_THRESHOLD` (default 0.5). In screening, a missed
referable case (a false negative) costs far more than an extra referral. So pick the
threshold from `drscreen evaluate --sweep` on local data: choose the highest threshold
that still reaches the sensitivity you need. A widely used benchmark for DR screening is
≥ 80% sensitivity and ≥ 95% specificity (the British Diabetic Association standard).

## About the "97% accuracy" figure

The original project reported 97% accuracy. **That number has not been reproduced here, and it should
not be quoted without re-evaluation.** Three reasons:

1. **Leakage.** The notebook reshuffled the train/validation split without a seed on every
   run, while training resumed from checkpoints of earlier runs. After several restarts,
   most validation images had already been seen in training.
2. **Metric choice.** About 49% of APTOS images are grade 0, so plain accuracy is flattering.
   The competition metric is quadratic weighted kappa (QWK). The best leaderboard
   score was about 0.93 QWK.
3. **Train/serve skew.** Training read images with OpenCV (BGR). The desktop app sent
   RGB. `drscreen` records the channel order in the checkpoint and fixes this.

To get honest numbers, keep a held-out set that was never used in training (or use
external data such as Messidor-2 or IDRiD) and run:

```bash
drscreen evaluate --csv holdout.csv --images holdout/ --sweep --output report.json
```

Report QWK, per-class recall, and the sensitivity/specificity for referable DR.

## Known limitations

- The model was trained on one population (India) and one set of cameras. Performance on
  other cameras, other ethnicities and smartphone fundus photos is unknown.
- It uses one image per eye. It has no macular-oedema output and does not combine both eyes.
- Ungradable images (blurred, dark, not a fundus) are only caught by simple heuristics.
  The model will still output a grade for them.
- The confidence values are softmax probabilities and have not been calibrated.

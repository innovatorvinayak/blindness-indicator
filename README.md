# AI-Based Diabetic Retinopathy Detection and Severity Classification

A desktop screening station that grades retinal fundus photographs for **Diabetic
Retinopathy (DR)** on the 5-point clinical scale. It uses a fine-tuned **ResNet-152**
(PyTorch). Each result is saved to **MySQL**, and the patient can get it by **SMS** (Twilio).

| Grade | Meaning | Suggested action |
|:---:|---|---|
| 0 | No DR | Re-screen in 12 months |
| 1 | Mild DR | Re-screen in 6–12 months |
| 2 | Moderate DR | **Refer**: ophthalmologist within 3 months |
| 3 | Severe DR | **Urgent referral** within 4 weeks |
| 4 | Proliferative DR | **See an ophthalmologist immediately** |

> DR is a leading cause of preventable blindness in working-age adults. Many clinics
> have too few specialists to screen everyone. This project automates the first-pass
> grading so specialists can spend their time on the patients who need them.
> Dataset: [APTOS 2019 Blindness Detection](https://www.kaggle.com/c/aptos2019-blindness-detection).

---

## How it works

```mermaid
flowchart LR
    A[Operator signs in] --> B[Enter patient details<br/>+ choose fundus image]
    B --> C[Preprocess<br/>resize 224², normalise]
    C --> D[ResNet-152<br/>+ flip TTA]
    D --> E[Grade 0–4 + probabilities<br/>+ referral decision]
    E --> F[(MySQL / SQLite<br/>patients, screenings)]
    E --> G[GUI result card]
    E -->|optional| H[Twilio SMS<br/>to patient]
```

1. **Upload.** The operator enters the patient's name, mobile number, age and sex, then picks a fundus image.
2. **Preprocess.** The image is converted to RGB (transparency is flattened onto black), resized, and normalised exactly as it was during training.
3. **Analyse.** ResNet-152 scores the image and its mirror image, and the two scores are averaged (test-time augmentation, TTA).
4. **Predict.** The app outputs a severity grade, the probability for each class, and a *referral* flag based on P(grade ≥ Moderate).
5. **Display.** The result card shows the grade (colour-coded), probability bars, advice and image-quality warnings.
6. **Store.** The patient record, the result, the model version and an archived copy of the image are saved to the database.
7. **Notify.** If requested, the patient gets a short SMS report.

## Features

- **Detection and severity grading** (0–4) with per-class probability bars and a referral
  flag you can tune, which lets you lower false negatives (Type-II errors).
- **Single-image and batch testing** from the CLI, including the bundled `sampleimages/`.
- **Reproducible training**: a fixed stratified split, class-weighted loss, a mixed-precision
  one-cycle schedule, model selection on **QWK** (the APTOS metric), and early stopping.
- **Evaluation**: accuracy, QWK, per-class precision/recall, confusion matrix, and
  sensitivity/specificity for referable DR across thresholds.
- **Desktop GUI** (Tkinter, on top of [CustomTkinter](https://github.com/TomSchimansky/CustomTkinter)
  for scrolling and [Pillow](https://python-pillow.org/) for imaging — everything else
  hand-built): a branded "Emerald & Ivory" glassmorphic interface — a custom rendered logo,
  a living animated landing/login screen, and a screening dashboard whose bars, image
  preview, and buttons genuinely rescale with the window. Scrolling (trackpad, mouse wheel,
  or the scrollbar) is handled by CustomTkinter rather than a hand-rolled mechanism, since
  its mousewheel handling has been battle-tested across real macOS/Windows/Linux use far
  more than anything written from scratch for this project could be. Runs on a worker
  thread so it never freezes during inference.
- **Full detailed reports, viewed in the app**: every screening gets a complete report —
  patient details, the fundus image, grade, full probability breakdown, referral
  recommendation, this patient's screening history/trend, model provenance — rendered
  natively (double-click any history row, or "View full report"; works instantly, no
  model load needed). A one-click "Export as HTML" still produces a portable,
  printable/emailable file for anyone who needs one.
- **Recent Screenings is its own page**, one click from the dashboard header (or
  `Ctrl/Cmd+F`) — search, "referrals only" filter, CSV export, and double-click-to-report
  all live there, so the main screening workflow never depends on scrolling past a table.
- **MySQL storage** (HeidiSQL-compatible) with SQLite as a zero-setup fallback.
- **SMS reports** via Twilio (free trial credit, card required at signup) or **Fast2SMS**
  (India — cheaper, but *not* free: their API refuses every request, even the first, until
  the account has a minimum ₹100 top-up). Without either configured, SMS runs in dry-run
  mode (printed to the log, nothing lost).
- **In-app Settings**: change clinic name, referral threshold, default country code and
  the SMS on/off switch without hand-editing `.env` — takes effect immediately.
- **CSV export** (GUI button or `drscreen export-csv`) and **batch screening**
  (`drscreen batch-screen`) for running a whole eye camp's folder of images against a
  patient CSV in one pass.
- **Image-quality feedback the moment you pick a photo** (blur/exposure/resolution), not
  only after you've already waited for a prediction.
- **Keyboard shortcuts**: `Ctrl/Cmd+O` choose image, `Ctrl/Cmd+Return` analyze,
  `Ctrl/Cmd+R` view report, `Ctrl/Cmd+F` recent screenings, `Ctrl/Cmd+E` export, `Esc` back.
- A referable result rings the system bell and pulses the banner — hard to miss even if
  you looked away from the screen.

## Quick start

The fastest path on any OS — one script handles the venv, dependencies, and `.env`:

```bash
./deploy.sh              # set up, then launch the desktop GUI
./deploy.sh doctor       # set up, then run any drscreen command instead
./deploy.sh setup        # just set up; don't run anything
```

`deploy.sh` is a Bash script, so it runs natively on **macOS** and **Linux**, and on
**Windows** via **Git Bash** (ships with [Git for Windows](https://git-scm.com/download/win))
or **WSL** — a `.sh` file can't be double-clicked or run from `cmd.exe`/PowerShell directly,
which is a Windows limitation no script content can work around. It detects the OS, finds a
Python 3.10+ interpreter, creates `.venv` (recovering gracefully if pip wasn't bundled — e.g.
a venv created by `uv`), installs the project, and copies `.env.example` → `.env` on first run.

Or by hand:

```bash
# 1. Install (Python 3.10+)
python -m venv .venv && source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[all]"

# 2. Configure
cp .env.example .env                                     # then edit as needed

# 3. Get model weights (see models/README.md)
drscreen convert-weights ~/Downloads/classifier.pt models/classifier.pt --trust

# 4. Check everything is wired up
drscreen doctor

# 5. Run
drscreen gui                                             # desktop app
drscreen predict sampleimages/                           # grade all sample images
drscreen predict sampleimages/eye1.png --json            # one image, machine-readable
```

Example output of `drscreen predict` (illustrative values):

```
eye1.png                     REFER  grade 2  Moderate DR               87.3%
eye4.jpg                            grade 0  No Diabetic Retinopathy   96.1%
```

## Command reference

| Command | Purpose |
|---|---|
| `drscreen gui` | Launch the desktop screening app |
| `drscreen predict IMG/DIR… [--json] [--no-tta]` | Grade one or more images or folders |
| `drscreen train --csv train.csv --images train_images/` | Fine-tune on APTOS (see `--help` for hyper-parameters) |
| `drscreen evaluate --csv … --images … [--sweep]` | Metrics on a labelled set, with an optional threshold sweep |
| `drscreen add-user USERNAME` | Create an operator account (password prompt) |
| `drscreen history [-n 20]` | Recent screenings |
| `drscreen sms-test +91XXXXXXXXXX` | Send a test SMS |
| `drscreen report ID [--open]` | Generate the full detailed report for a screening |
| `drscreen batch-screen --csv … --images DIR [--send-sms]` | Screen a whole eye-camp folder in one pass |
| `drscreen export-csv --output FILE` | Export screening history as CSV |
| `drscreen init-db` | Create database tables |
| `drscreen convert-weights SRC DST --trust` | Convert the legacy `classifier.pt` to the safe format |
| `drscreen doctor` | Check model, database and SMS configuration |

## Configuration

All settings come from environment variables or `.env`. See [.env.example](.env.example).

### MySQL (HeidiSQL)

Run [sql/schema.mysql.sql](sql/schema.mysql.sql) as an admin user. In HeidiSQL, use
*File → Load SQL file…* and then *Execute*. From a terminal, use
`mysql -u root -p < sql/schema.mysql.sql`. Then create a least-privilege app account:

```sql
CREATE USER 'drscreen'@'localhost' IDENTIFIED BY 'change-me';
GRANT SELECT, INSERT, UPDATE ON drscreen.* TO 'drscreen'@'localhost';
```

```ini
DRS_DATABASE_URL=mysql+pymysql://drscreen:change-me@localhost:3306/drscreen?charset=utf8mb4
```

Leave `DRS_DATABASE_URL` unset to use a local SQLite file (`data/drscreen.db`).

### SMS

`build_sender()` picks the first of these that's configured: **Twilio**, then
**Fast2SMS**, then dry-run (prints the message instead of sending). Both can also be
set from the app's Settings screen (clinic name, threshold, country code, on/off) —
API credentials still go in `.env`.

Neither provider is actually free — a real SMS costs a telecom operator money to
deliver, and every provider gates that behind *some* form of payment to stop the free
tier being abused for spam. Pick whichever friction you'd rather deal with:

**Twilio** (any country) — no charge unless you exceed the free trial credit, but a
card must be on file to activate the account at all:
1. Create a Twilio account and get a phone number (or a Messaging Service).
2. Put `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN` and `TWILIO_FROM_NUMBER` in `.env`.
3. **Trial accounts can only text verified numbers.** Add each recipient under
   *Phone Numbers → Verified Caller IDs* first.

**Fast2SMS** (India) — cheaper per message, no card needed to sign up, but its API
returns an error on every request — even the very first — until the account has a
minimum ₹100 (~$1.20) wallet top-up; after that, ₹100 covers hundreds of messages:
1. Sign up at [fast2sms.com](https://www.fast2sms.com) and copy your API key from the
   dashboard.
2. Add ₹100+ to the wallet (UPI/card, in their dashboard) — the API will reject every
   send with `"You need to complete one transaction of 100 INR or more..."` until you do.
3. Put the key in `.env` as `FAST2SMS_API_KEY`. The default route (`FAST2SMS_ROUTE=q`,
   "Quick SMS") needs no DLT template approval.
4. Only Twilio unconfigured lets Fast2SMS take over automatically; leave `TWILIO_*` blank
   to use it.

Either way, run `drscreen sms-test 98XXXXXXXX` to check it — bare 10-digit numbers get
`DRS_DEFAULT_COUNTRY_CODE` (+91) added in front.

Example message (illustrative):

```
DR Screening Centre: Eye screening report
Dear Asha, result: Moderate DR (Grade 2/4, 87% confidence).
Referable DR. Consult an ophthalmologist within 3 months.
AI-assisted screening, not a diagnosis.
```

## Training

```bash
drscreen train \
  --csv aptos2019/train.csv --images aptos2019/train_images \
  --epochs 30 --batch-size 32 --output models/classifier_v2.pt
```

| Choice | Why |
|---|---|
| Freeze `conv1`+`layer1`, fine-tune `layer2–4`+head | Low-level filters transfer well; fewer parameters on a 3.6k-image dataset |
| Stratified split, fixed seed | No validation leakage between runs; every grade is in validation |
| Inverse-√frequency class weights + label smoothing | APTOS is ~49% grade 0, and rare severe grades must not be ignored |
| Rotation/flip/colour augmentation | The fundus has no canonical orientation; cameras vary in exposure |
| Select on validation **QWK** | The official metric; it punishes 0↔4 errors more than 1↔2 errors |
| AdamW + OneCycle, AMP, grad clipping | Faster, more stable convergence |

The best checkpoint is written with its metrics and version embedded. A `*.history.json`
file next to it records every epoch.

## Model performance and limitations

See **[docs/MODEL_CARD.md](docs/MODEL_CARD.md)**. It includes an analysis of why the
original "97% accuracy" claim can't be trusted as-is (a validation-leakage problem and a
BGR/RGB mismatch between training and serving), and how to measure performance
properly. **This software is a screening aid, not a diagnostic device.**

## Engineering notes: what changed from v1

| Area | v1 | v2 |
|---|---|---|
| Inference | `RandomHorizontalFlip` at test time made results random | Deterministic transform + optional flip-TTA average |
| Train/serve | Trained on BGR (OpenCV), served RGB (PIL) | Channel order stored in the checkpoint and applied automatically |
| Login | Any username + *any user's* password logged in; failed logins still unlocked upload | Per-user scrypt password hashes; constant-time comparison |
| SQL | String-formatted queries (SQL injection) | SQLAlchemy parameterised queries, UNIQUE constraints, short transactions |
| Secrets | DB password hard-coded in source | `.env` / environment variables |
| Checkpoints | Full pickled module (arbitrary-code risk) | `weights_only` loading; explicit `convert-weights --trust` for old files |
| GUI | Froze during inference; opened a blocking matplotlib window | Background worker thread, integrated result card and history |
| Validation | Unseeded split, reshuffled on every resume | Seeded stratified split, QWK, referral sensitivity |
| Packaging | Pinned, mutually incompatible versions (`torchvision==0.3` with `torch==1.13`) | `pyproject.toml`, installable CLI, CUDA/MPS/CPU auto-select |
| Tests | None | 43 pytest tests covering model I/O, inference, metrics, training, DB, auth, SMS and CLI |

## Project layout

```
src/drscreen/
  grading.py        severity scale, advice, colours
  preprocessing.py  image loading, quality checks, train/eval transforms
  model.py          ResNet builder, safe checkpoint I/O, legacy conversion
  inference.py      Predictor (thread-safe, TTA, referral decision)
  data.py           APTOS dataset, stratified split, class weights
  training.py       training loop
  metrics.py        QWK, confusion matrix, referral sensitivity/specificity
  storage.py        SQLAlchemy models + repository (MySQL / SQLite)
  security.py       password hashing
  notify.py         Twilio SMS + dry-run sender, phone normalisation
  reporting.py      self-contained HTML clinical report generator
  service.py        screening workflow shared by GUI and CLI
  cli.py            `drscreen` command
  gui/
    theme.py          "Emerald & Ivory" palette, derived from 2 brand colours
    branding.py       the rendered logo (window icon, report header)
    canvas_widgets.py responsive/animated widgets (buttons, bars, scroll, background)
    app.py            the Tkinter application (landing/login, dashboard, native
                      report view, settings view)
tests/              pytest suite (run: pytest)
notebooks/          original Kaggle training/inference notebooks
legacy/             original v1 scripts, kept for reference
sql/                MySQL schema
docs/MODEL_CARD.md  intended use, metrics, limitations
```

## Development

```bash
pip install -e ".[all]"
pytest            # full suite, about 15 s on CPU (uses a small ResNet-18 for speed)
ruff check src tests
```

## Roadmap

- Web deployment (FastAPI + the same `ScreeningService`) with a lightweight backbone
  (EfficientNet-B0 / MobileNetV3) or ONNX export for CPU clinics.
- Grad-CAM heat-maps so clinicians can see which lesions drove a prediction.
- A proper ungradable-image detector, and probability calibration (temperature scaling).
- Privacy-preserving training across hospitals: Federated Learning, Differential
  Privacy, Secure Multi-Party Computation.
- External validation on Messidor-2 / IDRiD.

## Credits

Based on the original project by [@souravs17031999](https://github.com/souravs17031999/Retinal_blindness_detection_Pytorch),
inspired by Aravind Eye Hospital and the Asia Pacific Tele-Ophthalmology Society (APTOS).

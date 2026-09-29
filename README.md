# AI-Based Diabetic Retinopathy Detection and Severity Classification

A web-based screening application that grades retinal fundus photographs for **Diabetic
Retinopathy (DR)** on the 5-point clinical scale. It uses a fine-tuned **ResNet-152**
(PyTorch). Each result is saved to **MySQL** (or SQLite/Postgres), the patient can get it
by **SMS** (Twilio/Fast2SMS), and an operator can ask a local **AI chat assistant**
(Ollama) to explain any result in plain language.

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
    A[Operator signs in<br/>web browser] --> B[Enter patient details<br/>+ choose fundus image]
    B --> C[Preprocess<br/>resize 224², normalise]
    C --> D[ResNet-152<br/>+ flip TTA]
    D --> E[Grade 0–4 + probabilities<br/>+ referral decision]
    E --> F[(MySQL / SQLite / Postgres<br/>patients, screenings)]
    E --> G[Result panel + report]
    E -->|optional| H[Twilio / Fast2SMS<br/>to patient]
    E -->|optional| I[Ollama chat<br/>explains the result]
```

1. **Upload.** The operator enters the patient's name, mobile number, age and sex, then picks a fundus image in the browser.
2. **Preprocess.** The image is converted to RGB (transparency is flattened onto black), resized, and normalised exactly as it was during training.
3. **Analyse.** ResNet-152 scores the image and its mirror image, and the two scores are averaged (test-time augmentation, TTA).
4. **Predict.** The app returns a severity grade, the probability for each class, and a *referral* flag based on P(grade ≥ Moderate).
5. **Display.** The result panel shows the grade (colour-coded), animated probability bars, advice and image-quality warnings — no page reload.
6. **Store.** The patient record, the result, the model version and an archived copy of the image are saved to the database.
7. **Notify.** If requested, the patient gets a short SMS report.
8. **Explain (optional).** The operator can ask a chat assistant questions about *this* result — it's scoped to the screening at hand, not general medical advice.

## Features

- **Detection and severity grading** (0–4) with animated per-class probability bars and a
  referral flag you can tune, which lets you lower false negatives (Type-II errors).
- **Single-image and batch testing** from the CLI, including the bundled `sampleimages/`.
- **Reproducible training**: a fixed stratified split, class-weighted loss, a mixed-precision
  one-cycle schedule, model selection on **QWK** (the APTOS metric), and early stopping.
- **Evaluation**: accuracy, QWK, per-class precision/recall, confusion matrix, and
  sensitivity/specificity for referable DR across thresholds.
- **Next.js web UI** (React 19, TypeScript, Tailwind v4): a "Deep Field" interface —
  near-black void, electric cyan and violet, real `backdrop-filter` glass, and an
  aperture-and-iris mark drawn as SVG. A landing page with operator sign-in, a screening
  workspace whose result panel updates in place (radial confidence gauge, animated
  probability bars), a records table, and a report view. Runs anywhere a browser does —
  no desktop toolkit, no per-machine Tcl/Tk or GUI dependencies to go wrong.
- **FastAPI JSON backend** with session-cookie auth over the same scrypt password
  hashes. The UI proxies `/api/*` to it, so the cookie stays same-origin and there's no
  CORS setup or token storage to get wrong.
- **AI chat assistant** (optional, via [Ollama](https://ollama.com)): ask questions about
  a specific screening result in plain language. Deliberately scoped — the system prompt
  fixes the actual grade/advice from the prediction and instructs the model never to
  contradict the referral recommendation or answer unrelated medical questions. Runs
  entirely on infrastructure you control (no data leaves your Ollama instance); if it
  isn't running, the chat widget just doesn't appear — nothing else is affected.
- **Full detailed reports, viewed in the browser**: every screening gets a complete
  report — patient details, the fundus image, grade, full probability breakdown, referral
  recommendation, this patient's screening history/trend, model provenance. A one-click
  "Export as HTML" produces a portable, printable/emailable file for anyone who needs one.
- **Recent Screenings** page — search, "referrals only" filter, CSV export, and
  click-to-report, separate from the main screening workflow.
- **MySQL or Postgres storage** with SQLite as a zero-setup fallback.
- **SMS reports** via Twilio (free trial credit, card required at signup) or **Fast2SMS**
  (India — cheaper, but *not* free: their API refuses every request, even the first, until
  the account has a minimum ₹100 top-up). Without either configured, SMS runs in dry-run
  mode (printed to the log, nothing lost).
- **In-app Settings**: change clinic name, referral threshold, default country code, SMS
  on/off, and the chat assistant's model/host — without hand-editing `.env`, takes effect
  immediately (model/database changes still need a restart).
- **CSV export** and **batch screening** (`drscreen batch-screen`) for running a whole eye
  camp's folder of images against a patient CSV in one pass.
- **Image-quality feedback the moment you pick a photo** (blur/exposure/resolution), not
  only after you've already waited for a prediction.
- **Ships as a Compose stack** (UI + API + Ollama), portable to any Docker-capable host —
  Render, Railway, Fly.io, a plain VPS, or your own server.

## Architecture

```
                       ┌─────────────── drscreen web (:8000) ───────────────┐
  browser  ──────────▶ │  frontend/out   static Next.js UI                  │
                       │  /api/*         FastAPI JSON API                   │
                       └───────────────────────┬───────────────────────────┘
                                               ├─▶ ResNet-152 (PyTorch)
                                               ├─▶ SQLite / MySQL / Postgres
                                               ├─▶ Twilio / Fast2SMS
                                               └─▶ Ollama (chat assistant)
```

The UI is a **static export** that FastAPI serves itself, so the whole app is one
process on one port and Node is needed only to *build* the UI, never to run it. UI and
API therefore share an origin, which keeps the httpOnly session cookie working with no
CORS configuration. The same `ScreeningService` powers the API and every CLI command, so
there is no duplicated business logic.

## Quick start

### Option A — Docker Compose (recommended for a real/cloud deployment)

```bash
cp .env.example .env               # clinic name, SMS credentials, DRS_SECRET_KEY
docker compose up -d --build       # first boot also pulls the Ollama chat model
open http://localhost:8000
```

Put your own reverse proxy (Caddy, nginx, or your host's built-in one) with a real TLS
certificate in front of the `app` service for a public domain — see
[docker-compose.yml](docker-compose.yml); it's deliberately not tied to one hosting
provider. You'll still need model weights — see [models/README.md](models/README.md) —
mounted at `./models/classifier.pt`.

### Option B — one command, one port

```bash
./deploy.sh              # sets up Python + builds the UI, then serves both on :8000
```

Open <http://127.0.0.1:8000>. The first run builds the UI (needs Node 20+ once); after
that `frontend/out` is reused and startup is instant. Without Node the API still runs —
you just get the CLI rather than the interface.

### Option C — UI development with hot reload

```bash
drscreen web                                   # API on :8000
cd frontend && npm install && npm run dev      # UI on :3000, proxies /api to :8000
```

Point the proxy elsewhere with `DRS_API_ORIGIN=http://host:port npm run dev`. When
you're done, `npm run build` refreshes the static export that `drscreen web` serves.

### Option D — Windows / setup scripts

**macOS / Linux** (or Windows via Git Bash / WSL):

```bash
./deploy.sh              # set up, then launch the web app at http://127.0.0.1:8000
./deploy.sh doctor       # set up, then run any drscreen command instead
./deploy.sh setup        # just set up; don't run anything
```

`deploy.sh` is a Bash script — a `.sh` file can't be double-clicked or run from
`cmd.exe`/PowerShell directly, which is a Windows limitation no script content can work
around. On Windows it needs **Git Bash** (ships with
[Git for Windows](https://git-scm.com/download/win)) or **WSL**; run it from one of those
shells, not from PowerShell.

**Windows (native PowerShell)** — no Git Bash or WSL required:

```powershell
.\deploy.ps1              # set up, then launch the web app at http://127.0.0.1:8000
.\deploy.ps1 doctor       # set up, then run any drscreen command instead
.\deploy.ps1 setup        # just set up; don't run anything
```

If PowerShell refuses to run it ("running scripts is disabled on this system"), run once:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, confirm, then re-run `.\deploy.ps1`.
If it still refuses after a fresh download with "is not digitally signed", run
`Unblock-File .\deploy.ps1` first — Windows tags browser/ZIP downloads with a marker that
`RemoteSigned` treats as untrusted until it's removed.

Either script finds a Python 3.10+ interpreter, creates `.venv` (recovering gracefully if pip
wasn't bundled — e.g. a venv created by `uv`), installs the project, and copies
`.env.example` → `.env` on first run.

### Option E — by hand

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
drscreen web                                             # UI + API at http://127.0.0.1:8000
drscreen predict sampleimages/                           # grade all sample images
drscreen predict sampleimages/eye1.png --json             # one image, machine-readable
```

Example output of `drscreen predict` (illustrative values):

```
eye1.png                     REFER  grade 2  Moderate DR               87.3%
eye4.jpg                            grade 0  No Diabetic Retinopathy   96.1%
```

### Chat assistant setup (optional)

The chat feature needs a separate [Ollama](https://ollama.com) process:

```bash
# native install: https://ollama.com/download, or `brew install ollama` on macOS
ollama serve                     # in its own terminal, or as a system service
ollama pull llama3.2:3b          # the default model (docker-compose.yml does this for you)
```

If Ollama isn't reachable, the chat widget simply doesn't appear — no error surfaces
elsewhere in the app. Check reachability any time with `drscreen doctor`.

## Command reference

| Command | Purpose |
|---|---|
| `drscreen web [--host] [--port] [--reload]` | Launch the web application |
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
| `drscreen doctor` | Check model, database, SMS and chat-assistant configuration |

## Configuration

All settings come from environment variables or `.env`. See [.env.example](.env.example).

### Database: MySQL, Postgres, or SQLite

For MySQL (HeidiSQL-compatible), run [sql/schema.mysql.sql](sql/schema.mysql.sql) as an
admin user. In HeidiSQL, use *File → Load SQL file…* and then *Execute*. From a terminal,
use `mysql -u root -p < sql/schema.mysql.sql`. Then create a least-privilege app account:

```sql
CREATE USER 'drscreen'@'localhost' IDENTIFIED BY 'change-me';
GRANT SELECT, INSERT, UPDATE ON drscreen.* TO 'drscreen'@'localhost';
```

```ini
DRS_DATABASE_URL=mysql+pymysql://drscreen:change-me@localhost:3306/drscreen?charset=utf8mb4
```

For Postgres (install the extra with `pip install -e ".[postgres]"`):

```ini
DRS_DATABASE_URL=postgresql+psycopg://drscreen:change-me@localhost:5432/drscreen
```

Leave `DRS_DATABASE_URL` unset to use a local SQLite file (`data/drscreen.db`) — fine for
a single-machine deployment, not recommended for several concurrent operators sharing one
cloud instance.

### SMS

`build_sender()` picks the first of these that's configured: **Twilio**, then
**Fast2SMS**, then dry-run (prints the message instead of sending). Both can also be
set from the app's Settings page (clinic name, threshold, country code, on/off) —
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

### Chat assistant (Ollama)

`OLLAMA_HOST` (default `http://localhost:11434`) and `OLLAMA_MODEL` (default
`llama3.2:3b`) — see [drscreen/chat.py](src/drscreen/chat.py) for the exact system prompt
and guardrails. Any Ollama-compatible model works; a smaller model (e.g. `phi3:mini`)
trades explanation quality for lower CPU/memory use on a cheap cloud instance.

### Who can create an account

Operators can register themselves from the sign-in page by default, which is
convenient for a single clinic. An operator account can read **every** patient
record, so for anything reachable from the internet, gate it:

```ini
DRS_ALLOW_SIGNUP=true
DRS_SIGNUP_CODE=CLINIC-2026     # staff must know this code to register
```

or close it entirely and create accounts from the server:

```ini
DRS_ALLOW_SIGNUP=false
```
```bash
drscreen add-user asha
```

### Web app session security

`DRS_SECRET_KEY` signs session cookies. Auto-generated if left blank (fine for local use
— every restart forces re-login); set it explicitly for any real deployment:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
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
properly. **This software is a screening aid, not a diagnostic device.** The chat
assistant is an explanation aid on top of that same screening result — not a second
opinion, and it's explicitly instructed never to contradict the referral recommendation.

## Engineering notes: what changed from v1

| Area | v1 | v2 |
|---|---|---|
| Inference | `RandomHorizontalFlip` at test time made results random | Deterministic transform + optional flip-TTA average |
| Train/serve | Trained on BGR (OpenCV), served RGB (PIL) | Channel order stored in the checkpoint and applied automatically |
| Login | Any username + *any user's* password logged in; failed logins still unlocked upload | Per-user scrypt password hashes; constant-time comparison |
| SQL | String-formatted queries (SQL injection) | SQLAlchemy parameterised queries, UNIQUE constraints, short transactions |
| Secrets | DB password hard-coded in source | `.env` / environment variables |
| Checkpoints | Full pickled module (arbitrary-code risk) | `weights_only` loading; explicit `convert-weights --trust` for old files |
| Interface | Desktop Tkinter GUI, froze during inference | Next.js UI + FastAPI JSON API, deployable to the cloud |
| Validation | Unseeded split, reshuffled on every resume | Seeded stratified split, QWK, referral sensitivity |
| Packaging | Pinned, mutually incompatible versions (`torchvision==0.3` with `torch==1.13`) | `pyproject.toml`, installable CLI, CUDA/MPS/CPU auto-select, Docker image |
| Tests | None | 73 pytest tests covering model I/O, inference, metrics, training, DB, auth, SMS, reporting and CLI |

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
  storage.py        SQLAlchemy models + repository (MySQL / Postgres / SQLite)
  security.py       password hashing
  notify.py         Twilio/Fast2SMS SMS senders + dry-run, phone normalisation
  reporting.py      self-contained HTML clinical report generator
  chat.py           scoped Ollama chat assistant (explains one result)
  service.py        screening workflow shared by the web app and CLI
  theme.py          "Emerald & Ivory" palette, derived from 2 brand colours
  branding.py       the rendered logo (favicon, report header)
  cli.py            `drscreen` command
  theme.py          brand tokens for Python-rendered output (logo, report)
  branding.py       the DRSCREEN mark, rendered with PIL
  web/
    app.py            FastAPI application factory
    auth.py           signed-cookie session auth
    routes/api.py     the whole JSON API
frontend/           Next.js UI (React 19, TypeScript, Tailwind v4)
  out/                static export, served by FastAPI (git-ignored; npm run build)
  src/app/            landing+login, dashboard, history, report, settings
  src/components/     Logo, AppShell, Chat, ui primitives
  src/lib/api.ts      typed client for the JSON API
tests/              pytest suite (run: pytest)
notebooks/          original Kaggle training/inference notebooks
legacy/             original v1 scripts, kept for reference
sql/                MySQL schema
docs/MODEL_CARD.md  intended use, metrics, limitations
Dockerfile, docker-compose.yml   app + Ollama, portable to any Docker host
```

## Development

```bash
# backend
pip install -e ".[all]"
pytest                       # full suite, ~15 s on CPU (uses a small ResNet-18)
ruff check src tests

# frontend
cd frontend
npm install
npm run dev                  # http://localhost:3000, proxies /api to :8000
npm run lint && npx tsc --noEmit
```

## Roadmap

- Grad-CAM heat-maps so clinicians can see which lesions drove a prediction.
- A proper ungradable-image detector, and probability calibration (temperature scaling).
- A lighter backbone (EfficientNet-B0 / MobileNetV3) or ONNX export for CPU-only clinics.
- Privacy-preserving training across hospitals: Federated Learning, Differential
  Privacy, Secure Multi-Party Computation.
- External validation on Messidor-2 / IDRiD.

## Credits

Based on the original project by [@souravs17031999](https://github.com/souravs17031999/Retinal_blindness_detection_Pytorch),
inspired by Aravind Eye Hospital and the Asia Pacific Tele-Ophthalmology Society (APTOS).

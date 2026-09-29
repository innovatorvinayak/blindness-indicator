# One image: the Next.js UI is built to static files, then FastAPI serves
# both it and the JSON API on port 8000. No Node in the final image.
# Portable to any Docker-capable host (Render, Railway, Fly.io, a VPS, ...).

# ── stage 1: build the UI ──────────────────────────────────────────────
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build          # -> /ui/out (static export)

# ── stage 2: the app ───────────────────────────────────────────────────
FROM python:3.12-slim

WORKDIR /app

# CPU-only PyTorch: the default PyPI wheel pulls in CUDA libraries (several
# GB) that a CPU-only cloud instance never uses. Installing it from PyTorch's
# own CPU index first means the extras below reuse it as already-satisfied.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir -e ".[mysql,postgres,sms]"

COPY .env.example ./.env.example
COPY --from=ui /ui/out ./frontend/out

ENV DRS_DATABASE_URL=sqlite:////app/data/drscreen.db \
    DRS_IMAGE_STORE=/app/data/images \
    DRS_REPORT_DIR=/app/data/reports \
    DRS_MODEL_PATH=/app/models/classifier.pt

RUN mkdir -p /app/data /app/models

EXPOSE 8000
CMD ["drscreen", "web", "--host", "0.0.0.0", "--port", "8000"]

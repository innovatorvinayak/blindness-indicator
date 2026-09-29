#!/usr/bin/env bash
# drscreen deploy/run script — one file for macOS, Linux, and Windows.
#
# A .sh file cannot be double-clicked or run by cmd.exe/PowerShell directly —
# that's an OS-level fact no script content can work around. What this file
# does instead: run it from any shell that has bash, which covers all three
# platforms in practice —
#   macOS / Linux : native Terminal (bash or zsh both invoke it fine)
#   Windows       : Git Bash (ships with Git for Windows) or WSL
# and it detects which of those it's on and adjusts venv paths, the Python
# command name, and line-ending/path quirks accordingly.
#
# Usage:
#   ./deploy.sh                 # set up the environment, then launch the web app
#   ./deploy.sh setup           # only set up the environment, don't run anything
#   ./deploy.sh doctor          # set up, then run `drscreen doctor`
#   ./deploy.sh predict img.png # set up, then forward args to `drscreen`
#   ./deploy.sh --skip-setup web  # skip the setup check (fast path, once installed)
#
# Anything after the recognised flags is forwarded verbatim to `drscreen`,
# so every CLI command documented in README.md works through this script too.

set -euo pipefail

# -- output helpers -----------------------------------------------------------------
if [ -t 1 ]; then
  C_RESET=$'\033[0m'; C_BOLD=$'\033[1m'; C_GREEN=$'\033[32m'
  C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'; C_BLUE=$'\033[34m'
else
  C_RESET=""; C_BOLD=""; C_GREEN=""; C_YELLOW=""; C_RED=""; C_BLUE=""
fi
info()  { printf '%s[deploy]%s %s\n' "$C_BLUE" "$C_RESET" "$1"; }
ok()    { printf '%s[deploy]%s %s%s%s\n' "$C_GREEN" "$C_RESET" "$C_GREEN" "$1" "$C_RESET"; }
warn()  { printf '%s[deploy]%s %s%s%s\n' "$C_YELLOW" "$C_RESET" "$C_YELLOW" "$1" "$C_RESET"; }
fail()  { printf '%s[deploy]%s %s%s%s\n' "$C_RED" "$C_RESET" "$C_RED" "$1" "$C_RESET" >&2; exit 1; }

# -- resolve paths relative to this script, not the caller's cwd --------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# -- OS detection ---------------------------------------------------------------------
# uname -s reports Darwin/Linux natively; Git Bash / MSYS report
# MINGW64_NT-*, MSYS_NT-*, or CYGWIN_NT-* depending on the exact environment.
UNAME_S="$(uname -s 2>/dev/null || echo unknown)"
case "$UNAME_S" in
  Darwin*)                    PLATFORM="macos" ;;
  Linux*)                     PLATFORM="linux" ;;
  MINGW*|MSYS*|CYGWIN*)       PLATFORM="windows" ;;
  *)                          PLATFORM="unknown" ;;
esac
info "Detected platform: $C_BOLD$PLATFORM$C_RESET (uname -s: $UNAME_S)"

if [ "$PLATFORM" = "unknown" ]; then
  warn "Couldn't identify the OS from 'uname -s'; proceeding with generic" \
       "Unix-style paths. If this is Windows, run this script from Git Bash or WSL."
fi

# -- find a usable Python (3.10+) ------------------------------------------------------
find_python() {
  for candidate in python3.13 python3.12 python3.11 python3.10 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
      # Reject Python < 3.10 (the project's declared minimum) and Python 2,
      # which on some systems is still what a bare `python` resolves to.
      if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' \
        >/dev/null 2>&1; then
        echo "$candidate"
        return 0
      fi
    fi
  done
  return 1
}

PYTHON="$(find_python || true)"
if [ -z "${PYTHON:-}" ]; then
  fail "No Python 3.10+ found on PATH. Install it from https://python.org/downloads " \
       "(Windows: check \"Add python.exe to PATH\" during install), then re-run this script."
fi
info "Using Python: $C_BOLD$PYTHON$C_RESET ($($PYTHON --version 2>&1))"

# -- create / locate the virtualenv ----------------------------------------------------
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
  info "Creating virtual environment at .venv ..."
  "$PYTHON" -m venv "$VENV_DIR" \
    || fail "Failed to create the virtual environment. On Debian/Ubuntu you may need:" \
            "  sudo apt install python3-venv"
fi

# The venv's internal layout depends on which Python built it, not on which
# shell is running this script (a WSL Python venv looks like Linux even
# though the host OS is Windows) — so detect it directly instead of trusting
# $PLATFORM.
if [ -f "$VENV_DIR/bin/activate" ]; then
  VENV_BIN="$VENV_DIR/bin"
  ACTIVATE="$VENV_DIR/bin/activate"
elif [ -f "$VENV_DIR/Scripts/activate" ]; then
  VENV_BIN="$VENV_DIR/Scripts"
  ACTIVATE="$VENV_DIR/Scripts/activate"
else
  fail "Could not find an activate script under .venv/bin or .venv/Scripts." \
       "Delete the .venv folder and re-run this script to recreate it."
fi

# shellcheck disable=SC1090
source "$ACTIVATE"
info "Virtual environment active: $VENV_DIR"

# -- parse our own flags, forward the rest to `drscreen` -------------------------------
SKIP_SETUP=0
ARGS=()
for arg in "$@"; do
  case "$arg" in
    --skip-setup) SKIP_SETUP=1 ;;
    -h|--help)
      sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *) ARGS+=("$arg") ;;
  esac
done

# -- install / update the project and its dependencies ---------------------------------
if [ "$SKIP_SETUP" -eq 0 ]; then
  # A venv isn't guaranteed to have pip bundled (e.g. one created by `uv venv`
  # deliberately omits it) — bootstrap it via the stdlib rather than failing.
  if ! "$VENV_BIN/python" -m pip --version >/dev/null 2>&1; then
    info "pip isn't available in this virtual environment; bootstrapping it ..."
    "$VENV_BIN/python" -m ensurepip --upgrade \
      || fail "Couldn't bootstrap pip into .venv. Delete the .venv folder and" \
              "re-run this script to recreate it from scratch."
  fi

  info "Installing dependencies (this can take a few minutes the first time) ..."
  "$VENV_BIN/python" -m pip install --upgrade --quiet pip
  "$VENV_BIN/python" -m pip install --quiet -e "$SCRIPT_DIR"'[all]' \
    || fail "Dependency installation failed — see the pip output above."
  ok "Dependencies installed."
else
  info "Skipping dependency install (--skip-setup)."
fi

# -- .env: create from the example on first run, never overwrite an existing one -------
if [ ! -f "$SCRIPT_DIR/.env" ] && [ -f "$SCRIPT_DIR/.env.example" ]; then
  cp "$SCRIPT_DIR/.env.example" "$SCRIPT_DIR/.env"
  warn "Created .env from .env.example. Edit it to set your clinic name, SMS" \
       "provider credentials, etc. — see README.md."
fi

# -- web UI: build the static export once, then reuse it -------------------------------
# `drscreen web` serves frontend/out itself, so the UI needs Node only at
# build time — never at runtime.
UI_DIR="$SCRIPT_DIR/frontend"
if [ "$SKIP_SETUP" -eq 0 ] && [ ! -d "$UI_DIR/out" ]; then
  if command -v npm >/dev/null 2>&1; then
    info "Building the web UI (first run only; a few minutes) ..."
    ( cd "$UI_DIR" \
      && { [ -d node_modules ] || npm install --no-audit --no-fund; } \
      && npm run build ) \
      || warn "UI build failed — the API will still start, but there'll be no interface." \
              "Fix it with: cd frontend && npm install && npm run build"
    [ -d "$UI_DIR/out" ] && ok "Web UI built."
  else
    warn "Node.js/npm not found, so the web UI can't be built. Install Node 20+ from" \
         "https://nodejs.org and re-run, or use the CLI commands (predict, batch-screen)."
  fi
fi

# -- model weights: warn, don't fail (some commands don't need them) -------------------
if [ ! -f "$SCRIPT_DIR/models/classifier.pt" ]; then
  warn "models/classifier.pt not found — 'predict'/'web'/'evaluate' need it." \
       "See models/README.md to download or train one."
fi

ok "Setup complete."

# -- run ---------------------------------------------------------------------------------
if [ "${#ARGS[@]}" -eq 1 ] && [ "${ARGS[0]}" = "setup" ]; then
  # "setup" isn't a real `drscreen` subcommand — it means what it says here:
  # do the environment setup above, then stop, rather than forwarding a word
  # the CLI doesn't recognise and erroring out.
  exit 0
elif [ "${#ARGS[@]}" -eq 0 ]; then
  info "No command given — launching the web app (drscreen web) at http://127.0.0.1:8000"
  exec "$VENV_BIN/drscreen" web
else
  info "Running: drscreen ${ARGS[*]}"
  exec "$VENV_BIN/drscreen" "${ARGS[@]}"
fi

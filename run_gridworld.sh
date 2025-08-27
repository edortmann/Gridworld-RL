#!/usr/bin/env bash
set -Eeuo pipefail

# ---------------------------
# Settings
# ---------------------------
REPO_URL="https://github.com/edortmann/Gridworld-RL.git"
REPO_DIR="$HOME/Gridworld-RL"
VENV_DIR="$HOME/.gridworld-venv"
KERNEL_NAME="gridworld-venv"
KERNEL_DISPLAY="Python (gridworld-venv)"
TARGET_NOTEBOOK="gridworld_linux.ipynb"

# ---------------------------
# Helpers
# ---------------------------
log() { printf "\033[1;32m[INFO]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err() { printf "\033[1;31m[ERR ]\033[0m %s\n" "$*"; }
die() { err "$*"; exit 1; }

SUDO=""
if [ "${EUID:-$(id -u)}" -ne 0 ] && command -v sudo >/dev/null 2>&1; then
  SUDO="sudo"
fi

PM=""; PM_INSTALL=""
if command -v apt-get >/dev/null 2>&1; then
  PM="apt-get"; PM_INSTALL="$SUDO apt-get install -y"
  $SUDO apt-get update -y || true
elif command -v dnf >/dev/null 2>&1; then
  PM="dnf"; PM_INSTALL="$SUDO dnf install -y"
elif command -v yum >/dev/null 2>&1; then
  PM="yum"; PM_INSTALL="$SUDO yum install -y"
elif command -v pacman >/dev/null 2>&1; then
  PM="pacman"; PM_INSTALL="$SUDO pacman -Sy --noconfirm"
elif command -v zypper >/dev/null 2>&1; then
  PM="zypper"; PM_INSTALL="$SUDO zypper install -y"
else
  warn "No known package manager (apt/dnf/yum/pacman/zypper) found. Skipping system package installs."
fi

ensure_pkg() {
  local bin="$1"; shift
  if command -v "$bin" >/dev/null 2>&1; then return 0; fi
  if [ -n "$PM" ]; then
    log "Installing $* (for $bin)…"
    # shellcheck disable=SC2086
    $PM_INSTALL "$@" || warn "Could not install $* via $PM. You may need to install it manually."
  else
    warn "Cannot install $* automatically. Please install it manually."
  fi
}

# ---------------------------
# 1) Ensure Python 3 + venv/pip & git
# ---------------------------
if ! command -v python3 >/dev/null 2>&1; then
  log "Python3 not found — attempting installation."
  case "$PM" in
    apt-get) ensure_pkg python3 python3 python3-venv python3-pip ;;
    dnf|yum) ensure_pkg python3 python3 python3-pip ;;
    pacman)  ensure_pkg python3 python python-pip ;;
    zypper)  ensure_pkg python3 python3 python3-pip ;;
    *) die "Python3 is required but could not be installed automatically." ;;
  esac
fi

ensure_pkg git git

# Optional niceties (for video export & emoji rendering)
case "$PM" in
  apt-get)
    ensure_pkg ffmpeg ffmpeg
    ensure_pkg fc-cache fontconfig
    ensure_pkg emoji-fonts fonts-noto-color-emoji
    ;;
  dnf|yum)
    ensure_pkg ffmpeg ffmpeg || true
    ensure_pkg fc-cache fontconfig
    ensure_pkg emoji-fonts google-noto-emoji-color-fonts || true
    ;;
  pacman)
    ensure_pkg ffmpeg ffmpeg || true
    ensure_pkg fc-cache fontconfig
    ensure_pkg emoji-fonts noto-fonts-emoji || true
    ;;
  zypper)
    ensure_pkg ffmpeg ffmpeg || true
    ensure_pkg fc-cache fontconfig
    $PM_INSTALL noto-emoji-color-fonts || $PM_INSTALL google-noto-emoji-color-fonts || true
    ;;
esac

if command -v fc-cache >/dev/null 2>&1; then fc-cache -f || true; fi

# ---------------------------
# 2) Create & activate venv
# ---------------------------
PY_BIN="$(command -v python3 || true)"
[ -n "$PY_BIN" ] || die "python3 not available after installation attempt."

if [ ! -d "$VENV_DIR" ]; then
  log "Creating virtual environment at $VENV_DIR"
  "$PY_BIN" -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

log "Upgrading pip/setuptools/wheel in venv…"
"$VENV_PY" -m pip install --upgrade pip setuptools wheel >/dev/null

# ---------------------------
# 3) Install JupyterLab & requested packages in the venv
# ---------------------------
log "Installing JupyterLab and widgets in the venv…"
"$VENV_PY" -m pip install -U \
  jupyterlab ipywidgets jupyterlab_widgets widgetsnbextension ipykernel >/dev/null

# Useful scientific/visualization stack
"$VENV_PY" -m pip install -U numpy matplotlib pillow plotly moviepy imageio imageio-ffmpeg >/dev/null

# ---------------------------
# 4) Clone or update the repo
# ---------------------------
if [ -d "$REPO_DIR/.git" ]; then
  log "Updating existing repo at $REPO_DIR"
  git -C "$REPO_DIR" pull --rebase
else
  log "Cloning repo to $REPO_DIR"
  git clone --depth 1 "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"

# If the repo provides requirements.txt, prefer it (inside the venv).
if [ -f requirements.txt ]; then
  log "Installing Python dependencies from requirements.txt in the venv…"
  "$VENV_PY" -m pip install -r requirements.txt
fi

# ---------------------------
# 5) Register the venv as a Jupyter kernel
# ---------------------------
log "Registering Jupyter kernel: $KERNEL_NAME"
"$VENV_PY" -m ipykernel install --user \
  --name "$KERNEL_NAME" \
  --display-name "$KERNEL_DISPLAY" >/dev/null

# ---------------------------
# 6) Launch JupyterLab *from the venv*
# ---------------------------
NB_TO_OPEN="$TARGET_NOTEBOOK"
if [ ! -f "$NB_TO_OPEN" ]; then
  NB_TO_OPEN="$(ls -1 *.ipynb 2>/dev/null | grep -E '^gridworld.*\.ipynb$' | head -n1 || true)"
fi

log "Starting JupyterLab from the venv…"
if [ -n "$NB_TO_OPEN" ] && [ -f "$NB_TO_OPEN" ]; then
  exec "$VENV_PY" -m jupyter lab "$NB_TO_OPEN"
else
  warn "Could not find $TARGET_NOTEBOOK. Opening JupyterLab file browser instead."
  exec "$VENV_PY" -m jupyter lab
fi

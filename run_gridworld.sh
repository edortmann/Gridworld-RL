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

install_pkgs() {
  # shellcheck disable=SC2086
  [ -n "$PM" ] && $PM_INSTALL "$@" || warn "Cannot install $* automatically. Please install manually."
}

# ---------------------------
# 1) Ensure Python, Git, and (critically) ensurepip/venv support
# ---------------------------
if ! command -v python3 >/dev/null 2>&1; then
  log "Python3 not found — attempting installation."
  case "$PM" in
    apt-get) install_pkgs python3 python3-pip ;;  # venv handled separately below
    dnf|yum) install_pkgs python3 python3-pip ;;
    pacman)  install_pkgs python python-pip ;;
    zypper)  install_pkgs python3 python3-pip ;;
    *) die "Python3 is required but could not be installed automatically." ;;
  esac
fi

if ! command -v git >/dev/null 2>&1; then
  install_pkgs git
fi

# --- FIX: make sure ensurepip is present (Debian/Ubuntu split it out) ---
PY_BIN="$(command -v python3)"
if ! "$PY_BIN" - <<'PY' >/dev/null 2>&1
import ensurepip
PY
then
  log "ensurepip missing — installing venv support for your Python."
  case "$PM" in
    apt-get)
      # Try generic first, then versioned (e.g., python3.12-venv)
      install_pkgs python3-venv || {
        ver="$("$PY_BIN" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")')"
        install_pkgs "python${ver}-venv" || die "Could not install python-venv package (tried python3-venv and python${ver}-venv)."
      }
      ;;
    dnf|yum)
      # Usually included with python3, but install if available
      install_pkgs python3-venv || true
      ;;
    pacman)
      # venv is part of python on Arch
      :
      ;;
    zypper)
      install_pkgs python3-venv || true
      ;;
    *)
      warn "Unable to install venv support automatically. Please install your distro's python3-venv package."
      ;;
  esac
fi

# ---------------------------
# 2) Optional niceties (ffmpeg, emoji font)
# ---------------------------
case "$PM" in
  apt-get)
    install_pkgs ffmpeg || true
    install_pkgs fontconfig || true
    install_pkgs fonts-noto-color-emoji || true
    ;;
  dnf|yum)
    install_pkgs ffmpeg || true
    install_pkgs fontconfig || true
    install_pkgs google-noto-emoji-color-fonts || true
    ;;
  pacman)
    install_pkgs ffmpeg || true
    install_pkgs fontconfig || true
    install_pkgs noto-fonts-emoji || true
    ;;
  zypper)
    install_pkgs ffmpeg || true
    install_pkgs fontconfig || true
    $PM_INSTALL noto-emoji-color-fonts || $PM_INSTALL google-noto-emoji-color-fonts || true
    ;;
esac
command -v fc-cache >/dev/null 2>&1 && fc-cache -f || true

# ---------------------------
# 3) Create venv
# ---------------------------
if [ -d "$VENV_DIR" ]; then
  warn "Existing venv at $VENV_DIR detected."
else
  log "Creating virtual environment at $VENV_DIR"
  "$PY_BIN" -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"

log "Upgrading pip/setuptools/wheel in venv…"
"$VENV_PY" -m pip install --upgrade pip setuptools wheel >/dev/null

# ---------------------------
# 4) Install JupyterLab + requested packages in the venv
# ---------------------------
log "Installing JupyterLab and widgets in the venv…"
"$VENV_PY" -m pip install -U \
  jupyterlab ipywidgets jupyterlab_widgets widgetsnbextension ipykernel >/dev/null

# Useful libs for the notebook
"$VENV_PY" -m pip install -U numpy matplotlib pillow plotly moviepy imageio imageio-ffmpeg >/dev/null

# ---------------------------
# 5) Clone or update the repo
# ---------------------------
if [ -d "$REPO_DIR/.git" ]; then
  log "Updating existing repo at $REPO_DIR"
  git -C "$REPO_DIR" pull --rebase
else
  log "Cloning repo to $REPO_DIR"
  git clone --depth 1 "$REPO_URL" "$REPO_DIR"
fi

cd "$REPO_DIR"

# If requirements.txt exists, install it into the venv
if [ -f requirements.txt ]; then
  log "Installing Python dependencies from requirements.txt in the venv…"
  "$VENV_PY" -m pip install -r requirements.txt
fi

# ---------------------------
# 6) Register the venv as a kernel
# ---------------------------
log "Registering Jupyter kernel: $KERNEL_NAME"
"$VENV_PY" -m ipykernel install --user \
  --name "$KERNEL_NAME" \
  --display-name "$KERNEL_DISPLAY" >/dev/null

# ---------------------------
# 7) Launch JupyterLab from the venv
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

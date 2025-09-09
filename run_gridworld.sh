#!/usr/bin/env bash
set -Eeuo pipefail

# ---------------------------
# Settings
# ---------------------------
REPO_URL="https://github.com/edortmann/Gridworld-RL"
REPO_DIR="$HOME/Gridworld-RL"
VENV_DIR="$HOME/.gridworld-venv"
KERNEL_NAME="gridworld-venv"
KERNEL_DISPLAY="Python (gridworld-venv)"
TARGET_NOTEBOOK="gridworld_linux.ipynb"
MINIFORGE_DIR="$HOME/.miniforge"

# ---------------------------
# Helpers
# ---------------------------
log()  { printf "\033[1;32m[INFO]\033[0m %s\n" "$*"; }
warn() { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
err()  { printf "\033[1;31m[ERR ]\033[0m %s\n" "$*"; }
die()  { err "$*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

download() { # url -> dest
  local url="$1" dest="$2"
  if have curl; then curl -L --fail -o "$dest" "$url"
  elif have wget; then wget -O "$dest" "$url"
  elif have python3; then
    python3 - "$url" "$dest" <<'PY'
import sys,urllib.request
urllib.request.urlretrieve(sys.argv[1], sys.argv[2])
PY
  else
    die "Need curl or wget or python3 to download: $url"
  fi
}

ensure_python_with_venv() {
  # Return a python3 that can create venvs; reuse Miniforge if already installed.
  local py="${1:-$(command -v python3 || true)}"
  if [ -n "$py" ] && "$py" - <<'PY' >/dev/null 2>&1
import sys, ensurepip; assert sys.version_info[:2] >= (3,8)
PY
  then
    echo "$py"; return 0
  fi

  if [ -x "$MINIFORGE_DIR/bin/python3" ]; then
    log "Using existing Miniforge at $MINIFORGE_DIR"
    echo "$MINIFORGE_DIR/bin/python3"; return 0
  fi

  log "System Python lacks ensurepip/venv — installing Miniforge to \$HOME"
  local arch="$(uname -m)" os="Linux" mf_url=""
  case "$arch" in
    x86_64)  mf_url="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-${os}-x86_64.sh" ;;
    aarch64) mf_url="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-${os}-aarch64.sh" ;;
    *) die "Unsupported CPU arch: $arch" ;;
  esac
  mkdir -p "$MINIFORGE_DIR"
  tmp_inst="$(mktemp)"; download "$mf_url" "$tmp_inst"
  bash "$tmp_inst" -b -p "$MINIFORGE_DIR"; rm -f "$tmp_inst"
  [ -x "$MINIFORGE_DIR/bin/python3" ] || die "Miniforge install failed."
  echo "$MINIFORGE_DIR/bin/python3"
}

# ---------------------------
# 1) Python with venv support (no sudo)
# ---------------------------
PY_BIN="$(ensure_python_with_venv)"
log "Using Python at: $PY_BIN"

# ---------------------------
# 2) Create or reuse venv
# ---------------------------
if [ -d "$VENV_DIR" ]; then
  log "Reusing existing venv at $VENV_DIR"
else
  log "Creating virtual environment at $VENV_DIR"
  "$PY_BIN" -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"

log "Upgrading pip/setuptools/wheel in venv …"
"$VENV_PY" -m pip install --quiet --upgrade pip setuptools wheel

log "Installing JupyterLab & core libs …"
"$VENV_PY" -m pip install -q -U jupyterlab ipywidgets jupyterlab_widgets widgetsnbextension ipykernel
"$VENV_PY" -m pip install -q -U numpy matplotlib pillow plotly moviepy imageio imageio-ffmpeg

# ---------------------------
# 3) Repo: clone or force-update to origin (no stash)
# ---------------------------
if have git; then
  if [ -d "$REPO_DIR/.git" ]; then
    log "Updating Git repo at $REPO_DIR (discarding local changes to tracked files)"
    # ensure origin points to the right URL
    if ! git -C "$REPO_DIR" remote get-url origin >/dev/null 2>&1; then
      git -C "$REPO_DIR" remote add origin "$REPO_URL".git
    fi
    git -C "$REPO_DIR" remote set-url origin "$REPO_URL".git || true
    git -C "$REPO_DIR" fetch --all --tags --prune
    # detect default branch
    head_branch="$(git -C "$REPO_DIR" remote show origin | sed -n 's/ *HEAD branch: //p')"
    [ -n "$head_branch" ] || head_branch="main"
    # ensure branch exists locally and is checked out
    if ! git -C "$REPO_DIR" show-ref --verify --quiet "refs/heads/$head_branch"; then
      git -C "$REPO_DIR" checkout -B "$head_branch" "origin/$head_branch" || git -C "$REPO_DIR" checkout -B "$head_branch" "origin/master"
    else
      git -C "$REPO_DIR" checkout "$head_branch"
    fi
    # hard reset to remote (no stash, no merge)
    git -C "$REPO_DIR" reset --hard "origin/$head_branch"
    # (optional) clean untracked files/dirs; commented to avoid deleting user files
    # git -C "$REPO_DIR" clean -fd
  elif [ -d "$REPO_DIR" ]; then
    ts="$(date +%Y%m%d-%H%M%S)"; bak="${REPO_DIR}.bak-${ts}"
    warn "Existing non-git folder at $REPO_DIR — moving to $bak"
    mv "$REPO_DIR" "$bak"
    log "Cloning repo to $REPO_DIR"
    git clone --depth 1 "$REPO_URL".git "$REPO_DIR"
  else
    log "Cloning repo to $REPO_DIR"
    git clone --depth 1 "$REPO_URL".git "$REPO_DIR"
  fi
else
  # No git available: download zip and atomically replace folder
  log "git not found — using zip download."
  tmpzip="$(mktemp --suffix=.zip)"
  if ! download "$REPO_URL/archive/refs/heads/main.zip" "$tmpzip"; then
    download "$REPO_URL/archive/refs/heads/master.zip" "$tmpzip"
  fi
  tmpdir="$(mktemp -d)"
  "$VENV_PY" - <<PY "$tmpzip" "$tmpdir"
import sys,zipfile,os
zip_path,outdir=sys.argv[1],sys.argv[2]
with zipfile.ZipFile(zip_path) as z: z.extractall(outdir)
print(next(p for p in os.listdir(outdir) if os.path.isdir(os.path.join(outdir,p))))
PY
  topdir="$tmpdir/$(ls -1 "$tmpdir" | head -n1)"
  # Replace existing folder (keep a timestamped backup)
  if [ -e "$REPO_DIR" ]; then
    ts="$(date +%Y%m%d-%H%M%S)"; bak="${REPO_DIR}.bak-${ts}"
    warn "Replacing existing $REPO_DIR (zip mode). Backup at $bak"
    rm -rf "$bak"; mv "$REPO_DIR" "$bak"
  fi
  mv "$topdir" "$REPO_DIR"
  rm -rf "$tmpzip" "$tmpdir"
fi

cd "$REPO_DIR"

# ---------------------------
# 4) Install repo requirements (if present)
# ---------------------------
if [ -f requirements.txt ]; then
  log "Installing Python dependencies from requirements.txt …"
  "$VENV_PY" -m pip install -q -r requirements.txt
fi

# ---------------------------
# 5) Register kernel (safe to repeat) & launch JupyterLab
# ---------------------------
log "Registering Jupyter kernel: $KERNEL_NAME"
"$VENV_PY" -m ipykernel install --user --name "$KERNEL_NAME" --display-name "$KERNEL_DISPLAY" >/dev/null

NB_TO_OPEN="$TARGET_NOTEBOOK"
if [ ! -f "$NB_TO_OPEN" ]; then
  NB_TO_OPEN="$(ls -1 *.ipynb 2>/dev/null | grep -E '^gridworld.*\.ipynb$' | head -n1 || true)"
fi

log "Starting JupyterLab from the venv …"
if [ -n "$NB_TO_OPEN" ] && [ -f "$NB_TO_OPEN" ]; then
  exec "$VENV_PY" -m jupyter lab "$NB_TO_OPEN"
else
  warn "Could not find $TARGET_NOTEBOOK. Opening JupyterLab file browser instead."
  exec "$VENV_PY" -m jupyter lab
fi

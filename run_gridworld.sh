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
  # Return a python3 that can create venvs (printed on stdout). Reuse Miniforge if present.
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

  log "System Python lacks ensurepip/venv — installing Miniforge in \$HOME."
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
# 1) Get a python that can create venvs (no sudo)
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
VENV_PIP="$VENV_DIR/bin/pip"

log "Upgrading pip/setuptools/wheel in venv …"
"$VENV_PY" -m pip install --upgrade pip setuptools wheel >/dev/null

# ---------------------------
# 3) Install JupyterLab & essentials
# ---------------------------
log "Installing JupyterLab, widgets, ipykernel …"
"$VENV_PY" -m pip install -U \
  jupyterlab ipywidgets jupyterlab_widgets widgetsnbextension ipykernel >/dev/null

# Optional but handy libs for the notebook
"$VENV_PY" -m pip install -U numpy matplotlib pillow plotly moviepy imageio imageio-ffmpeg >/dev/null

# ---------------------------
# 4) Get or update the repo
# ---------------------------
if have git; then
  if [ -d "$REPO_DIR/.git" ]; then
    log "Updating Git repo at $REPO_DIR"
    git -C "$REPO_DIR" remote get-url origin >/dev/null 2>&1 || git -C "$REPO_DIR" remote add origin "$REPO_URL".git
    git -C "$REPO_DIR" fetch --all --tags
    # Pull on current branch (tracks origin/<branch> if set)
    if ! git -C "$REPO_DIR" pull --rebase; then
      warn "git pull failed (local changes?). Trying a safer fast-forward."
      git -C "$REPO_DIR" merge --ff-only || warn "Fast-forward failed; please resolve manually."
    fi
  elif [ -d "$REPO_DIR" ]; then
    # Folder exists but isn't a git repo (e.g., from zip). Back it up and clone cleanly.
    ts="$(date +%Y%m%d-%H%M%S)"
    bak="${REPO_DIR}.bak-${ts}"
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
  # try main first; fallback to master
  if ! download "$REPO_URL/archive/refs/heads/main.zip" "$tmpzip"; then
    download "$REPO_URL/archive/refs/heads/master.zip" "$tmpzip"
  fi
  tmpdir="$(mktemp -d)"
  "$VENV_PY" - <<PY "$tmpzip" "$tmpdir"
import sys,zipfile,os
zip_path, outdir = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(zip_path) as z:
    z.extractall(outdir)
print(next(p for p in os.listdir(outdir) if os.path.isdir(os.path.join(outdir,p))))
PY
  topdir="$tmpdir/$(ls -1 "$tmpdir" | head -n1)"
  # Atomic-ish replace: move old to backup, then move new into place
  if [ -e "$REPO_DIR" ]; then
    ts="$(date +%Y%m%d-%H%M%S)"; bak="${REPO_DIR}.bak-${ts}"
    warn "Replacing existing $REPO_DIR (no git). Backup at $bak"
    rm -rf "$bak"; mv "$REPO_DIR" "$bak"
  fi
  mv "$topdir" "$REPO_DIR"
  rm -rf "$tmpzip" "$tmpdir"
fi

cd "$REPO_DIR"

# ---------------------------
# 5) Install repo requirements (if present) into the venv
# ---------------------------
if [ -f requirements.txt ]; then
  log "Installing Python dependencies from requirements.txt …"
  "$VENV_PY" -m pip install -r requirements.txt
fi

# ---------------------------
# 6) Register/re-register the venv as a Jupyter kernel
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

log "Starting JupyterLab from the venv …"
if [ -n "$NB_TO_OPEN" ] && [ -f "$NB_TO_OPEN" ]; then
  exec "$VENV_PY" -m jupyter lab "$NB_TO_OPEN"
else
  warn "Could not find $TARGET_NOTEBOOK. Opening JupyterLab file browser instead."
  exec "$VENV_PY" -m jupyter lab
fi

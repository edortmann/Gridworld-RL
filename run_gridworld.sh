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

download() {
  # download URL -> dest
  local url="$1" dest="$2"
  if have curl; then
    curl -L --fail -o "$dest" "$url"
  elif have wget; then
    wget -O "$dest" "$url"
  else
    # try Python stdlib as last resort
    if have python3; then
      python3 - "$url" "$dest" <<'PY'
import sys,urllib.request
url,dst=sys.argv[1],sys.argv[2]
urllib.request.urlretrieve(url,dst)
PY
    else
      die "Need curl or wget (or python3) to download: $url"
    fi
  fi
}

ensure_python_with_venv() {
  # Return path to a python3 that can create venvs (prints on stdout).
  local py="${1:-$(command -v python3 || true)}"

  if [ -n "$py" ] && "$py" - <<'PY' >/dev/null 2>&1
import sys,ensurepip; assert sys.version_info[:2] >= (3,8)
PY
  then
    echo "$py"; return 0
  fi

  log "System Python missing ensurepip or too old — installing a user-local Python via Miniforge."
  # pick Miniforge installer for arch
  local arch="$(uname -m)"
  local os="Linux"
  local mf_url=""
  case "$arch" in
    x86_64)  mf_url="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-${os}-x86_64.sh" ;;
    aarch64) mf_url="https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-${os}-aarch64.sh" ;;
    *) die "Unsupported CPU arch: $arch (cannot auto-install Miniforge)";;
  esac

  mkdir -p "$MINIFORGE_DIR"
  tmp_inst="$(mktemp)"
  download "$mf_url" "$tmp_inst"
  bash "$tmp_inst" -b -p "$MINIFORGE_DIR"
  rm -f "$tmp_inst"

  local forge_py="$MINIFORGE_DIR/bin/python3"
  [ -x "$forge_py" ] || die "Miniforge install failed (no python at $forge_py)."
  echo "$forge_py"
}

# ---------------------------
# 1) Get a python that can create venvs (no sudo)
# ---------------------------
PY_BIN="$(ensure_python_with_venv)"
log "Using Python at: $PY_BIN"

# ---------------------------
# 2) Create venv
# ---------------------------
if [ -d "$VENV_DIR" ]; then
  log "Using existing venv at $VENV_DIR"
else
  log "Creating virtual environment at $VENV_DIR"
  "$PY_BIN" -m venv "$VENV_DIR"
fi

VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

log "Upgrading pip/setuptools/wheel in venv…"
"$VENV_PY" -m pip install --upgrade pip setuptools wheel >/dev/null

# ---------------------------
# 3) Install JupyterLab + requested packages (in venv)
# ---------------------------
log "Installing JupyterLab, widgets, ipykernel…"
"$VENV_PY" -m pip install -U \
  jupyterlab ipywidgets jupyterlab_widgets widgetsnbextension ipykernel >/dev/null

# Useful libs for the notebook (all user-space)
"$VENV_PY" -m pip install -U numpy matplotlib pillow plotly moviepy imageio imageio-ffmpeg >/dev/null

# ---------------------------
# 4) Fetch repo (git if available, else zip download)
# ---------------------------
if [ -d "$REPO_DIR/.git" ] && have git; then
  log "Updating existing repo at $REPO_DIR"
  git -C "$REPO_DIR" pull --rebase
elif have git; then
  log "Cloning repo to $REPO_DIR"
  git clone --depth 1 "$REPO_URL".git "$REPO_DIR"
else
  log "git not found — downloading zip archive instead."
  rm -rf "$REPO_DIR"
  mkdir -p "$REPO_DIR"
  # try main first, fallback to master
  tmpzip="$(mktemp --suffix=.zip)"
  if download "$REPO_URL/archive/refs/heads/main.zip" "$tmpzip"; then
    :
  elif download "$REPO_URL/archive/refs/heads/master.zip" "$tmpzip"; then
    :
  else
    die "Failed to download repository archive."
  fi
  log "Extracting archive…"
  "$VENV_PY" - <<PY "$tmpzip" "$REPO_DIR"
import sys,zipfile,os,shutil
zip_path, dest = sys.argv[1], sys.argv[2]
with zipfile.ZipFile(zip_path) as z:
    top = z.namelist()[0].rstrip('/')
    z.extractall(os.path.dirname(dest))
src = os.path.join(os.path.dirname(dest), top)
if os.path.exists(dest):
    shutil.rmtree(dest)
shutil.move(src, dest)
print("Extracted to", dest)
PY
  rm -f "$tmpzip"
fi

cd "$REPO_DIR"

# ---------------------------
# 5) Install repo requirements (if present) into the venv
# ---------------------------
if [ -f requirements.txt ]; then
  log "Installing Python dependencies from requirements.txt…"
  "$VENV_PY" -m pip install -r requirements.txt
fi

# ---------------------------
# 6) Register the venv as a Jupyter kernel (user scope)
# ---------------------------
log "Registering Jupyter kernel: $KERNEL_NAME"
"$VENV_PY" -m ipykernel install --user \
  --name "$KERNEL_NAME" \
  --display-name "$KERNEL_DISPLAY" >/dev/null

# ---------------------------
# 7) Launch JupyterLab from the venv (open notebook if present)
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

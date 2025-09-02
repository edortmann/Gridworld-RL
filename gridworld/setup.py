def setup():

    # Pakete im aktuellen Jupyter‑Kernel installieren
    # Cross-platform, PEP 668-safe setup for this notebook
    import sys, os, json, subprocess
    from pathlib import Path

    VENV_DIR = Path(".gridworld-venv")
    VENV_PY = VENV_DIR / ("Scripts/python.exe" if os.name == "nt" else "bin/python")

    def sh(*args):
        subprocess.check_call(list(map(str, args)))

    # 1) Create a local virtual environment (safe on Ubuntu/Debian)
    if not VENV_PY.exists():
        sh(sys.executable, "-m", "venv", str(VENV_DIR), "--upgrade-deps")

    # 2) Make sure pip/setuptools/wheel are up to date inside the venv
    sh(VENV_PY, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel")

    # 3) Install all packages
    pkgs = [
        "numpy",
        "matplotlib",
        "plotly",
        "ipywidgets",
        "pillow",
        "moviepy",
        "imageio[ffmpeg]",  # ensures ffmpeg binary via imageio-ffmpeg
        "ipykernel",
    ]
    sh(VENV_PY, "-m", "pip", "install", *pkgs)

    # 4) Register Jupyter kernel
    sh(VENV_PY, "-m", "ipykernel", "install", "--user",
       "--name", "gridworld-venv", "--display-name", "Python (gridworld-venv)")

    # 5) Also make the venv's site-packages available immediately in this session
    site_paths = subprocess.check_output([
        str(VENV_PY), "-c",
        "import site, json; print(json.dumps(site.getsitepackages()+[site.getusersitepackages()]))"
    ]).decode("utf-8")
    for p in json.loads(site_paths):
        if p not in sys.path:
            sys.path.insert(0, p)


    # --- Font setup --------------------------------------------
    import io, zipfile, urllib.request, subprocess
    from pathlib import Path

    FONT_DIR = Path.home() / ".local" / "share" / "fonts"
    FONT_DIR.mkdir(parents=True, exist_ok=True)

    def download(url: str, dest: Path, label: str):
        if dest.exists():
            print(f"✅ {label} already present")
            return
        print(f"↓ Downloading {label} …")
        with urllib.request.urlopen(url) as r:
            data = r.read()
        dest.write_bytes(data)
        print(f"✅ Saved {label} -> {dest}")

    # 1) Color emoji (works in many Linux apps, especially Chromium/Chrome)
    download(
        "https://github.com/googlefonts/noto-emoji/raw/main/fonts/NotoColorEmoji.ttf",
        FONT_DIR / "NotoColorEmoji.ttf",
        "NotoColorEmoji.ttf"
    )

    # 2) Monochrome emoji fallback (static TTF) from CTAN bundle
    mono_ttf = FONT_DIR / "NotoEmoji-Regular.ttf"
    if not mono_ttf.exists():
        print("↓ Fetching NotoEmoji-Regular.ttf from CTAN zip …")
        with urllib.request.urlopen("https://mirrors.ctan.org/fonts/noto-emoji.zip") as r:
            zdata = io.BytesIO(r.read())
        with zipfile.ZipFile(zdata) as zf:
            # Path inside the zip:
            # texmf-dist/fonts/truetype/google/noto-emoji/NotoEmoji-Regular.ttf
            candidates = [n for n in zf.namelist() if n.endswith("/NotoEmoji-Regular.ttf")]
            if not candidates:
                raise RuntimeError("NotoEmoji-Regular.ttf not found in CTAN package")
            with zf.open(candidates[0]) as fsrc:
                mono_ttf.write_bytes(fsrc.read())
        print(f"✅ Saved NotoEmoji-Regular.ttf -> {mono_ttf}")

    # Rebuild font cache (safe to ignore output)
    try:
        subprocess.run(["fc-cache", "-f", "-v"], check=False, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    except Exception:
        pass


    # --- Make installed emoji immediately visible in this kernel ---
    FONT_DIR = Path.home() / ".local" / "share" / "fonts"
    chosen = FONT_DIR / "NotoColorEmoji.ttf"
    if not chosen.exists():
        alt = FONT_DIR / "NotoEmoji-Regular.ttf"
        if alt.exists():
            chosen = alt
    if chosen.exists():
        os.environ["GRIDWORLD_EMOJI_FONT"] = str(chosen)

    # --- Optional: prefer color emoji in general UI text via fontconfig (no sudo) ---
    try:
        conf_dir = Path.home() / ".config" / "fontconfig"
        conf_dir.mkdir(parents=True, exist_ok=True)
        fonts_conf = conf_dir / "fonts.conf"
        fonts_conf.write_text("""<?xml version="1.0"?>
<!DOCTYPE fontconfig SYSTEM "urn:fontconfig:fonts.dtd">
<fontconfig>
  <alias><family>sans-serif</family><prefer><family>Noto Color Emoji</family></prefer></alias>
  <alias><family>serif</family><prefer><family>Noto Color Emoji</family></prefer></alias>
  <alias><family>monospace</family><prefer><family>Noto Color Emoji</family></prefer></alias>
</fontconfig>""")
        subprocess.run(["fc-cache", "-f"], check=False)
    except Exception:
        pass

    # --- Download Twemoji sprites for all glyphs we use (robust fallback) ---
    import urllib.request, json

    SPRITE_DIR = Path.home() / ".local" / "share" / "gridworld-emoji"
    SPRITE_DIR.mkdir(parents=True, exist_ok=True)
    os.environ["GRIDWORLD_EMOJI_SPRITES"] = str(SPRITE_DIR)

    def glyph_to_hex(g):
        cps = []
        for ch in g:
            cp = ord(ch)
            if cp in (0xFE0F, 0xFE0E):
                continue
            cps.append(f"{cp:x}")
        return "-".join(cps)

    glyphs = [
        "🤖", "🔰", "🚩", "🚧", "🕳️", "❄️", "🔴", "👣", "💰", "🔋", "💎", "🦘", "💨", "⚠️", "🌀",
        "⬆️", "⬇️", "⬅️", "➡️"
    ]

    base = "https://raw.githubusercontent.com/twitter/twemoji/v14.0.2/assets/72x72/{}.png"
    for g in glyphs:
        hexname = glyph_to_hex(g)
        dest = SPRITE_DIR / f"{hexname}.png"
        if dest.exists():
            continue
        try:
            with urllib.request.urlopen(base.format(hexname)) as r:
                data = r.read()
            dest.write_bytes(data)
            print(f"✅ sprite {g} -> {dest.name}")
        except Exception as e:
            print(f"⚠️ could not fetch sprite for {g} ({hexname}): {e}")


    print("Setup done.")

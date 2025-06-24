import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


# Symbolverzeichnis für die Felder
SYMBOLS = {
    "agent"      : "🤖",
    "start"      : "🔰",
    "goal"       : "🚩",
    "empty"      : "",
    "wall"       : "🧱️",  #"⬛️",
    "pit"        : "🕳️",
    "ice"        : "❄️",  #"🧊",
    "bumper"     : "🔴",  #"🪀️"
    "sticky"     : "🟫",
    "wind"       : "💨",
    "conveyor_U" : "⬆️",
    "conveyor_D" : "⬇️",
    "conveyor_L" : "⬅️",
    "conveyor_R" : "➡️",
    "trampoline" : "🦘",  #"↕️",
    "portal"     : "🌀",
    "collapse"   : "⚠️",
    "toll"       : "💰",
    "battery"    : "🔋️",
    "gem"        : "💎️",
}

def _symbol_for(env, r, c):
    """Gibt den SYMBOLS‑Schlüssel für die Position (r,c) in *env* zurück."""
    pos = (r, c)
    if pos == env.start_pos: return "start"
    if pos == env.goal_pos: return "goal"
    if pos in getattr(env, "wall_positions",       set()): return "wall"
    if pos in getattr(env, "pit_positions",        set()): return "pit"
    if pos in getattr(env, "ice_positions",        set()): return "ice"
    if pos in getattr(env, "bumper_positions",     set()): return "bumper"
    if pos in getattr(env, "sticky_positions",     set()): return "sticky"
    if pos in getattr(env, "wind_positions",       set()): return "wind"
    if pos in getattr(env, "trampoline_positions", set()): return "trampoline"
    if pos in getattr(env, "portal_lookup",       dict()): return "portal"
    if pos in getattr(env, "collapse_positions",   set()):  return "collapse"
    if pos in getattr(env, "already_collapsed",    set()): return "pit"
    if pos in getattr(env, "toll_positions",       set()):  return "toll"
    if pos in getattr(env, "battery_positions",    set()):  return "battery"
    if pos in getattr(env, "gem_positions",        set()):  return "gem"

    # conveyor
    conv_dir = getattr(env, "conveyor_map", {}).get(pos)
    if conv_dir:
        return f"conveyor_{conv_dir}"

    # portal
    for a,b in getattr(env, "portal_pairs", []):
        if pos in (a,b): return "portal"

    return "empty"


def _glyph_for(env, r, c):
    key = _symbol_for(env, r, c)
    return SYMBOLS.get(key)


# Hilfsfunktionen für Video Frames

# OS-specific colour emoji font
def _default_emoji_font(px):
    if sys.platform.startswith("win"):
        fp = Path(r"C:\Windows\Fonts\seguiemj.ttf")
    elif sys.platform.startswith("linux"):
        fp = Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf")
    else:
        raise OSError("Add a colour-emoji font path for your OS")
    return ImageFont.truetype(str(fp), px)


def _emoji_frame(rows, cols, cell_px, border, symbols, agent_pos, font_path=None, agent_glyph="🤖"):
    """
    Zeichne Grid-Umgebung basierend auf den Argumenten.

    symbols:     dict {(row, col): glyph}
    agent_pos:   (row, col)
    """
    W, H = cols * cell_px + 2 * border, rows * cell_px + 2 * border
    img = Image.new("RGBA", (W, H), "white")
    draw = ImageDraw.Draw(img)

    # grid lines
    for r in range(rows + 1):
        y = border + r * cell_px
        draw.line([(border, y), (W - border, y)], fill="grey")
    for c in range(cols + 1):
        x = border + c * cell_px
        draw.line([(x, border), (x, H - border)], fill="grey")

    # wähle font
    font = ImageFont.truetype(str(font_path), int(cell_px * 0.8)) if font_path else _default_emoji_font(
        int(cell_px * 0.8))

    # Hilfsfunktion, um Emojis zentriert in Feldern zu zeichnen
    def _draw_centered(glyph, cx, cy):
        g = glyph.replace("\uFE0F", "")
        l, t, rbb, bbb = draw.textbbox((0, 0), g, font=font, embedded_color=True)
        w, h = rbb - l, bbb - t
        draw.text((cx - w / 2 - l, cy - h / 2 - t), g, font=font, embedded_color=True)

    # zeichne emojis + agent
    if agent_pos:
        symbols = dict(symbols)
        symbols[agent_pos] = agent_glyph

    for (r, c), glyph in symbols.items():
        gx, gy = border + c * cell_px + cell_px // 2, border + r * cell_px + cell_px // 2
        _draw_centered(glyph, gx, gy)
        # draw.text((gx, gy),
        #          glyph.replace("\uFE0F", ""),    # drop VS-16
        #          font=font,
        #          anchor="mm",
        #          embedded_color=True)
    return img


_PRESET_RES = {"720p": (1280, 720), "1080p": (1920, 1080)}
# Hilfsfunktion für die Auflösung der Videos
def _parse_resolution(res):
    """
    Akzeptiert '720p', '1080p', ein (Breite, Höhe) Tupel oder None
    """
    if res is None:
        return None
    if isinstance(res, str):
        try:
            return _PRESET_RES[res.lower()]
        except KeyError:
            raise ValueError(f"Unknown preset '{res}'. Use one of {list(_PRESET_RES)} or pass a (width, height) tuple.")
    if len(res) == 2:
        return tuple(map(int, res))
    raise ValueError("Auflösung muss sein '720p' / '1080p' / (Breite, Höhe) / None")
import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Dict, Tuple, Optional
from PIL import Image, ImageDraw, ImageFont

# =========================
# Emoji + Symbols
# =========================

SYMBOLS: Dict[str, str] = {
    "agent": "🤖",
    "start": "🔰",
    "goal": "🚩",
    "empty": "",
    "wall": "🚧",
    "pit": "🕳️",
    "ice": "❄️",
    "bumper": "🔴",
    "sticky": "👣",
    "toll": "💰",
    "battery": "🔋",
    "gem": "💎",
    "trampoline": "🦘",
    "wind": "💨",
    "collapse": "⚠️",
    "portal": "🌀",
    "conveyor_U": "⬆️",
    "conveyor_D": "⬇️",
    "conveyor_L": "⬅️",
    "conveyor_R": "➡️",
}

_PRESET_RES = {"720p": (1280, 720), "1080p": (1920, 1080)}

def _parse_resolution(res):
    if res is None:
        return None
    if isinstance(res, str):
        try:
            return _PRESET_RES[res.lower()]
        except KeyError:
            raise ValueError(f"Unknown preset '{res}'. Use one of {list(_PRESET_RES)} or pass a (width, height) tuple.")
    if len(res) == 2:
        return tuple(map(int, res))
    raise ValueError("Resolution must be '720p' / '1080p' / (width, height) / None")

# =========================
# Font helpers
# =========================

def _resolve_font(px: int) -> Tuple[ImageFont.FreeTypeFont, bool]:
    """
    Try fonts in a sensible order and return (font, is_color_font).
    Avoids 'invalid pixel size' by probing safe sizes for bitmap/color fonts.
    """
    home = Path.home()
    candidates = [
        # Prefer color emoji first (if system supports it)
        home / ".local/share/fonts/NotoColorEmoji.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf"),
        Path(r"C:\Windows\Fonts\seguiemj.ttf") if sys.platform.startswith("win") else None,

        # Monochrome emoji fallback
        home / ".local/share/fonts/NotoEmoji-Regular.ttf",
        Path("/usr/share/fonts/truetype/noto/NotoEmoji-Regular.ttf"),

        # Generic fallback: no emoji, prevents crashes
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]

    def _try_sizes(path: Path, base_px: int):
        safe = [base_px, 128, 96, 72, 64, 56, 48, 44, 40, 36, 32, 28, 26, 24, 22, 20, 18, 16]
        last = None
        for s in safe:
            try:
                return ImageFont.truetype(str(path), s), s
            except OSError as e:
                last = e
        raise last

    for fp in candidates:
        if not fp:
            continue
        if not fp.exists():
            continue
        try:
            fnt, used_px = _try_sizes(fp, px)
            is_color = ("ColorEmoji" in fp.name) or (fp.name.lower() == "seguiemj.ttf")
            return fnt, is_color
        except OSError:
            continue

    return ImageFont.load_default(), False

# =========================
# Sprite helpers (Twemoji fallback)
# =========================

SPRITE_DIR = Path(os.environ.get("GRIDWORLD_EMOJI_SPRITES", Path.home() / ".local" / "share" / "gridworld-emoji"))

def _glyph_to_hex(glyph: str) -> str:
    # remove emoji VS16 to match sprite filenames
    cps = [f"{ord(ch):x}" for ch in glyph if ord(ch) not in (0xFE0F, 0xFE0E)]
    return "-".join(cps)

@lru_cache(maxsize=256)
def _load_sprite_for_glyph(glyph: str) -> Optional[Image.Image]:
    path = SPRITE_DIR / f"{_glyph_to_hex(glyph)}.png"
    if path.exists():
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            return None
    return None

# expose for envs.py
def get_sprite_for_glyph(glyph: str) -> Optional[Image.Image]:
    return _load_sprite_for_glyph(glyph)

# =========================
# Symbol resolution
# =========================

def _symbol_for(env, r, c):
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

    conv_dir = getattr(env, "conveyor_map", {}).get(pos)
    if conv_dir:
        return f"conveyor_{conv_dir}"

    for a, b in getattr(env, "portal_pairs", []):
        if pos in (a, b): return "portal"

    return "empty"

def _glyph_for(env, r, c) -> Optional[str]:
    key = _symbol_for(env, r, c)
    return SYMBOLS.get(key)

# =========================
# Frame rendering
# =========================

def _emoji_frame(rows: int,
                 cols: int,
                 cell_size: int,
                 padding: int,
                 symbols: Dict[Tuple[int, int], str],
                 agent: Optional[Tuple[int, int]] = None,
                 agent_glyph: str = "🤖") -> Image.Image:
    """
    Create a PIL.Image of a board, drawing emojis centered in each cell.
    symbols: dict mapping (r,c)->emoji glyph.
    """
    W = cols * cell_size + 2 * padding
    H = rows * cell_size + 2 * padding
    im = Image.new("RGBA", (W, H), (255, 255, 255, 0))
    draw = ImageDraw.Draw(im)

    # grid
    for r in range(rows + 1):
        y = padding + r * cell_size
        draw.line([(padding, y), (padding + cols * cell_size, y)], fill=(180, 180, 180, 255), width=1)
    for c in range(cols + 1):
        x = padding + c * cell_size
        draw.line([(x, padding), (x, padding + rows * cell_size)], fill=(180, 180, 180, 255), width=1)

    # choose text font once
    font, is_color = _resolve_font(int(cell_size * 0.8))

    def draw_centered_glyph(glyph: str, rc: Tuple[int, int]):
        r, c = rc
        if not glyph:
            return
        x0 = padding + c * cell_size
        y0 = padding + r * cell_size
        cx = x0 + cell_size / 2
        cy = y0 + cell_size / 2

        # Try sprite first
        spr = get_sprite_for_glyph(glyph)
        if spr is not None:
            # keep aspect, fit into ~90% of cell
            target = int(cell_size * 0.9)
            if spr.width != target:
                spr = spr.resize((target, target), Image.LANCZOS)
            im.alpha_composite(spr, (int(cx - spr.width/2), int(cy - spr.height/2)))
            return

        # Fallback to font-rendered emoji/text
        g = glyph  # keep VS-16; color fonts benefit from it
        l, t, rbb, bbb = draw.textbbox((0, 0), g, font=font, embedded_color=is_color)
        w, h = rbb - l, bbb - t
        draw.text((cx - w / 2 - l, cy - h / 2 - t), g, font=font, embedded_color=is_color)

    # draw tiles
    for (r, c), glyph in symbols.items():
        draw_centered_glyph(glyph, (r, c))

    # draw agent last
    if agent is not None:
        draw_centered_glyph(agent_glyph, agent)

    return im

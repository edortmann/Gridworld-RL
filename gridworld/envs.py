from ._render import SYMBOLS, _emoji_frame, _parse_resolution
import ipywidgets as widgets, numpy as np, sys, io, random
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from ._render import _glyph_for


class InteractiveGridEnv:
    """
    Interaktive, teilweise beobachtbare Felder-Umgebung
    """
    def __init__(self, rows=6, cols=6, pit_frac=0.10, ice_frac=0.15, bumper_frac=0.10, reveal_full=False,
                 init_new_canvas=True, seed=None):
        if seed is not None:
            random.seed(seed)

        self.rows = rows
        self.cols = cols

        self.start_pos = (0, 0)
        # Zielposition zufällig wählen
        cells = [(r, c) for r in range(self.rows) for c in range(self.cols) if (r, c) != self.start_pos]
        self.goal_pos = random.choice(cells)

        self.agent_pos = self.start_pos
        self.visited = set([self.start_pos])

        # Canvas‑Objekt für die Visualisierung
        if init_new_canvas:
            self.cell_size = 25
            self.canvas = widgets.Image(format='png', layout={'width': '25%'})

        self.pit_frac = pit_frac
        self.ice_frac = ice_frac
        self.bumper_frac = bumper_frac

        self.reveal_full = reveal_full
        self.done = False
        self.last_event = None  # "goal" | "pit" | None

        # ----- verteile Feldervariationen -------------------------------------------------
        self.tile_map = {}  # (r,c) -> {"ice","bumper","pit"}
        pool = [p for p in cells if p != self.goal_pos]
        random.shuffle(pool)

        def take(frac):
            n = int(frac * len(pool))
            picked, rest = pool[:n], pool[n:]
            return picked, rest

        pits, pool = take(pit_frac)
        ice, pool = take(ice_frac)
        bumpers, pool = take(bumper_frac)

        self.tile_map.update({p: "pit" for p in pits})
        self.tile_map.update({p: "ice" for p in ice})
        self.tile_map.update({p: "bumper" for p in bumpers})

    # ---------------------------------------------------------------------------
    # Hilfsfunktionen
    # ---------------------------------------------------------------------------
    def _move(self, direction):
        r, c = self.agent_pos
        if direction == "Oben":
            r = max(r - 1, 0)
        elif direction == "Unten":
            r = min(r + 1, self.rows - 1)
        elif direction == "Links":
            c = max(c - 1, 0)
        elif direction == "Rechts":
            c = min(c + 1, self.cols - 1)
        self.agent_pos = (r, c)
        self.visited.add(self.agent_pos)

    def _propagate_effects(self, incoming_dir):
        """
        Eis-/Abpralleffekte anwenden, bis kein neuer Effekt mehr auftritt oder der Agent Ziel/Grube oder den Spielfeldrand erreicht.
        """
        while not self.done:
            # zuerst prüfen, ob das Ziel erreicht wurde
            if self.agent_pos == self.goal_pos:
                self.done = True
                self.last_event = "goal"
                return

            tile = self.tile_map.get(self.agent_pos)

            if tile == "pit":
                self.done = True
                self.last_event = "pit"
                return

            if tile == "ice" and random.random() < 0.5:
                slip_dir = random.choice(["Oben", "Unten", "Links", "Rechts"])
                self._move(slip_dir)
                # self.visited.add(self.agent_pos)
                incoming_dir = slip_dir
                continue  # Schleife fortführen, um potentiell neuen Feldeffekt zu evaluieren

            if tile == "bumper":
                opposite = {"Oben": "Unten", "Unten": "Oben", "Links": "Rechts", "Rechts": "Links"}[incoming_dir]
                for _ in range(3):
                    self._move(opposite)
                    # self.visited.add(self.agent_pos)

                    # Frühzeitige Abbruchprüfung bei jedem Abpraller
                    if self.agent_pos == self.goal_pos:
                        self.done = True
                        self.last_event = "goal"
                        return
                    if self.tile_map.get(self.agent_pos) == "pit":
                        self.done = True
                        self.last_event = "pit"
                        return
                incoming_dir = opposite
                continue  # Schleife fortführen, um potentiell neuen Feldeffekt zu evaluieren

            return

    # ---------------------------------------------------------------------------
    # RL functions
    # ---------------------------------------------------------------------------
    def restart_agent(self):
        """
        Setzt den Agenten auf die Startposition zurück und verdeckt alle gesehenen Felder.
        """
        self.agent_pos = self.start_pos
        self.visited = set([self.start_pos])
        self.done = False
        self.last_event = None
        self.render()

    def full_reset(self):
        """
        Ändert die Umgebung zu einer zufälligen neuen Umgebung und setzt den Agenten zurück.
        """
        self.__init__(rows=self.rows, cols=self.cols, pit_frac=self.pit_frac, ice_frac=self.ice_frac,
                      bumper_frac=self.bumper_frac, init_new_canvas=False)
        self.render()

    def step(self, action):
        if self.done:
            return self.agent_pos, True

        # Hauptbewegungsschritt
        self._move(action)
        # self.visited.add(self.agent_pos)

        # Kaskaden-Logik
        self._propagate_effects(action)

        self.render()
        return self.agent_pos, self.done

    # ---------------------------------------------------------------------------
    # Render-Funktionen
    # ---------------------------------------------------------------------------
    def render(self):
        cs, R, C = self.cell_size, self.rows, self.cols
        W, H = C * cs, R * cs
        img = Image.new("RGBA", (W, H), "white")
        draw = ImageDraw.Draw(img)

        # wähle colour-emoji font basierend auf Betriebssystem
        if sys.platform.startswith("win"):
            font_path = Path(r"C:\Windows\Fonts\seguiemj.ttf")
        elif sys.platform.startswith("linux"):
            font_path = Path("/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf")
        else:
            raise OSError("add a colour-emoji font path for your OS")
        font = ImageFont.truetype(str(font_path), int(cs * 0.8))

        # Hilfsfunktion, um Emojis zentriert in Feldern zu zeichnen
        def _draw_centered(glyph, cx, cy):
            g = glyph.replace("\uFE0F", "")
            l, t, rbb, bbb = draw.textbbox((0, 0), g, font=font, embedded_color=True)
            w, h = rbb - l, bbb - t
            draw.text((cx - w / 2 - l, cy - h / 2 - t), g, font=font, embedded_color=True)

        # zeichne Hintergrundfarben der Felder
        for r in range(R):
            for c in range(C):
                x0, y0, x1, y1 = c * cs, r * cs, (c + 1) * cs - 1, (r + 1) * cs - 1
                if (not self.reveal_full) and ((r, c) not in self.visited):
                    draw.rectangle([x0, y0, x1, y1], fill="#D3D3D3")
                else:
                    draw.rectangle([x0, y0, x1, y1], fill="white")

        # zeichne Emojis
        for r in range(R):
            for c in range(C):
                key = ("goal" if (r, c) == self.goal_pos else self.tile_map.get((r, c)))
                g = SYMBOLS.get(key)
                if g and ((self.reveal_full) or ((r, c) in self.visited)):
                    _draw_centered(g, c * cs + cs / 2, r * cs + cs / 2)
        ar, ac = self.agent_pos
        _draw_centered(SYMBOLS["agent"], ac * cs + cs / 2, ar * cs + cs / 2)

        # zeichne Felderränder
        for r in range(R + 1):
            y = min(r * cs, H - 1)
            draw.line([(0, y), (W - 1, y)], fill="grey")
        for c in range(C + 1):
            x = min(c * cs, W - 1)
            draw.line([(x, 0), (x, H - 1)], fill="grey")

        # flush to widgets.Image
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        self.canvas.value = buf.getvalue()


class LargeGridEnv:
    """
    Eine Felder-Umgebung mit speziellen Feldervarianten:
    - Eisfeld 🧊: 50 % Chance, nach dem eigentlichen Zug zufällig wegzurutschen.
    - Abpraller 🔴: Betritt der Agent das Feld, wird er drei Felder in die Richtung zurückgeschleudert, aus der er kam.
    - Grube 🕳️: Die Episode endet sofort mit einer Strafe.
    - Ziel 🚩: Die Episode endet mit einer Belohnung.
    """
    def __init__(self, rows=6, cols=6, ice_positions=[(2, 2), (3, 4)], bumper_positions=[(1, 4)],
                 pit_positions=[(4, 1)], goal_position=(5, 5),
                 reward_goal=10.0, reward_pit=-10.0, reward_step=-0.1, resolution="720p"):
        self.rows = rows
        self.cols = cols
        self.ice_positions = set(ice_positions)
        self.bumper_positions = set(bumper_positions)
        self.pit_positions = set(pit_positions)

        self.start_pos = (0, 0)
        self.goal_pos = goal_position

        self.reward_goal = reward_goal
        self.reward_pit = reward_pit
        self.reward_step = reward_step

        # self.action_map = {
        #    0: (-1, 0), # up
        #    1: (1, 0),  # down
        #    2: (0, -1), # left
        #    3: (0, 1)   # right
        # }
        self.action_map = {
            0: "up",
            1: "down",
            2: "left",
            3: "right"
        }

        self.rng = np.random.default_rng()

        self.agent_pos = (0, 0)
        self.visited = set([self.agent_pos])
        self.done = False

        self.tile_map = {}  # (r,c) -> {"ice","bumper","pit"}
        self.tile_map.update({p: "pit" for p in pit_positions})
        self.tile_map.update({p: "ice" for p in ice_positions})
        self.tile_map.update({p: "bumper" for p in bumper_positions})

        self.cell_size = 25
        # ───────── Fenster‑, Zellen‑ und Randgrößen bestimmen ───────────────
        target = _parse_resolution(resolution)

        if target is None:
            self.cell_size = 25
            self.frame_w = cols * self.cell_size
            self.frame_h = rows * self.cell_size
        else:
            self.frame_w, self.frame_h = target  # e.g. (1280, 720)
            self.cell_size = min(self.frame_w // cols, self.frame_h // rows)
            if self.cell_size == 0:
                raise ValueError("Grid ist zu groß für ausgewählte Auflösung.")

        # derived geometry
        grid_w, grid_h = cols * self.cell_size, rows * self.cell_size
        self.offset_x = (self.frame_w - grid_w) // 2  # ≥ 0 (letter-box)
        self.offset_y = (self.frame_h - grid_h) // 2

    # ---------------------------------------------------------------------------
    # Hilfsfunktionen
    # ---------------------------------------------------------------------------
    def to_index(self, row, col):
        """
        Wandel (row, col) in einen einzelnen Integer Index um.
        """
        return row * self.cols + col

    def from_index(self, index):
        """
        Inverse von to_index: gegeben einen Integer Index, gebe (row, col) zurück.
        """
        return (index // self.cols, index % self.cols)

    def _move(self, direction):
        r, c = self.agent_pos
        if direction == "up":
            r = max(r - 1, 0)
        elif direction == "down":
            r = min(r + 1, self.rows - 1)
        elif direction == "left":
            c = max(c - 1, 0)
        elif direction == "right":
            c = min(c + 1, self.cols - 1)
        self.agent_pos = (r, c)
        self.visited.add(self.agent_pos)

    def _propagate_effects(self, incoming_dir):
        """
        Eis-/Abpralleffekte anwenden, bis kein neuer Effekt mehr auftritt oder der Agent Ziel/Grube oder den Spielfeldrand erreicht.
        """
        while not self.done:
            # zuerst prüfen, ob das Ziel erreicht wurde
            if self.agent_pos == self.goal_pos:
                self.done = True
                # self.last_event = "goal"
                return

            tile = self.tile_map.get(self.agent_pos)

            if tile == "pit":
                self.done = True
                # self.last_event = "pit"
                return

            if tile == "ice" and random.random() < 0.5:
                slip_dir = random.choice(["up", "down", "left", "right"])
                self._move(slip_dir)
                # self.visited.add(self.agent_pos)
                incoming_dir = slip_dir
                continue

            if tile == "bumper":
                opposite = {"up": "down", "down": "up", "left": "right", "right": "left"}[incoming_dir]
                for _ in range(3):
                    self._move(opposite)
                    # self.visited.add(self.agent_pos)

                    # Frühzeitige Abbruchprüfung bei jedem Abpraller
                    if self.agent_pos == self.goal_pos:
                        self.done = True
                        # self.last_event = "goal"
                        return
                    if self.tile_map.get(self.agent_pos) == "pit":
                        self.done = True
                        # self.last_event = "pit"
                        return
                incoming_dir = opposite
                continue

            return

    # ---------------------------------------------------------------------------
    # Reinforcement Learning Funktionen
    # ---------------------------------------------------------------------------
    def reset(self):
        """
        Starte immer in der links oberen Ecke.
        """
        self.agent_pos = self.start_pos
        self.visited = set([self.agent_pos])
        self.done = False
        return self.to_index(*self.agent_pos)

    def step(self, action):
        """
        Gehe einen Schritt in der Umgebung anhand der gegebenen Aktion (0..3).
        """
        if self.done:
            return self.to_index(*self.agent_pos), 0.0, True

        # Hauptbewegungsschritt
        self._move(self.action_map[action])
        # self.visited.add(self.agent_pos)

        # Kaskaden-Logik
        self._propagate_effects(self.action_map[action])

        # berechne Belohnung
        tile = self.tile_map.get(self.agent_pos)
        if self.agent_pos == self.goal_pos:
            reward = self.reward_goal
        elif tile == "pit":
            reward = self.reward_pit
        else:
            reward = self.reward_step

        # self.render()
        return self.to_index(*self.agent_pos), reward, self.done

    # ---------------------------------------------------------------------------
    # Render-Funktionen
    # ---------------------------------------------------------------------------
    def _make_frame(self, *, with_agent=True):
        """
        Pillow image of the current board.
        `with_agent=False` lets you render a background-only frame.
        """
        padding_size = 2  # for padding at borders
        symbols = {
            (r, c): _glyph_for(self, r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if _glyph_for(self, r, c) is not None
        }
        agent = self.agent_pos if with_agent else None
        return _emoji_frame(self.rows,
                            self.cols,
                            self.cell_size,
                            padding_size,
                            symbols,
                            agent)

    def render(self, pos):
        """
        Rendern der aktuellen Position des Agenten in der Umgebung.
        """
        self.agent_pos = pos
        return np.asarray(self._make_frame())[:, :, :3]


class ExtendedGridEnv(LargeGridEnv):
    """
    Erweiterung des bestehenden LargeGridEnv, die zusätzliche Feldervarianten hinzufügt.
    """
    # Richtungs‑Hilfsfunktion
    DIRS = {
        "U": (-1, 0),
        "D": (1, 0),
        "L": (0, -1),
        "R": (0, 1)
    }

    def __init__(self,
                 rows=6, cols=6,
                 # originale Felder
                 ice_positions=None,
                 bumper_positions=None,
                 pit_positions=None,
                 # neue Felder
                 wall_positions=None,
                 sticky_positions=None,
                 conveyor_map=None,  # dict (row,col)->"U/D/L/R"
                 trampoline_positions=None,
                 wind_positions=None,
                 portal_pairs=None,  # list[((r1,c1),(r2,c2))]
                 collapse_positions=None,
                 toll_positions=None,
                 battery_positions=None,
                 gem_positions=None,
                 # Belohnungen
                 reward_goal=10.0,
                 reward_pit=-10.0,
                 reward_step=-0.1,
                 reward_wall=-0.5,
                 reward_sticky=-1.0,
                 reward_trampoline=1.0,
                 reward_toll=-3.0,
                 battery_required=False,
                 goal_position=None,
                 rng_seed=None):

        # Elternklasse mit entsprechenden Argumenten aufrufen
        super().__init__(
            rows=rows, cols=cols,
            ice_positions=ice_positions or [],
            bumper_positions=bumper_positions or [],
            pit_positions=pit_positions or [],
            goal_position=goal_position or (rows - 1, cols - 1),
            reward_goal=reward_goal,
            reward_pit=reward_pit,
            reward_step=reward_step
        )

        self.action_map = {
            0: (-1, 0),  # oben
            1: (1, 0),  # unten
            2: (0, -1),  # links
            3: (0, 1)  # rechts
        }

        # speichere neue Felder
        self.wall_positions = set(wall_positions or [])
        self.sticky_positions = set(sticky_positions or [])
        self.conveyor_map = {tuple(k): v for k, v in (conveyor_map or {}).items()}
        self.trampoline_positions = set(trampoline_positions or [])
        self.wind_positions = set(wind_positions or [])
        self.portal_lookup = {}
        if portal_pairs:
            for a, b in portal_pairs:
                self.portal_lookup[tuple(a)] = tuple(b)
                self.portal_lookup[tuple(b)] = tuple(a)
        self.collapse_positions = set(collapse_positions or [])
        self.already_collapsed = set()
        self.toll_positions = set(toll_positions or [])
        self.battery_positions = set(battery_positions or [])
        self.gem_positions = set(gem_positions or [])

        self.reward_wall = reward_wall
        self.reward_sticky = reward_sticky
        self.reward_trampoline = reward_trampoline
        self.reward_toll = reward_toll

        self.battery_required = battery_required
        self.has_battery = False

        # Windrichtung wird pro Episode neu bestimmt
        self.rng = np.random.default_rng(rng_seed)
        self.wind_dir_idx = self.rng.integers(0, 4)
        self.skip_turns = 0
        self.step_count = 0

        # Originalpositionen von Batterien, Edelsteinen und Einsturzfeldern für den Reset speichern
        self.battery_positions_original = self.battery_positions.copy()
        self.gem_positions_original = self.gem_positions.copy()
        self.collapse_positions_original = self.collapse_positions.copy()

    # ──────────────────────────────────────────────────────────────── #
    # Hilfsfunkion
    def _in_bounds(self, r, c):
        return 0 <= r < self.rows and 0 <= c < self.cols

    # ──────────────────────────────────────────────────────────────── #
    def reset(self, display_canvas=False):
        # Reset der Elternklasse verwenden und Batterien, Edelsteine, Einsturzfelder aktualisieren
        self.has_battery = False
        self.battery_positions = self.battery_positions_original.copy()
        self.gem_positions = self.gem_positions_original.copy()
        self.already_collapsed.clear()
        self.collapse_positions = self.collapse_positions_original.copy()
        self.skip_turns = 0
        self.wind_dir_idx = self.rng.integers(0, 4)
        return super().reset()

    # ──────────────────────────────────────────────────────────────── #
    def check_proposed_pos(self, pos, dr=None, dc=None):
        """
        Lösen von Ketten von erzwungenen Bewegungen auf (Förderbänder, Wind, Trampoline, ...) und zurückgeben des letzten Feldes.
        Die Schleife endet, wenn eine Regel den Agenten auf demselben Feld hält, oder wenn er auf einem Feld landet, das keine neue Bewegungswirkung erzwingt.
        """
        cur_r, cur_c = pos
        cur_dr, cur_dc = dr, dc  # letzte Bewegungsrichtung - benötigt von Abpraller / Trampolin
        visited = set()  # Schleifenerkennung von Förderbändern, die einen Kreislauf bilden

        while True:
            cur_pos = (cur_r, cur_c)

            # 1. Felder, die die Bewegung sofort abbrechen
            if cur_pos in self.wall_positions:
                return self.agent_pos  # die ursprüngliche Bewegung rückgängig machen
            if cur_pos in self.portal_lookup:
                return self.portal_lookup[cur_pos]
            if cur_pos not in (
                    self.ice_positions
                    | self.bumper_positions
                    | set(self.conveyor_map)
                    | self.trampoline_positions
                    | self.wind_positions
            ):
                return cur_pos  # kein anderes Feld ändert die Position

            # 2. Schleifen erkennen (Wind am Umgebungsrand Richtung Wand, Förderband Richtung Wand, Zyklen, ...)
            if cur_pos in visited:
                return cur_pos  # bereits besucht → Stop
            visited.add(cur_pos)

            # 3. genau *eine* Bewegungsregel anwenden
            if cur_pos in self.ice_positions:
                if self.rng.random() < 0.5:
                    slip_action = self.rng.integers(0, 4)
                    cur_dr, cur_dc = self.action_map[slip_action]
                else:
                    return cur_pos  # kein Rutschen
            elif cur_pos in self.bumper_positions and cur_dr is not None:
                cur_dr, cur_dc = -cur_dr, -cur_dc
                cur_dr *= 3
                cur_dc *= 3
            elif cur_pos in self.conveyor_map:
                cur_dr, cur_dc = self.DIRS[self.conveyor_map[cur_pos]]
            elif cur_pos in self.trampoline_positions and cur_dr is not None:
                cur_dr *= 2
                cur_dc *= 2
            elif cur_pos in self.wind_positions:
                cur_dr, cur_dc = list(self.DIRS.values())[self.wind_dir_idx]
            else:
                return cur_pos  # Fall zur Absicherung

            # 4. Bewegung (mit Randbegrenzung)
            cur_r = np.clip(cur_r + cur_dr, 0, self.rows - 1)
            cur_c = np.clip(cur_c + cur_dc, 0, self.cols - 1)

    # ──────────────────────────────────────────────────────────────── #
    def step(self, action):
        self.step_count += 1

        # Umgang mit Klebrigem Schlamm
        if self.skip_turns > 0:
            self.skip_turns -= 1
            # keine Bewegung ausführen
            reward = self.reward_sticky
            done = False
            return self.to_index(*self.agent_pos), reward, done

        if self.done:
            return self.to_index(*self.agent_pos), 0.0, True

        dr, dc = self.action_map[action]
        next_r = np.clip(self.agent_pos[0] + dr, 0, self.rows - 1)
        next_c = np.clip(self.agent_pos[1] + dc, 0, self.cols - 1)
        proposed_pos = (next_r, next_c)
        final_pos = self.check_proposed_pos(proposed_pos, dr=dr, dc=dc)

        # Falls Agent auf Klebrigem Schlamm landet
        if final_pos in self.sticky_positions:
            self.skip_turns = 1

        # Update Agentenposition
        self.agent_pos = final_pos
        self.visited.add(final_pos)

        # Belohnung / Terminierungsflag
        reward = self.reward_step
        done = False

        # Grube / Einstürzender Boden
        if self.agent_pos in self.pit_positions or self.agent_pos in self.already_collapsed:
            reward = self.reward_pit
            done = True
        elif self.agent_pos in self.collapse_positions:
            self.already_collapsed.add(self.agent_pos)
            self.collapse_positions.remove(self.agent_pos)

        # Maut-Tor
        if self.agent_pos in self.toll_positions:
            reward += self.reward_toll

        # Trampolin-Belohnungsbonus
        if proposed_pos in self.trampoline_positions:
            reward += self.reward_trampoline

        # Batterie wird aufgesammelt
        if self.agent_pos in self.battery_positions:
            self.has_battery = True
            self.battery_positions.remove(self.agent_pos)

        # Zeit-abhängiges Juwel
        if self.agent_pos in self.gem_positions:
            bonus = 3 if self.step_count < 20 else -1
            reward += bonus
            self.gem_positions.remove(self.agent_pos)

        # Ziel
        if self.agent_pos == self.goal_pos:
            if not self.battery_required or self.has_battery:
                reward = self.reward_goal
                done = True

        self.done = done
        return self.to_index(*self.agent_pos), reward, done

    # ──────────────────────────────────────────────────────────────── #
    def render(self, pos):
        self.agent_pos = pos

        # Einstürzender Boden -> Symbol muss geändert werden
        if self.agent_pos in self.collapse_positions:
            self.already_collapsed.add(self.agent_pos)
            self.collapse_positions.remove(self.agent_pos)
        # Batterie aufgehoben -> Batterie nicht mehr anzeigen
        if self.agent_pos in self.battery_positions:
            self.battery_positions.remove(self.agent_pos)
        # Zeit-Juwel aufgehoben -> nicht mehr anzeigen
        if self.agent_pos in self.gem_positions:
            self.gem_positions.remove(self.agent_pos)

        return np.asarray(self._make_frame())[:, :, :3]
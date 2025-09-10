import numpy as np
import ipywidgets as widgets
from IPython.display import display
from PIL import Image
from contextlib import ExitStack
from .envs import InteractiveGridEnv, ExtendedGridEnv
from .qlearning import q_learning
from .vis import plot_q_learning_progress, show_q_heatmap, make_video_from_frames


# ───────────────────────────────────────────
#  SMALL “PLAYER” DEMO
# ───────────────────────────────────────────
def launch_player_demo(rows=5, cols=5, **env_kwargs):
    env = InteractiveGridEnv(rows=rows, cols=cols, **env_kwargs)

    # Knöpfe
    up_btn = widgets.Button(description="Oben", layout={'width': '60px'})
    down_btn = widgets.Button(description="Unten", layout={'width': '60px'})
    left_btn = widgets.Button(description="Links", layout={'width': '60px'})
    right_btn = widgets.Button(description="Rechts", layout={'width': '60px'})
    reset_btn = widgets.Button(description="Zurück zum Start", button_style="warning")
    reveal_btn = widgets.ToggleButton(value=False, description="Umgebung aufdecken")
    randomize_btn = widgets.Button(description="Neues Spiel", button_style="danger")

    # status message
    status = widgets.HTML(value="", layout={'height': '30px', 'margin': '4px 0 0 0'})

    def _toggle_moves(disable=True):
        """Aktiviert bzw. deaktiviert die Bewegungsschaltflächen."""
        for b in (up_btn, down_btn, left_btn, right_btn):
            b.disabled = disable

    output = widgets.Output()

    @output.capture(clear_output=True)
    def on_move(btn):
        if btn is reset_btn:
            env.restart_agent()
            status.value = ""
            _toggle_moves(False)
            display(ui)
            return

        if btn is randomize_btn:
            env.full_reset()
            status.value = ""
            reveal_btn.value = False
            _toggle_moves(False)
            display(ui)
            return

        action = btn.description
        _, done = env.step(action)

        if done:
            _toggle_moves(True)
            if env.last_event == "goal":
                status.value = "<b>Du hast das Ziel erreicht! Drücke auf \"Neues Spiel\", um in einer neuen zufälligen Umgebung zu starten.</b>"
            elif env.last_event == "pit":
                status.value = "<b>Du bist in eine Grube gefallen! Drücke auf \"Zurück zum Start\", um neu zu starten.</b>"
        display(ui)

    def on_reveal(change):
        env.reveal_full = change["new"]
        env.render()

    # Knopf-Callbacks verbinden
    for b in (up_btn, down_btn, left_btn, right_btn, reset_btn, randomize_btn):
        b.on_click(on_move)
    reveal_btn.observe(on_reveal, "value")

    # layout
    btn_row = widgets.HBox([left_btn, up_btn, down_btn, right_btn, reset_btn, reveal_btn, randomize_btn])
    ui = widgets.VBox([btn_row, env.canvas, status])

    env.render()
    display(ui)
    #return ui   # so callers can embed / style further


# ───────────────────────────────────────────
#  Hilfsfunktionen für großes Dashboard
# ───────────────────────────────────────────
def create_tile_selectors(rows, cols, preset, preset_configs):
    """
    Erstellt ein 2D-Gitter mit Dropdown-Widgets (eines pro Feld).
    Gibt dieses als Liste von Listen zurück, zusammen mit einer VBox, die diese visuell anordnet.
    """
    # get a safe tile_grid
    tg = preset_configs[preset]["tile_grid"]
    if not tg:  # None or empty list
        tg = [[""] * cols for _ in range(rows)]
    else:  # pad / crop if size differs
        tg = [
            [
                tg[r][c] if r < len(tg) and c < len(tg[r]) else "Empty"
                for c in range(cols)
            ]
            for r in range(rows)
        ]

    tile_types = ["", "Abpraller", "Batterie", "Einstürzender Boden", "Eis", "Förderband (links)", "Förderband (oben)",
                  "Förderband (rechts)", "Förderband (unten)", "Grube", "Klebriger Schlamm", "Mauer",
                  "Maut-Tor", "Portal", "Start", "Trampolin", "Wind", "Zeit-Juwel", "Ziel"]
    dd_layout = widgets.Layout(width='130px')  # erhöhte Breite, damit lange Namen nicht abgeschnitten werden

    grid_rows, selectors_2d = [], []
    for r in range(rows):
        row_selectors = [
            widgets.Dropdown(options=tile_types, value=tg[r][c], description='', layout=dd_layout)
            for c in range(cols)
        ]
        selectors_2d.append(row_selectors)
        grid_rows.append(widgets.HBox(row_selectors))
    return selectors_2d, widgets.VBox(grid_rows)


# ───────────────────────────────────────────
#  LARGE TRAINING DASHBOARD
# ───────────────────────────────────────────
def launch_training_lab():
    tile_selectors = []

    # -------------------------------------
    # Schieberegler für Umgebungsparameter
    # -------------------------------------
    # einheitlicher Stil, so dass alle Regler visuell angenehmer und besser aufeinander abgestimmt sind
    slider_style = {'description_width': '240px'}  # label column width
    slider_layout = widgets.Layout(width='540px')  # longer slider track
    box_layout = widgets.Layout(margin='5px 0')

    # Hilfsfunktion: Slider und Zahlenfeld nebeneinander, synchronisiert
    def _make_slider_with_text(*, is_int, **kwargs):
        Sldr = widgets.IntSlider if is_int else widgets.FloatSlider
        Txt = widgets.IntText if is_int else widgets.FloatText
        s = Sldr(readout=False, continuous_update=True, style=slider_style, layout=slider_layout, **kwargs)
        t = Txt(step=kwargs.get("step", 1), layout=widgets.Layout(width='100px'))
        widgets.link((s, 'value'), (t, 'value'))  # two-way binding
        return s, t, widgets.HBox([s, t])

    # Widgets definieren, um die Umgebung anzupassen
    # ---- basic grid size ------------------------------------------------
    rows_widget, _, rows_row = _make_slider_with_text(is_int=True, value=5, min=4, max=10, step=1,
                                                   description='Grid Reihen')
    cols_widget, _, cols_row = _make_slider_with_text(is_int=True, value=5, min=4, max=10, step=1,
                                                   description='Grid Spalten')
    # ---- Ziel-/Grube-/Schritt-Belohnungen --------------------------------------
    reward_goal_widget, _, reward_goal_row = _make_slider_with_text(is_int=False, value=10.0, min=0.0, max=50.0, step=1.0,
                                                                 description='Ziel-Belohnung')
    reward_pit_widget, _, reward_pit_row = _make_slider_with_text(is_int=False, value=-10.0, min=-50.0, max=0.0, step=1.0,
                                                               description='Gruben-Belohnung')
    reward_step_widget, _, reward_step_row = _make_slider_with_text(is_int=False, value=-0.1, min=-10.0, max=10.0,
                                                                 step=0.1, description='Schritt-Belohnung')
    # ---- Felder-abhängige Belohnungen ------------------------------------------
    reward_wall_widget, _, reward_wall_row = _make_slider_with_text(is_int=False, value=-0.5, min=-5.0, max=0.0, step=0.1,
                                                                 description='Wand-Bestrafung')
    reward_sticky_widget, _, reward_sticky_row = _make_slider_with_text(is_int=False, value=-1.0, min=-10.0, max=0.0,
                                                                     step=0.1,
                                                                     description='Klebriger-Schlamm-Bestrafung')
    reward_trampoline_widget, _, reward_trampoline_row = _make_slider_with_text(is_int=False, value=0.1, min=0.0, max=5.0,
                                                                             step=0.1,
                                                                             description='Trampolin-Belohnung')
    reward_toll_widget, _, reward_toll_row = _make_slider_with_text(is_int=False, value=-3.0, min=-10.0, max=0.0, step=0.1,
                                                                 description='Maut-Tor-Bestrafung')
    # ---- Zeit-Juwel -----------------------------------------------------
    reward_jewel_pos_widget, _, reward_jewel_pos_row = _make_slider_with_text(is_int=False, value=3.0, min=0.0, max=10.0, step=0.1,
                                                                    description='Zeit-Juwel-Belohnung')
    reward_jewel_neg_widget, _, reward_jewel_neg_row = _make_slider_with_text(is_int=False, value=-1.0, min=-10.0, max=0.0, step=0.1,
                                                                    description='Zeit-Juwel-Bestrafung')
    jewel_steps_widget, _, jewel_steps_row = _make_slider_with_text(is_int=True, value=10, min=0, max=1000, step=1,
                                                                    description='Zeit-Juwel Schritte bis Bestrafung')
    # ---- simple flags / seed --------------------------------------------
    battery_required_widget = widgets.Checkbox(value=False, description='Agent braucht Batterie für Ziel', indent=True)
    rng_seed_widget, _, rng_seed_row = _make_slider_with_text(is_int=True, value=0, min=0, max=65535, step=1,
                                                           description='RNG Seed (0=random)')
    # ---- alle Umgebungswidgets sammeln ----------------------------------
    env_parameters_box = widgets.VBox([
        rows_row, cols_row,
        reward_goal_row, reward_pit_row, reward_step_row,
        reward_wall_row, reward_sticky_row,
        reward_trampoline_row, reward_toll_row,
        battery_required_widget,
        reward_jewel_pos_row, reward_jewel_neg_row, jewel_steps_row,
        rng_seed_row
    ], layout=box_layout)

    # -------------------------------------
    # Schieberegler für Agentenparameter
    # -------------------------------------
    alpha_widget, _, alpha_row = _make_slider_with_text(is_int=False, value=0.1, min=0.0, max=1.0, step=0.01, description=r'α (Lernrate)')
    gamma_widget, _, gamma_row = _make_slider_with_text(is_int=False, value=0.95, min=0.0, max=1.0, step=0.01, description=r'γ (Diskontierungsfaktor)')
    epsilon_widget, _, epsilon_row = _make_slider_with_text(is_int=False, value=0.1, min=0.0, max=1.0, step=0.01, description=r'ε (Exploration)')
    epsilon_decay_widget = widgets.Checkbox(value=False, description=r'ε-Annealing aktivieren', indent=True)
    epsilon_decay_interval_widget, epsilon_decay_interval_textfield, epsilon_decay_interval_row = _make_slider_with_text(is_int=True, value=20, min=1, max=1000, step=1, description=r'ε-Annealing Intervall (Epis.)')
    epsilon_decay_factor_widget, epsilon_decay_factor_textfield, epsilon_decay_factor_row = _make_slider_with_text(is_int=False, value=0.95, min=0.5, max=0.99, step=0.001, description=r'ε-Annealing Faktor')
    epsilon_min_widget, epsilon_min_textfield, epsilon_min_row = _make_slider_with_text(is_int=False, value=0.01, min=0.001, max=0.9, step=0.001, description=r'ε-Annealing untere Grenze für ε')
    num_episodes_widget, _, num_episodes_row = _make_slider_with_text(is_int=True, value=100, min=1, max=1000, step=10, description='Episoden')
    max_steps_widget, _, max_steps_row = _make_slider_with_text(is_int=True, value=100, min=10, max=1000, step=10, description='Max. Schritte pro Episode')
    record_interval_widget, _, record_interval_row = _make_slider_with_text(is_int=True, value=100, min=1, max=1000, step=10, description='Abstand Trainingsepisoden speichern')
    report_interval_widget, _, report_interval_row = _make_slider_with_text(is_int=True, value=20, min=10, max=100, step=10, description='Fenstergröße für Belohnungsdiagramm')

    agent_parameters_box = widgets.VBox([alpha_row, gamma_row, epsilon_row, epsilon_decay_widget,
                                         epsilon_decay_interval_row, epsilon_decay_factor_row, epsilon_min_row,
                                         num_episodes_row, max_steps_row, record_interval_row, report_interval_row],
                                        layout=box_layout)

    # ε-Annealing Intervall + Faktor widgets ausgrauen, solange die Checkbox nicht angekreuzt ist
    def _toggle_decay_widgets(change):
        on = change["new"]
        epsilon_decay_interval_widget.disabled = not on
        epsilon_decay_factor_widget.disabled = not on
        epsilon_min_widget.disabled = not on
        epsilon_decay_interval_textfield.disabled = not on
        epsilon_decay_factor_textfield.disabled = not on
        epsilon_min_textfield.disabled = not on

    epsilon_decay_widget.observe(_toggle_decay_widgets, names="value")
    _toggle_decay_widgets({"new": epsilon_decay_widget.value})

    # -------------------------------------
    # Schieberegler für Videoparameter
    # -------------------------------------
    fps_widget, _, fps_row = _make_slider_with_text(is_int=True, value=5, min=1, max=10, step=1, description=r'fps')

    video_parameters_box = widgets.VBox([fps_row], layout=box_layout)

    # -------------------------------------
    # Feldauswahl + Presets + Zurücksetzen
    # -------------------------------------
    #_widget_vars = {name: obj for name, obj in globals().items() if name.endswith("_widget") and hasattr(obj, "value")}
    _widget_vars = {name: obj for name, obj in locals().items() if name.endswith("_widget") and hasattr(obj, "value")}
    _default_values = {name: w.value for name, w in _widget_vars.items()}
    _default_tile_grid = [[""] * cols_widget.value for _ in range(rows_widget.value)]

    preset_configs = {
        "Default": {
            **_default_values,
            "tile_grid": _default_tile_grid,
        },
        "Warm-Up Playground (5×5) - sanfter Einstieg mit ein paar Hindernissen": {
            **_default_values,
            "rows_widget": 5, "cols_widget": 5,
            "num_episodes_widget": 400, "max_steps_widget": 120,
            "alpha_widget": 0.12, "epsilon_widget": 0.18,
            "reward_step_widget": -0.10, "reward_pit_widget": -12.0, "reward_wall_widget": -0.6,
            "tile_grid": [
                ["", "", "Mauer", "", ""],
                ["Eis", "", "Mauer", "Grube", ""],
                ["", "", "", "", ""],
                ["", "Grube", "", "", ""],
                ["", "", "", "", "Ziel"],
            ],
        },
        "Conveyor Workshop (6×6) - Förderbänder, Schlamm & Wind lehren Zwangsbewegungen": {
            **_default_values,
            "rows_widget": 6, "cols_widget": 6,
            "num_episodes_widget": 800, "max_steps_widget": 160,
            "alpha_widget": 0.15, "epsilon_widget": 0.30,
            "reward_step_widget": -0.05, "reward_sticky_widget": -1.0, "reward_trampoline_widget": 0.2,
            "reward_wall_widget": -1.0,
            "tile_grid": [
                ["", "Förderband (rechts)", "Förderband (rechts)", "Förderband (rechts)", "Förderband (unten)", ""],
                ["", "Klebriger Schlamm", "", "", "Förderband (unten)", ""],
                ["", "", "", "", "Förderband (unten)", ""],
                ["Trampolin", "", "Mauer", "Mauer", "Förderband (unten)", ""],
                ["", "", "", "", "Förderband (unten)", ""],
                ["", "", "", "", "", "Ziel"],
            ],
        },
        "Battery‑Portal Run (7×5) – Batterie einsammeln, Maut entrichten, Portale benutzen": {
            **_default_values,
            "rows_widget": 7, "cols_widget": 5,
            "battery_required_widget": True,
            "num_episodes_widget": 1100, "max_steps_widget": 180,
            "alpha_widget": 0.10, "epsilon_widget": 0.25,
            "reward_step_widget": -0.20, "reward_toll_widget": -3.0, "reward_wall_widget": -1.5,
            "tile_grid": [
                ["", "", "Portal", "Mauer", ""],
                ["", "Mauer", "", "Mauer", ""],
                ["", "Mauer", "", "Maut-Tor", ""],
                ["Förderband (unten)", "", "", "Mauer", ""],
                ["Portal", "Mauer", "", "Wind", ""],
                ["Batterie", "", "", "Mauer", ""],
                ["", "", "", "", "Ziel"],
            ],
        },
        "Collapsing Canyon (6×7) – verschwindende Böden und stürmische Schluchten": {
            **_default_values,
            "rows_widget": 6, "cols_widget": 7,
            "num_episodes_widget": 1400, "max_steps_widget": 200,
            "alpha_widget": 0.12, "epsilon_widget": 0.35,
            "reward_step_widget": -0.15, "reward_pit_widget": -15.0, "reward_wall_widget": -1.0,
            "tile_grid": [
                ["", "Wind", "", "", "", "Wind", ""],
                ["", "Einstürzender Boden", "", "Grube", "", "Einstürzender Boden", ""],
                ["", "Einstürzender Boden", "", "", "", "Einstürzender Boden", ""],
                ["", "Wind", "", "Grube", "", "Wind", ""],
                ["", "Trampolin", "", "", "", "", ""],
                ["", "", "", "", "", "", "Ziel"],
            ],
        },
        "Gem‑Bumper Maze (6×6) – Edelsteine sammeln, Abprallern und Mauern ausweichen": {
            **_default_values,
            "rows_widget": 6, "cols_widget": 6,
            "num_episodes_widget": 650, "max_steps_widget": 140,
            "alpha_widget": 0.11, "epsilon_widget": 0.22,
            "reward_step_widget": -0.08, "reward_wall_widget": -1.2,
            "reward_jewel_pos_widget": 5.0, "reward_jewel_neg_widget": -3.0, "jewel_steps_widget": 10,
            "tile_grid": [
                ["", "Mauer", "", "Abpraller", "", "Zeit-Juwel"],
                ["", "Mauer", "", "Klebriger Schlamm", "", ""],
                ["", "", "Förderband (oben)", "Förderband (links)", "Förderband (links)", ""],
                ["", "Mauer", "Mauer", "Mauer", "", ""],
                ["", "Mauer", "", "", "", ""],
                ["Zeit-Juwel", "Mauer", "", "", "", "Ziel"],
            ],
        },
    }

    # Helfer, der ein Preset‑Dictionary auf die Widgets anwendet
    def _apply_preset(cfg_name):
        cfg = preset_configs[cfg_name]
        #rows_widget.unobserve(update_tile_grid, names='value')
        #cols_widget.unobserve(update_tile_grid, names='value')
        #preset_dropdown.unobserve(update_tile_grid, names='value')
        affected = [rows_widget, cols_widget, preset_dropdown] + list(_widget_vars.values())

        with ExitStack() as es:
            for w in affected:
                es.enter_context(w.hold_trait_notifications())

            for key, val in cfg.items():
                if key in _widget_vars:
                    _widget_vars[key].value = val

            # bring the dropdown into sync *inside* the hold-block
            preset_dropdown.value = cfg_name

        # alle Schieberegler / Skalar-Widgets aktualisieren
        #try:
        #    for k, v in cfg.items():
        #        if k in _widget_vars:
        #            _widget_vars[k].value = v
        #    preset_dropdown.value = cfg_name
        #finally:
        #    rows_widget.observe(update_tile_grid, names='value')
        #    cols_widget.observe(update_tile_grid, names='value')
        #    preset_dropdown.observe(update_tile_grid, names='value')

        # Nach Ändern der Slider die Kachelmatrix neu aufbauen
        update_tile_grid(None)

    # Funktion, um momentane Umgebung und Parameterwerte als neues Preset zu speichern
    def _save_current_as_preset(_):
        cfg = {name: w.value for name, w in _widget_vars.items()}

        # momentane Umgebung speichern
        rows, cols = rows_widget.value, cols_widget.value
        cfg["tile_grid"] = [
            [tile_selectors[r][c].value for c in range(cols)]
            for r in range(rows)
        ]

        # finde passende Nummer zum Abspeichern
        custom_ids = [
            int(key.split("Vorlage ")[1])
            for key in preset_configs
            if key.startswith("Vorlage ") and key.split("Vorlage ")[1].isdigit()
        ]
        next_id = max(custom_ids, default=0) + 1
        preset_name = f"Vorlage {next_id}"

        # speichere Preset und aktualisiere Liste
        preset_configs[preset_name] = cfg
        preset_dropdown.options = list(preset_configs.keys())
        preset_dropdown.value = preset_name

    preset_dropdown = widgets.Dropdown(options=list(preset_configs.keys()), value="Default", description="Vorlage", style={'description_width': 'initial'})
    apply_btn = widgets.Button(description="Vorlage anwenden", button_style="success", tooltip="Ausgewählte Vorlage anwenden")
    reset_btn = widgets.Button(description="Alles zurücksetzen", button_style="warning", tooltip="Alle Werte auf Standard zurücksetzen")
    save_btn = widgets.Button(description="Eigene Vorlage speichern", tooltip="Aktuelle Einstellungen als neue Vorlage sichern", icon="save", layout=widgets.Layout(width='300px'))

    apply_btn.on_click(lambda b: _apply_preset(preset_dropdown.value))
    reset_btn.on_click(lambda b: _apply_preset("Default"))
    save_btn.on_click(_save_current_as_preset)

    preset_box = widgets.HBox([preset_dropdown, apply_btn, reset_btn, save_btn])

    #tile_selectors = []  # 2D list (rows x cols) of Dropdown widgets
    tile_grid_container = widgets.VBox()

    def update_tile_grid(_):
        """
        Erstellt das 2D-Raster der Kachelselektoren neu, wenn sich Zeile/Spalte/Preset ändern.
        """
        nonlocal tile_selectors

        rows = rows_widget.value
        cols = cols_widget.value
        preset = preset_dropdown.value

        # Tile‑Dropdowns neu aufbauen
        #global tile_selectors
        #tile_selectors, grid_vbox = create_tile_selectors(rows, cols, preset)
        tile_selectors, grid_vbox = create_tile_selectors(rows, cols, preset, preset_configs)

        tile_grid_container.children = [grid_vbox]

    # Änderungen an Zeilen/Spalten beobachten, um die Kachelmatrix neu aufzubauen
    rows_widget.observe(update_tile_grid, names='value')
    cols_widget.observe(update_tile_grid, names='value')
    preset_dropdown.observe(update_tile_grid, names='value')

    # Die Kachelmatrix einmalig beim Start initialisieren
    update_tile_grid(None)

    # -------------------------------------
    # Knöpfe + Output
    # -------------------------------------
    # Schaltfläche zum Starten des Trainings mit gewählten Parametern
    train_button = widgets.Button(description='Trainiere Q-Learning-Agenten mit ausgewählten Parameter-Werten 🚀',
                                  layout=widgets.Layout(width='500px'))

    # Knopf um Trainings Episoden abzuspielen
    replay_button = widgets.Button(description='Wiederhole Trainingsepisoden', layout=widgets.Layout(width='500px'))

    # Knopf um Test Episode abzuspielen
    test_button = widgets.Button(description='Testepisode mit ausgelerntem Agent', layout=widgets.Layout(width='500px'))

    # Anzeigebereich für das Training
    output1 = widgets.Output(layout={'border': '1px solid black', 'height': '550px', 'overflow': 'scroll'})

    # Anzeigebereich für Trainings‑Replays
    output2 = widgets.Output(layout={'border': '1px solid black', 'height': '800px', 'overflow': 'scroll'})

    # Anzeigebereich für Testepisode
    output3 = widgets.Output(layout={'border': '1px solid black', 'height': '800px', 'overflow': 'scroll'})

    # Gemeinsames Dictionary zwischen Schaltflächen
    training_data = {
        'env': None,
        'Q': None,
        'trajectories': None,
        'rewards_history': None
    }

    def train_agent(env_params, agent_params, training_data):
        """
        Erstellt die Umgebung und den Q-Learning-Agenten unter Verwendung der übergebenen Dictionaries.
        Führt dann das Training durch.
        """

        # Als Ziel wird das erste vom Benutzer gewählte „Goal“-Feld verwendet
        goal_positions = env_params['goal_positions']
        if len(goal_positions) == 0:
            # Falls kein Ziel gewählt wurde → Zelle unten rechts als Standard
            goal_pos = (env_params['rows'], env_params['cols'])
        else:
            goal_pos = goal_positions[-1]

        # Umgebung initialisieren
        large_env = ExtendedGridEnv(
            rows=env_params['rows'],
            cols=env_params['cols'],
            # tiles
            ice_positions=env_params['ice_positions'],
            bumper_positions=env_params['bumper_positions'],
            pit_positions=env_params['pit_positions'],
            wall_positions=env_params['wall_positions'],
            sticky_positions=env_params['sticky_positions'],
            conveyor_map=env_params['conveyor_map'],  # dict (row,col)->"U/D/L/R"
            trampoline_positions=env_params['trampoline_positions'],
            wind_positions=env_params['wind_positions'],
            portal_pairs=env_params['portal_pairs'],  # list[((r1,c1),(r2,c2))]
            collapse_positions=env_params['collapse_positions'],
            toll_positions=env_params['toll_positions'],
            battery_positions=env_params['battery_positions'],
            gem_positions=env_params['gem_positions'],
            # rewards
            reward_goal=env_params['reward_goal'],
            reward_pit=env_params['reward_pit'],
            reward_step=env_params['reward_step'],
            reward_wall=env_params['reward_wall'],
            reward_sticky=env_params['reward_sticky'],
            reward_trampoline=env_params['reward_trampoline'],
            reward_toll=env_params['reward_toll'],
            reward_jewel_pos=env_params['reward_jewel_pos'],
            reward_jewel_neg=env_params['reward_jewel_neg'],
            jewel_steps=env_params['jewel_steps'],
            battery_required=env_params['battery_required'],
            goal_position=goal_pos,
            rng_seed=env_params['rng_seed'],
        )

        large_env.start_pos = env_params['start_pos']
        large_env.agent_pos = env_params['start_pos']
        large_env.visited = {env_params['start_pos']}

        if agent_params['epsilon_decay']:
            decay_factor = agent_params['epsilon_decay_factor']
            decay_interval = agent_params['epsilon_decay_interval']
            epsilon_min = agent_params['epsilon_min']
        else:
            decay_factor = None
            decay_interval = 1
            epsilon_min = 0.01

        # Tabellarisches Q-Learning trainieren
        Q, stored_trajectories, rewards_history = q_learning(
            large_env,
            num_episodes=agent_params['num_episodes'],
            alpha=agent_params['alpha'],
            gamma=agent_params['gamma'],
            epsilon=agent_params['epsilon'],
            epsilon_decay_factor=decay_factor,
            epsilon_decay_interval=decay_interval,
            epsilon_min=epsilon_min,
            max_steps=agent_params['max_steps'],
            record_interval=agent_params['record_interval'],
            report_interval=agent_params['report_interval']
        )

        # Belohnungsfortschritt-Diagramm plotten
        plot_q_learning_progress(rewards_history, interval=agent_params['report_interval'],
                                 rolling_window=agent_params['report_interval'])

        show_q_heatmap(Q, large_env)

        # Referenzen für spätere Wiedergabe sichern
        training_data['env'] = large_env
        training_data['Q'] = Q
        training_data['trajectories'] = stored_trajectories
        training_data['rewards_history'] = rewards_history

    @output1.capture(clear_output=True)
    def on_train_button_clicked(_):

        rows = rows_widget.value
        cols = cols_widget.value

        # tile_selectors (die 2D‑Dropdowns) in Positionslisten umwandeln
        ice_positions = []
        bumper_positions = []
        wall_positions = []
        sticky_positions = []
        conveyor_map = {}
        trampoline_positions = []
        wind_positions = []
        portal_positions = []
        collapse_positions = []
        toll_positions = []
        battery_positions = []
        gem_positions = []
        pit_positions = []
        goal_positions = []
        start_pos = None

        #print(tile_selectors)

        for r in range(rows):
            for c in range(cols):
                tile_choice = tile_selectors[r][c].value
                if tile_choice == "Start":
                    if start_pos is not None:
                        print("⚠️  Mehrere Start-Felder gewählt – nehme das erste.")
                    else:
                        start_pos = (r, c)
                elif tile_choice == "Eis":
                    ice_positions.append((r, c))
                elif tile_choice == "Abpraller":
                    bumper_positions.append((r, c))
                elif tile_choice == "Mauer":
                    wall_positions.append((r, c))
                elif tile_choice == "Klebriger Schlamm":
                    sticky_positions.append((r, c))
                elif tile_choice == "Förderband (oben)":
                    conveyor_map[(r, c)] = "U"
                elif tile_choice == "Förderband (unten)":
                    conveyor_map[(r, c)] = "D"
                elif tile_choice == "Förderband (links)":
                    conveyor_map[(r, c)] = "L"
                elif tile_choice == "Förderband (rechts)":
                    conveyor_map[(r, c)] = "R"
                elif tile_choice == "Trampolin":
                    trampoline_positions.append((r, c))
                elif tile_choice == "Wind":
                    wind_positions.append((r, c))
                elif tile_choice == "Portal":
                    portal_positions.append((r, c))
                elif tile_choice == "Einstürzender Boden":
                    collapse_positions.append((r, c))
                elif tile_choice == "Maut-Tor":
                    toll_positions.append((r, c))
                elif tile_choice == "Batterie":
                    battery_positions.append((r, c))
                elif tile_choice == "Zeit-Juwel":
                    gem_positions.append((r, c))
                elif tile_choice == "Grube":
                    pit_positions.append((r, c))
                elif tile_choice == "Ziel":
                    goal_positions.append((r, c))

        if start_pos is None:
            start_pos = (0, 0)

        if len(goal_positions) == 0:
            goal_positions.append((rows - 1, cols - 1))

        portal_pairs = []
        if len(portal_positions) >= 2:
            portal_pairs.append((portal_positions[0], portal_positions[1]))

        # Einstellungen aus den Umgebungs‑Widgets auslesen
        env_params = {
            'rows': rows_widget.value,
            'cols': cols_widget.value,
            # Belohnungen
            'reward_goal': reward_goal_widget.value,
            'reward_pit': reward_pit_widget.value,
            'reward_step': reward_step_widget.value,
            'reward_wall': reward_wall_widget.value,
            'reward_sticky': reward_sticky_widget.value,
            'reward_trampoline': reward_trampoline_widget.value,
            'reward_toll': reward_toll_widget.value,
            'reward_jewel_pos':  reward_jewel_pos_widget.value,
            'reward_jewel_neg': reward_jewel_neg_widget.value,
            'jewel_steps': jewel_steps_widget.value,
            'battery_required': battery_required_widget.value,
            'rng_seed': (None if rng_seed_widget.value == 0 else rng_seed_widget.value),
            # Felder-Positionen
            'ice_positions': ice_positions,
            'bumper_positions': bumper_positions,
            'wall_positions': wall_positions,
            'sticky_positions': sticky_positions,
            'conveyor_map': conveyor_map,
            'trampoline_positions': trampoline_positions,
            'wind_positions': wind_positions,
            'portal_pairs': portal_pairs,
            'collapse_positions': collapse_positions,
            'toll_positions': toll_positions,
            'battery_positions': battery_positions,
            'gem_positions': gem_positions,
            'pit_positions': pit_positions,
            'goal_positions': goal_positions,
            'start_pos': start_pos,
        }

        # Einstellungen aus den Agent‑Widgets auslesen
        agent_params = {
            'alpha': alpha_widget.value,
            'gamma': gamma_widget.value,
            'epsilon': epsilon_widget.value,
            'epsilon_decay': epsilon_widget.value,
            'epsilon_decay_factor': epsilon_decay_factor_widget.value,
            'epsilon_decay_interval': epsilon_decay_interval_widget.value,
            'epsilon_min': epsilon_min_widget.value,
            'num_episodes': num_episodes_widget.value,
            'max_steps': max_steps_widget.value,
            'record_interval': record_interval_widget.value,
            'report_interval': report_interval_widget.value
        }

        # An die Trainingsfunktion übergeben
        train_agent(env_params, agent_params, training_data)
        print("Training completed.")

    @output2.capture(clear_output=True)
    def on_replay_button_clicked(_):
        env = training_data['env']
        trajectories = training_data['trajectories']

        global replay_training_canvases
        replay_training_canvases = {}

        if env is None or trajectories is None:
            print("Keine gespeicherten Trainingsdaten gefunden. Bitte erst trainieren.")
            return

        episodes = {}
        for ep, traj in trajectories.items():
            env.reset()
            ep_frames = [env.render(pos) for pos in traj]
            episodes[ep] = ep_frames

        im = Image.fromarray(episodes[0][0])
        im.save("grid.png")

        for ep, frames in episodes.items():
            print(f"=== Training Episode {ep} ===")
            video = make_video_from_frames(frames, fps=fps_widget.value)
            display(video)

        print("Training completed.")

    @output3.capture(clear_output=True)
    def on_test_button_clicked(_):
        env = training_data['env']
        agent = training_data['Q']

        if env is None or agent is None:
            print("Keine gespeicherten Trainingsdaten gefunden. Bitte erst trainieren.")
            return

        # Test‑Episode‑Trajektorie speichern
        state = env.reset()
        trajectory = [env.agent_pos]
        max_steps = max_steps_widget.value
        for _ in range(max_steps):
            # tie-breaking so the agent doesn’t always pick action 0
            q_row = agent[state]
            best = np.flatnonzero(q_row == q_row.max())
            action = int(np.random.choice(best))

            #action = np.argmax(agent[state])
            next_state, _, done = env.step(action)
            trajectory.append(env.agent_pos)
            state = next_state

            if done:
                break

        env.reset()
        test_ep_frames = [env.render(pos) for pos in trajectory]

        print(f"=== Test Episode ===")
        test_video = make_video_from_frames(test_ep_frames, fps=fps_widget.value)
        display(test_video)

    # Callbacks an Schaltflächen anhängen
    train_button.on_click(on_train_button_clicked)
    replay_button.on_click(on_replay_button_clicked)
    test_button.on_click(on_test_button_clicked)

    # Boxen in ein Tab-Widget einbinden
    tab = widgets.Tab(children=[env_parameters_box, tile_grid_container, agent_parameters_box, video_parameters_box])
    tab.set_title(0, "Umgebung")
    tab.set_title(1, "Felder")
    tab.set_title(2, "Agent")
    tab.set_title(3, "Video-Generierung")

    # Tabs, Schaltflächen und Ausgabebereich stapeln
    lab = widgets.VBox([
        tab,
        preset_box,
        train_button,
        output1,
        replay_button,
        output2,
        test_button,
        output3,
    ])
    display(lab)
    #return lab

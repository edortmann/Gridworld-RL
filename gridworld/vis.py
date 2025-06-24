import numpy as np
import plotly.graph_objs as go
import matplotlib.pyplot as plt
import ipywidgets as widgets
import os, tempfile, time
from moviepy import ImageSequenceClip
from IPython.display import display, clear_output, Video


def plot_q_learning_progress(rewards, interval=50, rolling_window=50):
    """
    Zeichnet zwei Kurven:
      • Block Durchschnitt alle `interval` Episoden
      • Gleitender Durchschnitt mit `rolling_window` Größe über Episoden
    """
    r = np.asarray(rewards, dtype=float)
    n_ep = r.size
    if n_ep == 0:
        return

    # ---------- Block Durchschnitt -------------------------------------
    cut_points  = np.arange(interval, n_ep + 1, interval)
    block_means = [r[i-interval:i].mean() for i in cut_points]

    # ---------- gleitender Durchschnitt --------------------------------
    if n_ep >= rolling_window:
        kernel = np.ones(rolling_window) / rolling_window
        roll_vals = np.convolve(r, kernel, mode="valid")
        roll_x    = np.arange(rolling_window, n_ep + 1)
    else:
        roll_vals, roll_x = np.array([]), np.array([])

    # ---------- zeichnen des Diagramms ----------------------------------
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=cut_points, y=block_means, mode="lines+markers", name=f"Block Durchschnitt ({interval})"))
    if roll_vals.size:
        fig.add_trace(go.Scatter(x=roll_x, y=roll_vals, mode="lines", name=f"Gleitender Durchschnitt ({rolling_window})"))
    fig.update_layout(
        width=700,
        height=500,
        title="Q-Learning Trainingsfortschritt",
        xaxis_title="Episode",
        yaxis_title="Durchschnittliche Belohnung",
        template="plotly_white",
        xaxis=dict(
            tick0=interval,
            dtick=interval
        )
    )
    fig.show()


def show_q_heatmap(Q, env):
    """
    Visualisiert (1) den höchsten Q-Wert pro Zustand als Farbfeld
    und (2) die aktuell bevorzugte Aktion als Richtungspfeil.
    """
    qs = Q.max(axis=1).reshape(env.rows, env.cols)  # Matrix mit dem höchsten Q-Wert pro Zustand
    policy = Q.argmax(axis=1).reshape(env.rows, env.cols)  # Matrix mit dem Index der besten Aktion pro Zustand

    fig, ax = plt.subplots(figsize=(5, 5))
    im = ax.imshow(qs, cmap="viridis", origin="upper")

    # Pfeile in jede Zelle zeichnen
    for r in range(env.rows):
        for c in range(env.cols):
            arrow = "↑↓←→"[policy[r, c]]
            ax.text(c, r, arrow, ha="center", va="center", color="white", fontsize=14)

    plt.colorbar(im, ax=ax, label="max Q-Wert")
    ax.set_title("Gelerntes Q-Wert- & Policy-Raster")
    plt.savefig("heatmap.png")
    plt.show()


def make_video_from_frames(frames, filename=None, fps=25):
    """
    Diese Funktion nimmt eine Liste von Frames und macht daraus ein Video, das im Browser angezeigt werden kann.
    """
    clip = ImageSequenceClip(frames, fps=fps)

    use_tmpfile = filename is None

    if use_tmpfile:
        with tempfile.NamedTemporaryFile(mode='w+b', suffix='.mp4', delete=False) as f:
            filename = f.name
    else:
        folder = os.path.dirname(filename)
        os.makedirs(folder, exist_ok=True)

    clip.write_videofile(filename, logger=None, preset='ultrafast', threads=1)
    with open(filename, mode='rb') as f:
        video_embd = Video(f.read(), html_attributes='controls autoplay', mimetype='video/mp4', embed=use_tmpfile)

    if use_tmpfile:
        os.unlink(filename)

    video_embd.reload()

    return video_embd


def show_training_videos(trajectories, env, fps=2):
    # Schritte jeder gespeicherten Episode als Frames speichern
    episodes = {}
    for ep, traj in trajectories.items():
        env.reset()
        ep_frames = [env.render(pos) for pos in traj]
        episodes[ep] = ep_frames
        time.sleep(0.1)

    # Videos aus den Frames erstellen und darstellen
    training_output = widgets.Output(layout={'border': '1px solid black', 'height': '800px', 'overflow': 'scroll'})
    with training_output:
        clear_output(wait=True)
        for ep, frames in episodes.items():
            print(f"=== Training Episode {ep} ===")
            video = make_video_from_frames(frames, fps=fps)
            display(video)
    display(training_output)


def show_test_video(Q, env, fps=2):
    # Test‑Episode‑Trajektorie speichern
    state = env.reset()
    trajectory = [env.agent_pos]
    done = False
    while not done:
        action = np.argmax(Q[state])
        next_state, _, done = env.step(action)
        trajectory.append(env.agent_pos)
        state = next_state

    # Schritte der Test-Episode als Frames speichern
    env.reset()
    test_ep_frames = [env.render(pos) for pos in trajectory]

    # Test-Video aus Frames erstellen und darstellen
    test_output = widgets.Output(layout={'border': '1px solid black', 'height': '800px', 'overflow': 'scroll'})
    with test_output:
        clear_output(wait=True)
        print(f"=== Test Episode ===")
        test_video = make_video_from_frames(test_ep_frames, fps=fps)
        display(test_video)
    display(test_output)
# Gridworld-RL

An interactive **Gridworld** for teaching **Q-Learning**. Explore tile mechanics, tune hyper-parameters, and watch the agent learn.

---

## Choose the right notebook

- **Windows → `gridworld.ipynb`**
- **Linux   → `gridworld_linux.ipynb`**

For Linux users who want a one-command setup and launch:

- **Script to automatically setup (for Linux) → `run_gridworld.sh`**

---

## Features

- 🧠 Q-Learning agent with configurable ε-greedy, learning rate, discount, episodes, etc.
- 🧩 Rich tile set (walls, pits, mud/sticky, wind, trampolines, portals, tolls, batteries, gems, collapse, conveyors…)
- 🎛️ Big dashboard UI to design environments and tweak parameters
- 🎥 Visualizations: live grid, policy heatmaps, and rendered runs

---

## Quick start

### Windows
1. Install **Python 3.10–3.12**.
2. Start **JupyterLab** (recommended) or **Jupyter Notebook**.
3. Open **`gridworld.ipynb`**.
4. Run the first **Setup** cell (it will install missing packages and assets into your environment).
5. Run the dashboard cell and start experimenting!

### Linux (auto-setup)
> No admin privileges required.

```bash
chmod +x run_gridworld.sh
./run_gridworld.sh

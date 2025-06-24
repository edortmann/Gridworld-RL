import numpy as np


def q_learning(
        env,
        num_episodes=200,
        alpha=0.1,                  # Lernrate / learning rate
        gamma=0.95,                 # Diskontierungsfaktor / discount rate
        epsilon=0.1,                # Explorationsrate / exploration rate (epsilon-greedy strategy)
        epsilon_decay_factor=None,
        epsilon_decay_interval=1,
        epsilon_min=0.01,
        max_steps=100,              # Begrenzung der Schritte pro Episode, um endloses Umherwandern zu verhindern / limit on steps per episode to prevent infinite wandering
        record_interval=20,         # Intervall für die Speicherung von Trainingsepisoden / interval for storing training episodes
        report_interval=20          # Intervall für die Meldung der Episodenbelohnung / interval for reporting episode reward
):
    """
    Trainiere einen tabellarischen Q-Learning-Agenten in der gegebenen Umgebung.
    """
    num_states = env.rows * env.cols
    num_actions = 4  # up/down/left/right

    # Q‑Tabelle initialisieren (Anzahl_Zustände × Anzahl_Aktionen)
    Q = np.zeros((num_states, num_actions), dtype=np.float32)

    # Listen zur Speicherung der Trainingsdaten initialisieren
    stored_trajectories = {}  # key=Episode, value=Liste der gesehenen Zustände
    rewards_history = []

    for episode in range(num_episodes):
        state = env.reset()
        episode_reward = 0.0
        trajectory = [env.agent_pos]

        for t in range(max_steps):
            # Epsilon-greedy Aktions-Auswahl
            if np.random.rand() < epsilon:
                action = np.random.randint(num_actions)
            else:
                action = np.argmax(Q[state])

            next_state, reward, done = env.step(action)

            episode_reward += reward
            trajectory.append(env.agent_pos)

            # Q-learning update
            best_next_q = np.max(Q[next_state])
            Q[state, action] += alpha * (reward + gamma * best_next_q - Q[state, action])

            state = next_state

            if done:
                break

        rewards_history.append(episode_reward)

        # ε-annealing
        if (epsilon_decay_factor is not None and (episode + 1) % epsilon_decay_interval == 0):
            epsilon = max(epsilon_min, epsilon * epsilon_decay_factor)

        # Ende der Episode
        # Speichere die Laufbahn alle 'record_interval' Episoden
        if episode % record_interval == 0:
            stored_trajectories[episode] = trajectory[:]

        # Dokumentiere Belohnungs-Fortschritt
        #if episode % report_interval == 0:
        #    avg_r = np.mean(rewards_history[-report_interval:])
        #    print(f"Episode {episode}, Avg reward (last {report_interval} ep.): {avg_r:.2f}")

    return Q, stored_trajectories, rewards_history
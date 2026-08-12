import sys
import numpy as np
from enviroment import CaineEnv
from dqn_model import DQNAgent

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

env = CaineEnv()
obs_dim = env.observation_space.shape[0]
act_dim = env.action_space.n

agent = DQNAgent(input_dim=obs_dim, output_dim=act_dim, lr=3e-5)

try:
    agent.load("caine_dqn.pth")
    print("Продолжаем обучение с существующей модели")
except:
    print("Начинаем с нуля")

episodes = 30000
save_every = 1000
log_every  = 100

reward_history = []

for episode in range(episodes):
    obs, _ = env.reset()
    total_reward = 0
    losses = []

    while True:
        action = agent.select_action(obs)
        next_obs, reward, done, _, _ = env.step(action)

        agent.push(obs, action, reward, next_obs, float(done))
        loss = agent.train_step()
        if loss is not None:
            losses.append(loss)

        obs = next_obs
        total_reward += reward

        if done:
            break

    reward_history.append(total_reward)
    if len(reward_history) > 100:
        reward_history.pop(0)

    avg_reward = np.mean(reward_history)

    if episode % log_every == 0:
        avg_loss = np.mean(losses) if losses else 0
        print(
            f"Episode {episode:>5} | "
            f"reward: {total_reward:>8.2f} | "
            f"avg100: {avg_reward:>8.2f} | "
            f"loss: {avg_loss:>7.4f} | "
            f"epsilon: {agent.epsilon:.3f} | "
            f"buffer: {len(agent.buffer)}"
        )

    if episode % save_every == 0 and episode > 0:
        agent.save("caine_dqn.pth")

agent.save("caine_dqn.pth")
print("Обучение завершено!")
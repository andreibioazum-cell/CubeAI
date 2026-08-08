import torch
import torch.nn as nn
import numpy as np
from collections import deque
import random


class DQN(nn.Module):
    def __init__(self, input_dim, output_dim):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 256),
            nn.ReLU(),
            nn.Linear(256, 256),
            nn.ReLU(),
            nn.Linear(256, 128),
            nn.ReLU(),
            nn.Linear(128, output_dim),
        )

    def forward(self, x):
        return self.net(x)


class ReplayBuffer:
    def __init__(self, capacity=200000):
        self.buffer = deque(maxlen=capacity)

    def push(self, obs, action, reward, next_obs, done):
        self.buffer.append((obs, action, reward, next_obs, done))

    def sample(self, batch_size):
        batch = random.sample(self.buffer, batch_size)
        obs, actions, rewards, next_obs, dones = zip(*batch)
        return (
            torch.FloatTensor(np.array(obs)),
            torch.LongTensor(actions),
            torch.FloatTensor(rewards),
            torch.FloatTensor(np.array(next_obs)),
            torch.FloatTensor(dones),
        )

    def __len__(self):
        return len(self.buffer)


class DQNAgent:
    def __init__(self, input_dim, output_dim, lr=5e-5, gamma=0.95, device=None):
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.gamma = gamma
        self.output_dim = output_dim

        self.policy_net = DQN(input_dim, output_dim).to(self.device)
        self.target_net = DQN(input_dim, output_dim).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()

        self.optimizer = torch.optim.Adam(self.policy_net.parameters(), lr=lr)
        self.buffer = ReplayBuffer(capacity=200000)

        self.epsilon = 1.0
        self.epsilon_min = 0.05
        self.epsilon_decay = 0.999994
        self.batch_size = 128
        self.target_update_freq = 2000
        self.train_every = 4
        self.steps_done = 0

    def select_action(self, obs):
        if random.random() < self.epsilon:
            return random.randint(0, self.output_dim - 1)
        obs_t = torch.FloatTensor(obs).unsqueeze(0).to(self.device)
        with torch.no_grad():
            q_values = self.policy_net(obs_t)
        return int(q_values.argmax(dim=1).item())

    def push(self, obs, action, reward, next_obs, done):
        self.buffer.push(obs, action, reward, next_obs, done)

    def train_step(self):
        if len(self.buffer) < 5000:
            return None

        self.steps_done += 1
        if self.steps_done % self.train_every != 0:
            return None

        obs, actions, rewards, next_obs, dones = self.buffer.sample(self.batch_size)
        obs = obs.to(self.device)
        actions = actions.to(self.device)
        rewards = rewards.to(self.device)
        next_obs = next_obs.to(self.device)
        dones = dones.to(self.device)

        q_values = self.policy_net(obs).gather(1, actions.unsqueeze(1)).squeeze(1)

        with torch.no_grad():
            next_q = self.target_net(next_obs).max(1)[0]
            targets = rewards + self.gamma * next_q * (1 - dones)

        loss = nn.SmoothL1Loss()(q_values, targets)
        self.optimizer.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(self.policy_net.parameters(), 1.0)
        self.optimizer.step()

        self.epsilon = max(self.epsilon_min, self.epsilon * self.epsilon_decay)

        if self.steps_done % self.target_update_freq == 0:
            self.target_net.load_state_dict(self.policy_net.state_dict())

        return loss.item()

    def save(self, path="caine_dqn.pth"):
        torch.save({
            "policy_net": self.policy_net.state_dict(),
            "target_net": self.target_net.state_dict(),
            "optimizer": self.optimizer.state_dict(),
            "epsilon": self.epsilon,
            "steps_done": self.steps_done,
        }, path)
        print(f"Сохранено: {path}")

    def load(self, path="caine_dqn.pth"):
        checkpoint = torch.load(path, map_location=self.device)
        self.policy_net.load_state_dict(checkpoint["policy_net"])
        self.target_net.load_state_dict(checkpoint["target_net"])
        self.optimizer.load_state_dict(checkpoint["optimizer"])
        self.epsilon = max(checkpoint.get("epsilon", self.epsilon_min), 0.3)
        self.steps_done = 0
        print(f"Загружено: {path}, epsilon={self.epsilon:.3f}")
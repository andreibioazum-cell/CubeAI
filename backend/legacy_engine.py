"""Старый движок: DQN, копирующий шесть зашитых паттернов."""

import random

from enviroment import CaineEnv, LOCATION_TYPES
from dqn_model import DQNAgent

# Индексы цветов старой среды в реальные цвета
COLOR_HEX = {
    1: '#e04b4b', 2: '#4b7fe0', 3: '#4bc46b',
    4: '#e3c33f', 5: '#9b5fd0', 6: '#e08a3c',
    7: '#48c9d8', 8: '#e77bb5',
}


class LegacyEngine:
    def __init__(self, location=None, epsilon=0.01, offset=-27):
        self.env = CaineEnv()
        self.env.fixed_location = location or random.choice(list(LOCATION_TYPES))
        self.agent = DQNAgent(input_dim=self.env.observation_space.shape[0],
                              output_dim=self.env.action_space.n)
        try:
            self.agent.load("caine_dqn.pth")
        except Exception as e:
            print(f"[legacy] чекпоинт не найден: {e}")
        self.agent.epsilon = epsilon

        self.obs, _ = self.env.reset()
        self.offset = offset
        self.pattern_count = 0
        self.ox, self.oz = offset, offset
        self.placed = 0
        self.missed = 0

    @property
    def style_name(self):
        return LOCATION_TYPES[self.env.location_type]['name'] + ' (старый DQN)'

    def level_info(self):
        return {
            'style': self.env.location_type,
            'style_name': self.style_name,
            'pattern': self.env.pattern_name,
            'legacy': True,
            'decorations': [],
            'built': [],
            'sky': '#111111',
            'mood': 'механическое',
            'awaiting': False,
            'bounds': {'minx': -20, 'maxx': 20, 'minz': -20, 'maxz': 20},
            'total_steps': self.env.max_steps,
        }

    def step(self):
        action = self.agent.select_action(self.obs)
        self.obs, _, done, _, info = self.env.step(action)
        row, col, height = self.env.position

        x = float(col + self.ox)
        y = float(height)
        z = float(row + self.oz)

        frame = {
            'kind': 'move', 'x': x, 'y': 0.0, 'z': z,
            'blocks': [], 'decor': [],
            'progress': round(info['similarity'], 3),
            'map_done': bool(done), 'awaiting': False,
            'world_reset': False, 'level': None,
        }

        if info['placed']:
            self.placed += 1
            frame['kind'] = 'place'
            frame['blocks'] = [{'x': x, 'y': y, 'z': z,
                                'color': COLOR_HEX.get(info['color'], '#888888')}]
        elif info['miss']:
            self.missed += 1
            frame['kind'] = 'miss'
            frame['y'] = y

        if done:
            self.obs, _ = self.env.reset()
            self.pattern_count += 1
            if self.pattern_count % 5 == 0:
                self.ox = self.offset
                self.oz += 6
            else:
                self.ox += 6
            if self.oz > -self.offset:
                self.ox = self.oz = self.offset
                frame['world_reset'] = True
                frame['level'] = self.level_info()

        return frame

    def stats(self):
        total = self.placed + self.missed
        return {
            'mode': 'legacy',
            'style_name': self.style_name,
            'pattern': self.env.pattern_name,
            'epsilon': round(self.agent.epsilon, 4),
            'placed': self.placed,
            'missed': self.missed,
            'accuracy': round(self.placed / total, 3) if total else 0.0,
            'patterns_built': self.pattern_count,
        }

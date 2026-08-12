import gymnasium as gym
import numpy as np
import random

COLORS = ['red', 'blue', 'green', 'yellow', 'purple', 'orange', 'cyan', 'pink']

# ─────────────────────────────────────────────
# 6 паттернов 6x6
# 1 = стена, 2 = пол/акцент, 3 = особый акцент
# ─────────────────────────────────────────────
patterns = {

    # Ворота — вход в локацию, всегда первый
    'gate': [
        [1,1,0,0,1,1],
        [1,1,0,0,1,1],
        [1,1,0,0,1,1],
        [1,1,0,0,1,1],
        [3,3,3,3,3,3],
        [0,0,0,0,0,0],
    ],

    # Коридор — узкий проход со стенами
    'corridor': [
        [1,1,0,0,1,1],
        [1,1,0,0,1,1],
        [1,1,0,0,1,1],
        [1,1,0,0,1,1],
        [1,1,0,0,1,1],
        [1,1,0,0,1,1],
    ],

    # Перекрёсток — узел между комнатами
    'crossroad': [
        [1,1,0,0,1,1],
        [1,1,0,0,1,1],
        [0,0,0,0,0,0],
        [0,0,0,0,0,0],
        [1,1,0,0,1,1],
        [1,1,0,0,1,1],
    ],

    # Маленькая комната
    'room_small': [
        [1,1,1,1,1,1],
        [1,0,0,0,0,1],
        [1,0,0,0,0,1],
        [1,0,0,0,0,1],
        [1,0,0,0,0,1],
        [1,1,1,1,1,1],
    ],

    # Большая комната с колоннами
    'room_large': [
        [1,1,1,1,1,1],
        [1,2,0,0,2,1],
        [1,0,0,0,0,1],
        [1,0,0,0,0,1],
        [1,2,0,0,2,1],
        [1,1,1,1,1,1],
    ],

    # Башня — вертикальная структура
    'tower': [
        [0,3,3,3,3,0],
        [3,3,0,0,3,3],
        [3,0,0,0,0,3],
        [3,0,0,0,0,3],
        [1,1,1,1,1,1],
        [0,0,0,0,0,0],
    ],
}

# ─────────────────────────────────────────────
# Правила переходов
# ─────────────────────────────────────────────
transition_rules = {
    'gate':       ['corridor'],
    'corridor':   ['crossroad', 'room_small', 'room_large', 'tower'],
    'crossroad':  ['corridor', 'room_small', 'room_large'],
    'room_small': ['corridor', 'crossroad'],
    'room_large': ['corridor', 'crossroad'],
    'tower':      ['gate', 'corridor'],
}

# ─────────────────────────────────────────────
# Типы локаций
# ─────────────────────────────────────────────
LOCATION_TYPES = {
    'cave': {
        'name': 'Пещера',
        'wall_colors':   [5],
        'floor_colors':  [3],
        'accent_colors': [2],
        'decorations':   ['chest'],
        'description':   'Тёмная пещера с извилистыми коридорами',
    },
    'castle': {
        'name': 'Замок',
        'wall_colors':   [1],
        'floor_colors':  [4],
        'accent_colors': [5],
        'decorations':   ['chest'],
        'description':   'Величественный замок с башнями и залами',
    },
    'mansion': {
        'name': 'Особняк',
        'wall_colors':   [6],
        'floor_colors':  [4],
        'accent_colors': [8],
        'decorations':   ['chest'],
        'description':   'Роскошный особняк с просторными комнатами',
    },
    'island': {
        'name': 'Остров',
        'wall_colors':   [3],
        'floor_colors':  [2],
        'accent_colors': [1],
        'decorations':   ['chest', 'tree'],
        'description':   'Таинственный остров с сокровищами',
    },
}

pattern_names = list(patterns.keys())
pattern_list  = list(patterns.values())


class CaineEnv(gym.Env):
    def __init__(self):
        super().__init__()
        self.grid_size     = 6
        self.max_height    = 6
        self.num_patterns  = len(patterns)
        self.num_locations = len(LOCATION_TYPES)

        self.action_space = gym.spaces.Discrete(36)
        self.observation_space = gym.spaces.Box(
            low=0, high=8,
            shape=(
                self.grid_size * self.grid_size * self.max_height
                + 3
                + self.num_patterns
                + self.num_locations,
            ),
            dtype=np.float32,
        )

        self.pattern           = None
        self.pattern_name      = None
        self.last_pattern_name = None
        self.location_type     = None
        self.fixed_location    = None   # если задана — локация не меняется весь запуск
        self.grid              = None
        self.position          = [0, 0, 0]
        self.steps             = 0
        self.max_steps         = 250
        self.patterns_built    = 0

    def _pick_location(self):
        if self.fixed_location is not None:
            return self.fixed_location
        return random.choice(list(LOCATION_TYPES.keys()))

    def _next_pattern(self):
        if self.last_pattern_name is None or self.patterns_built == 0:
            return 'gate'

        allowed = list(transition_rules.get(self.last_pattern_name, pattern_names))

        # Правило 2: после gate башня запрещена
        if self.last_pattern_name == 'gate':
            allowed = [p for p in allowed if p != 'tower']

        # Правило 3: две комнаты подряд запрещены
        if self.last_pattern_name in ('room_small', 'room_large'):
            allowed = [p for p in allowed if p not in ('room_small', 'room_large')]

        # Правило 4: из crossroad нельзя в gate и tower
        if self.last_pattern_name == 'crossroad':
            allowed = [p for p in allowed if p not in ('gate', 'tower')]

        return random.choice(allowed) if allowed else 'corridor'

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        if self.last_pattern_name is None or self.patterns_built >= 6:
            self.location_type  = self._pick_location()
            self.patterns_built = 0
            self.last_pattern_name = None

        self.pattern_name = self._next_pattern()
        self.pattern      = patterns[self.pattern_name]
        self.grid         = np.zeros((self.grid_size, self.grid_size, self.max_height))
        self.position     = [0, 0, 0]
        self.steps        = 0
        return self._get_obs(), {}

    def _get_obs(self):
        flat   = self.grid.flatten()
        pos    = np.array(self.position, dtype=np.float32)

        pat_oh = np.zeros(self.num_patterns, dtype=np.float32)
        if self.pattern_name in pattern_names:
            pat_oh[pattern_names.index(self.pattern_name)] = 1.0

        loc_oh = np.zeros(self.num_locations, dtype=np.float32)
        loc_names = list(LOCATION_TYPES.keys())
        if self.location_type in loc_names:
            loc_oh[loc_names.index(self.location_type)] = 1.0

        return np.concatenate([flat, pos, pat_oh, loc_oh]).astype(np.float32)

    def _target_color(self):
        loc = LOCATION_TYPES[self.location_type]
        row, col, _ = self.position
        val = self.pattern[row][col]
        if val == 0:
            return 0
        if val == 1:
            return loc['wall_colors'][0]
        if val == 2:
            return loc['floor_colors'][0]
        return loc['accent_colors'][0]

    def _pattern_similarity(self):
        total, correct = 0, 0
        for r in range(self.grid_size):
            for c in range(self.grid_size):
                if self.pattern[r][c] != 0:
                    total += 1
                    if any(self.grid[r][c][h] == self.pattern[r][c]
                           for h in range(self.max_height)):
                        correct += 1
        return correct / total if total > 0 else 0

    def step(self, action):
        direction = action % 6
        color     = action // 6

        row, col, height = self.position

        if   direction == 0 and row > 0:                    row -= 1
        elif direction == 1 and row < self.grid_size - 1:   row += 1
        elif direction == 2 and col > 0:                    col -= 1
        elif direction == 3 and col < self.grid_size - 1:   col += 1
        elif direction == 4 and height < self.max_height-1: height += 1
        elif direction == 5 and height > 0:                 height -= 1

        self.position = [row, col, height]
        target_color  = self._target_color()
        already       = self.grid[row][col][height] != 0
        self.steps   += 1
        reward        = 0

        placed = False   # блок реально поставлен этим действием
        miss   = False   # агент попытался построить и ошибся

        if already:
            reward -= 2.0
            miss = True
        elif target_color == 0:
            reward += 0.3 if color == 5 else -0.5
        else:
            if color == target_color:
                reward += 3.0
                self.grid[row][col][height] = color
                placed = True
                reward += self._pattern_similarity() * 2.0
            else:
                reward -= 1.5
                miss = True

        done = self.steps >= self.max_steps
        similarity = self._pattern_similarity()

        if done:
            reward += similarity * 10.0
            self.last_pattern_name  = self.pattern_name
            self.patterns_built    += 1

        info = {
            'placed':     placed,
            'miss':       miss,
            'color':      int(color),
            'target':     int(target_color),
            'similarity': float(similarity),
        }
        return self._get_obs(), reward, done, False, info
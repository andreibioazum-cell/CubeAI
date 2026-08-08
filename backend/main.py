from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import random
from enviroment import CaineEnv, patterns as all_patterns, pattern_names, pattern_list, LOCATION_TYPES
from dqn_model import DQNAgent

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

env = CaineEnv()
obs_dim = env.observation_space.shape[0]
act_dim = env.action_space.n

agent = DQNAgent(input_dim=obs_dim, output_dim=act_dim, lr=5e-5)

obs, _ = env.reset()

# ── Одна локация на весь запуск ──────────────────────
LOCATION = random.choice(list(LOCATION_TYPES.keys()))
env.location_type = LOCATION
print(f"[Main] Локация этого запуска: {LOCATION_TYPES[LOCATION]['name']}")

PATTERN_SIZE  = 5
pattern_count = 0
offset_x      = -30
offset_z      = -30

placed_decorations = []

COLOR_MAP = {
    1: 'red',    2: 'blue',   3: 'green',
    4: 'yellow', 5: 'purple', 6: 'orange',
    7: 'cyan',   8: 'pink',
}


def get_location_color(location_type, color_index):
    loc = LOCATION_TYPES[location_type]
    if color_index == 1:
        c = loc['wall_colors'][0]
    elif color_index == 2:
        c = loc['floor_colors'][0]
    elif color_index == 3:
        c = loc['accent_colors'][0]
    else:
        return None
    return COLOR_MAP.get(c, 'red')


def get_shape(pattern_name, row, col):
    if pattern_name == 'tower':
        if row <= 1:   return 'cone'
        elif row <= 2: return 'sphere'
        else:          return 'cube'
    elif pattern_name == 'room_large':
        return 'sphere' if row in (1, 3) and col in (1, 3) else 'cube'
    return 'cube'


def generate_decorations(location_type, ox, oz, count=2):
    loc = LOCATION_TYPES[location_type]
    result = []
    for _ in range(count):
        dec_type = random.choice(loc['decorations'])
        x = float(random.randint(0, PATTERN_SIZE - 1) + ox)
        z = float(random.randint(0, PATTERN_SIZE - 1) + oz)
        result.append({'type': dec_type, 'x': x, 'y': 0.0, 'z': z})
    return result


@app.on_event("startup")
def load_model():
    try:
        agent.load("caine_dqn.pth")
        print(f"DQN загружена! Локация: {LOCATION_TYPES[LOCATION]['name']}")
    except Exception as e:
        print(f"DQN не найдена: {e}")


@app.get("/step")
def step():
    global obs, pattern_count, offset_x, offset_z, placed_decorations

    action = agent.select_action(obs)
    next_obs, reward, done, _, _ = env.step(action)

    agent.push(obs, action, reward, next_obs, float(done))
    agent.train_step()

    obs = next_obs
    row, col, height = env.position

    pattern_name = env.pattern_name
    pattern      = all_patterns[pattern_name]

    target = pattern[row][col]
    color  = get_location_color(LOCATION, target) if target != 0 else None
    shape  = get_shape(pattern_name, row, col)

    world_x = float(col + offset_x)
    world_y = float(height)
    world_z = float(row + offset_z)

    new_decorations = []
    new_walker      = None

    if done:
        obs, _ = env.reset()
        pattern_count += 1

        # Случайное расположение паттернов
        if pattern_count % 5 == 0:
            offset_x = -30
            offset_z += 6
        else:
            offset_x += 6

        if offset_z > 30:
            offset_x = -30
            offset_z = -30
            pattern_count = 0

        # Декорации для нового паттерна
        new_decorations = generate_decorations(LOCATION, offset_x, offset_z)
        placed_decorations.extend(new_decorations)

        # 30% шанс создать гуляку
        if random.random() < 0.3:
            new_walker = {
                'color': random.choice(['red', 'blue', 'green']),
                'x': float(offset_x + random.randint(0, PATTERN_SIZE - 1)),
                'z': float(offset_z + random.randint(0, PATTERN_SIZE - 1)),
            }

        if pattern_count % 10 == 0:
            agent.save("caine_dqn.pth")

    return {
        "x": world_x,
        "y": world_y,
        "z": world_z,
        "color": color,
        "shape": shape,
        "done": done,
        "pattern_name": pattern_name,
        "location": LOCATION,
        "location_name": LOCATION_TYPES[LOCATION]['name'],
        "epsilon": round(agent.epsilon, 4),
        "new_decorations": new_decorations,
        "new_walker": new_walker,
    }


@app.get("/reset")
def reset():
    global obs, pattern_count, offset_x, offset_z, placed_decorations
    obs, _ = env.reset()
    pattern_count = 0
    offset_x      = -30
    offset_z      = -30
    placed_decorations = []
    return {"x": 0.0, "y": 0.0, "z": 0.0}


@app.get("/stats")
def stats():
    return {
        "epsilon":        round(agent.epsilon, 4),
        "steps_done":     agent.steps_done,
        "buffer_size":    len(agent.buffer),
        "total_patterns": len(all_patterns),
        "location":       LOCATION,
        "location_name":  LOCATION_TYPES[LOCATION]['name'],
        "pattern_count":  pattern_count,
    }
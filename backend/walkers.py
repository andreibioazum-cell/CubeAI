"""Гуляки с мозгами: критик меряет карту тем, как в ней живётся."""

import os

import numpy as np

BRAIN_PATH = os.path.join(os.path.dirname(__file__), 'walker_brain.npz')

# север, восток, юг, запад в координатах (z, x)
MOVES = np.array([(-1, 0), (0, 1), (1, 0), (0, -1)], dtype=np.int32)

# 4 — что проходимо, 4 — где не был, 4 — куда шёл в прошлый раз,
# 1 — затоптанность своей клетки, 1 — давно ли попадалось новое,
# 1 — сколько времени вышло.
N_IN = 15
N_HID = 12
N_OUT = 4
N_PARAMS = N_IN * N_HID + N_HID + N_HID * N_OUT + N_OUT

DEFAULT_N = 16
DEFAULT_STEPS = 420

# Явная просьба «иди без мозга». Раньше её роль играл theta=None, но это же
# значение означает «возьми сохранённый мозг» — и приёмка, сравнивавшая
# эволюционировавшего ходока с наивным, после появления файла мозга начала
# молча сравнивать мозг сам с собой.
NAIVE = 'naive'


def unpack(theta):
    i = 0
    w1 = theta[i:i + N_IN * N_HID].reshape(N_IN, N_HID); i += N_IN * N_HID
    b1 = theta[i:i + N_HID]; i += N_HID
    w2 = theta[i:i + N_HID * N_OUT].reshape(N_HID, N_OUT); i += N_HID * N_OUT
    b2 = theta[i:i + N_OUT]
    return w1, b1, w2, b2


def seed_brain(rng, noise=0.05):
    """Мозг, уже умеющий держать курс и тянуться к неизведанному."""
    w1 = rng.normal(0, noise, (N_IN, N_HID))
    b1 = np.zeros(N_HID)
    w2 = rng.normal(0, noise, (N_HID, N_OUT))
    b2 = np.zeros(N_OUT)
    for k in range(4):
        w1[8 + k, k] = 1.4          # прошлое направление
        w1[4 + k, k] = 1.1          # новизна соседней клетки
        w1[k, k] = 0.6              # проходимо ли туда
        w2[k, k] = 2.0
    return np.concatenate([w1.ravel(), b1, w2.ravel(), b2])


def walkable_grid(level):
    return np.asarray(level.roles) == 0


def simulate(level, dist, goal, theta=None, n=DEFAULT_N, steps=DEFAULT_STEPS,
             rng=None, trace=False, temp=0.2, seed=0):
    """Прогулка. Возвращает (доля нашедших цель, среднее время, покрытие)."""
    walk = walkable_grid(level)
    total = int(walk.sum())
    if not total or not dist:
        return (0.0, 1.0, 0.0) if not trace else (0.0, 1.0, 0.0, [])

    h, w = walk.shape
    start = level.entry_cell()
    if theta is NAIVE:
        return naive_walk(level, walk, dist, goal, n, steps, rng, trace)
    if theta is None:
        theta = load()
    if theta is None:
        return naive_walk(level, walk, dist, goal, n, steps, rng, trace)

    w1, b1, w2, b2 = unpack(theta)
    z = np.full(n, start[0], dtype=np.int32)
    x = np.full(n, start[1], dtype=np.int32)

    # Всё разложено в плоские массивы и переиспользуется между шагами.
    flat = walk.ravel()
    nrng = np.random.default_rng(seed)

    # Память у каждого ходока своя: общая превратила бы стаю в один организм.
    visits = np.zeros((n, h * w), dtype=np.int16)
    pos = z * w + x
    idx = np.arange(n)
    visits[idx, pos] = 1
    seen = np.zeros(h * w, dtype=bool)
    seen[pos] = True

    alive = np.ones(n, dtype=bool)
    found_at = np.full(n, -1, dtype=np.int32)
    path = [] if trace else None
    goal_flat = goal[0] * w + goal[1] if goal is not None else -1

    # Стая должна быть стаей, а не одним ходоком в шестнадцати копиях.
    obs = np.zeros((n, N_IN))
    obs[idx, 8 + nrng.integers(0, 4, n)] = 1.0      # начальный курс
    stale = np.zeros(n)
    step_off = np.array([-w, 1, w, -1], dtype=np.int32)
    col = x

    for t in range(steps):
        if not alive.any():
            break
        nb = pos[:, None] + step_off[None, :]
        ncol = col[:, None] + np.array([0, 1, 0, -1])[None, :]
        free = ((nb >= 0) & (nb < h * w) & (ncol >= 0) & (ncol < w))
        nb = np.clip(nb, 0, h * w - 1)
        free &= flat[nb]

        obs[:, 0:4] = free
        np.exp(visits[idx[:, None], nb] * -0.7, out=obs[:, 4:8])
        obs[:, 4:8] *= free
        obs[:, 12] = visits[idx, pos] * 0.1
        obs[:, 13] = stale * 0.05
        obs[:, 14] = t / steps

        act = np.tanh(obs @ w1 + b1) @ w2 + b2
        act = np.where(free, act, -1e9)
        if temp > 0:
            e = np.exp((act - act.max(axis=1, keepdims=True)) / temp) * free
            tot = e.sum(axis=1, keepdims=True)
            d = (np.where(tot > 0, e / np.maximum(tot, 1e-12),
                          0.0).cumsum(axis=1)
                 < nrng.random((n, 1))).sum(axis=1).clip(0, 3)
        else:
            d = act.argmax(axis=1)

        alive &= free.any(axis=1)
        step = np.where(alive, nb[idx, d] - pos, 0)
        pos = pos + step
        col = pos % w
        fresh = alive & ~seen[pos]
        stale = np.where(fresh, 0.0, stale + 1.0)
        visits[idx, pos] += alive
        seen[pos] |= alive
        obs[:, 8:12] = 0.0
        obs[idx, 8 + d] = alive
        if trace:
            path.append(np.stack([pos // w, col], axis=1).copy())

        if goal_flat >= 0:
            # Ходок не исчезает, найдя сундук: иначе покрытие и находки
            # меряют друг друга — кто дошёл быстрее, тот меньше обошёл,
            # и отбор уходит в спринтеров вместо исследователей.
            hit = alive & (pos == goal_flat) & (found_at < 0)
            found_at[hit] = t

    found = int((found_at >= 0).sum())
    reach = found / n
    mean_time = float(found_at[found_at >= 0].mean() / steps) if found else 1.0
    coverage = float(seen.sum() / total)
    if trace:
        return reach, mean_time, coverage, path
    return reach, mean_time, coverage


def naive_walk(level, walk, dist, goal, n=30, steps=700, rng=None,
               trace=False):
    """Бродяга без памяти: держится направления, у стены сворачивает."""
    import random
    rng = rng or random.Random(0)
    cells = set(dist)
    start = level.entry_cell()
    visited, found, times = set(), 0, []
    for _ in range(n):
        pos, d = start, rng.randrange(4)
        for t in range(steps):
            if rng.random() < 0.25:
                d = rng.randrange(4)
            nxt = (pos[0] + MOVES[d][0], pos[1] + MOVES[d][1])
            if nxt not in cells:
                opts = [i for i in range(4)
                        if (pos[0] + MOVES[i][0], pos[1] + MOVES[i][1]) in cells]
                if not opts:
                    break
                d = rng.choice(opts)
                nxt = (pos[0] + MOVES[d][0], pos[1] + MOVES[d][1])
            pos = nxt
            visited.add(pos)
            if goal and pos == goal:
                found += 1
                times.append(t / steps)
                break
    reach = found / n
    mt = sum(times) / len(times) if times else 1.0
    cov = len(visited) / max(len(cells), 1)
    return (reach, mt, cov, []) if trace else (reach, mt, cov)


# ─────────────────────────────────────────────────────────────
# Хранение мозга
# ─────────────────────────────────────────────────────────────

_CACHE = {'theta': None, 'loaded': False}


def save(theta, path=BRAIN_PATH, meta=None):
    np.savez(path, theta=np.asarray(theta, dtype=np.float64),
             **(meta or {}))
    _CACHE['theta'] = np.asarray(theta, dtype=np.float64)
    _CACHE['loaded'] = True
    return path


def load(path=BRAIN_PATH):
    if _CACHE['loaded']:
        return _CACHE['theta']
    _CACHE['loaded'] = True
    if not os.path.exists(path):
        _CACHE['theta'] = None
        return None
    try:
        _CACHE['theta'] = np.load(path)['theta']
    except (OSError, KeyError, ValueError):
        _CACHE['theta'] = None
    return _CACHE['theta']

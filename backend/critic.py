"""Критик: насколько карта хороша."""

import math
import random
from collections import Counter

from modules import MODULES, DELTA, OPPOSITE, sockets
import walkers

# Веса слагаемых. Сумма положительных ≈ 1.0, штрафы вычитаются сверху.
WEIGHTS = {
    'reach_rate':   0.22,   # доля гуляк, нашедших сундук
    'coverage':     0.16,   # какую часть карты они обошли
    'winding':      0.14,   # маршрут до цели длиннее прямого пути
    'loops':        0.12,   # есть циклы, а не только дерево коридоров
    'depth':        0.12,   # карту есть куда углубляться
    'variety':      0.14,   # разнообразие модулей
    'spread':       0.10,   # постройка разложена по полю, а не сжата
}

PENALTIES = {
    'open_blob':    0.45,   # один гигантский пустой зал
    'snake':        0.40,   # кишка без ветвлений
    'huddle':       0.30,   # всё скучено в углу
    'monotony':     0.35,   # одни и те же модули
    'trivial':      0.50,   # цель в двух шагах от входа
}

NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1))


# ─────────────────────────────────────────────────────────────
# Наивные ходоки
# ─────────────────────────────────────────────────────────────

def simulate_explorers(level, dist, goal, n=30, steps=700, rng=None):
    """Гуляки с эволюционировавшими мозгами, а если мозга нет — бродяги."""
    brain = walkers.load()
    if brain is not None:
        return walkers.simulate(level, dist, goal, brain,
                                n=walkers.DEFAULT_N,
                                steps=walkers.DEFAULT_STEPS)
    return walkers.simulate(level, dist, goal, walkers.NAIVE,
                            n=n, steps=steps, rng=rng)


# ─────────────────────────────────────────────────────────────
# Структура
# ─────────────────────────────────────────────────────────────

def loop_ratio(level):
    """Обходные пути: сколько в карте независимых петель."""
    v = len(level.tiles)
    if v < 3:
        return 0.0
    e = 0
    for (tx, ty), t in level.tiles.items():
        for side in ('E', 'S'):          # каждое ребро считаем один раз
            dx, dy = DELTA[side]
            nb = level.tiles.get((tx + dx, ty + dy))
            if nb and side in sockets(t['grid']) \
                    and OPPOSITE[side] in sockets(nb['grid']):
                e += 1
    cycles = max(0, e - v + 1)
    return min(1.0, cycles / max(v / 10.0, 1.0))


def goal_cell(level):
    for d in level.decorations:
        if d.get('goal'):
            return (int(d['z']), int(d['x']))
    return None


def bfs_path_len(dist, goal):
    return dist.get(goal, 0) if goal else 0


def open_blob_ratio(level, dist):
    """Доля клеток, у которых открыты все четыре соседа."""
    walk = set(dist)
    if not walk:
        return 0.0
    wide = sum(1 for (z, x) in walk
               if all((z + dz, x + dx) in walk for dz, dx in NEIGHBOURS))
    return wide / len(walk)


def module_entropy(level):
    """Разнообразие модулей."""
    names = [t['name'] for t in level.tiles.values()]
    if not names:
        return 0.0
    counts = Counter(names)
    total = len(names)
    h = -sum((c / total) * math.log(c / total) for c in counts.values())
    return min(1.0, h / math.log(len(MODULES)))


def spread_ratio(level):
    """Насколько постройка разложена по полю относительно своего объёма."""
    if not level.tiles:
        return 0.0
    xs = [tx for (tx, _) in level.tiles]
    zs = [ty for (_, ty) in level.tiles]
    box = (max(xs) - min(xs) + 1) * (max(zs) - min(zs) + 1)
    return min(1.0, box / max(len(level.tiles) * 2.2, 1.0))


# ─────────────────────────────────────────────────────────────
# Оценка
# ─────────────────────────────────────────────────────────────

def evaluate(level, rng=None, clip_score=None, human_score=None):
    """Оценить карту. Возвращает счёт, слагаемые и причину отказа."""
    rng = rng or random.Random(0)
    dist = level.distances()
    d = level.descriptor
    goal = goal_cell(level)

    # ── жёсткие ворота ───────────────────────────────────────
    gate_fail = None
    if d.get('reachability', 0) < 0.999:
        gate_fail = 'карта не проходима целиком'
    elif goal is None:
        gate_fail = 'нет цели'
    elif len(dist) < 40:
        gate_fail = 'слишком мало проходимых клеток'
    if gate_fail:
        return {'score': 0.0, 'rejected': gate_fail, 'terms': {}, 'penalties': {}}

    # ── ходоки ───────────────────────────────────────────────
    reach_rate, mean_time, coverage = simulate_explorers(level, dist, goal, rng=rng)

    # ── структура ────────────────────────────────────────────
    path = bfs_path_len(dist, goal)
    straight = abs(goal[0] - level.entry_cell()[0]) + abs(goal[1] - level.entry_cell()[1])
    winding = min(1.0, (path / max(straight, 1) - 1.0) / 1.5) if straight else 0.0
    loops = loop_ratio(level)
    depth = min(1.0, d['depth'] / 90.0)
    variety = module_entropy(level)
    spread = spread_ratio(level)

    terms = {
        'reach_rate': reach_rate,
        'coverage': coverage,
        'winding': max(0.0, winding),
        'loops': loops,
        'depth': depth,
        'variety': variety,
        'spread': spread,
    }
    score = sum(WEIGHTS[k] * v for k, v in terms.items())

    # ── вырождение ───────────────────────────────────────────
    blob = open_blob_ratio(level, dist)
    pen = {}
    if blob > 0.35:
        pen['open_blob'] = PENALTIES['open_blob'] * min(1.0, (blob - 0.35) / 0.35)
    # Кишка — это не «мало развилок», а «мало развилок И всё одинаковое».
    if d['branching'] < 0.03 and loops < 0.02 and variety < 0.45:
        pen['snake'] = PENALTIES['snake']
    if spread < 0.35:
        pen['huddle'] = PENALTIES['huddle'] * (1.0 - spread / 0.35)
    if variety < 0.45:
        pen['monotony'] = PENALTIES['monotony'] * (1.0 - variety / 0.45)
    if path < 12:
        pen['trivial'] = PENALTIES['trivial']

    score -= sum(pen.values())

    # ── вкус и зрители ───────────────────────────────────────
    if clip_score is not None:
        terms['clip'] = clip_score
        score += 0.15 * clip_score
    if human_score is not None:
        terms['human'] = human_score
        score += 0.15 * human_score

    return {
        'score': round(max(0.0, score), 4),
        'rejected': None,
        'terms': {k: round(v, 3) for k, v in terms.items()},
        'penalties': {k: round(v, 3) for k, v in pen.items()},
        'path_len': path,
        'mean_time': round(mean_time, 3),
    }


def describe(result):
    if result['rejected']:
        return f"отклонена: {result['rejected']}"
    good = ' '.join(f'{k}={v}' for k, v in result['terms'].items())
    bad = ' '.join(f'-{k}={v}' for k, v in result['penalties'].items())
    return f"счёт={result['score']:.3f}  {good}  {bad}".strip()

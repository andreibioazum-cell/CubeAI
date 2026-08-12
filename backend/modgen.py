"""Изобретение новых модулей."""

import json
import os
import random
from collections import deque

import numpy as np

from modules import (
    MODULES, VARIANTS, TILE, SIDES, BASE_MODULE_NAMES,
    register_module, unregister_module, sockets,
)

INVENTED_PATH = os.path.join(os.path.dirname(__file__), 'invented_modules.json')

DOOR = (2, 3)                 # канонические клетки прохода на стороне
CENTRE = ((2, 2), (2, 3), (3, 2), (3, 3))
MIN_OPEN, MAX_OPEN = 8, 28


# ─────────────────────────────────────────────────────────────
# Форма
# ─────────────────────────────────────────────────────────────

def _apply_edges(g, sides):
    """Привести границы к канону: либо дверь в клетках 2–3, либо глухая стена."""
    for side in SIDES:
        idx = list(range(TILE))
        for i in idx:
            v = 0 if (side in sides and i in DOOR) else 1
            if side == 'N':   g[0, i] = v if v == 0 else max(g[0, i], 1)
            elif side == 'S': g[TILE - 1, i] = v if v == 0 else max(g[TILE - 1, i], 1)
            elif side == 'W': g[i, 0] = v if v == 0 else max(g[i, 0], 1)
            else:             g[i, TILE - 1] = v if v == 0 else max(g[i, TILE - 1], 1)
    return g


def _carve_to_centre(g, side):
    """Прокопать проход от двери к центру — гнездо обязано вести внутрь."""
    if side == 'N':
        for r in range(0, 3):
            g[r, 2] = g[r, 3] = 0
    elif side == 'S':
        for r in range(3, TILE):
            g[r, 2] = g[r, 3] = 0
    elif side == 'W':
        for c in range(0, 3):
            g[2, c] = g[3, c] = 0
    else:
        for c in range(3, TILE):
            g[2, c] = g[3, c] = 0
    return g


def _largest_open_component(g):
    open_cells = {(r, c) for r in range(TILE) for c in range(TILE) if g[r, c] == 0}
    best = set()
    seen = set()
    for cell in open_cells:
        if cell in seen:
            continue
        comp = set()
        q = deque([cell])
        seen.add(cell)
        while q:
            r, c = q.popleft()
            comp.add((r, c))
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                n = (r + dr, c + dc)
                if n in open_cells and n not in seen:
                    seen.add(n)
                    q.append(n)
        if len(comp) > len(best):
            best = comp
    return best


def _seal_islands(g):
    """Отрезанные пустоты закрываем: карман без входа — это не комната."""
    comp = _largest_open_component(g)
    for r in range(TILE):
        for c in range(TILE):
            if g[r, c] == 0 and (r, c) not in comp:
                g[r, c] = 1
    return g


def propose(rng, base=None):
    """Новый модуль: либо правка существующего, либо форма с нуля."""
    n_sides = rng.choice([1, 2, 2, 3, 3, 4])
    sides = set(rng.sample(list(SIDES), n_sides))

    if base is not None and rng.random() < 0.65:
        g = np.array(MODULES[base]['grid'], dtype=np.int8).copy()
        for r in range(1, TILE - 1):
            for c in range(1, TILE - 1):
                if rng.random() < 0.25:
                    g[r, c] = 0 if g[r, c] != 0 else 1
    else:
        g = np.ones((TILE, TILE), dtype=np.int8)
        for _ in range(rng.randint(1, 3)):     # пара случайных полостей
            r0 = rng.randint(1, 3)
            c0 = rng.randint(1, 3)
            h = rng.randint(1, 4 - r0 + 1)
            w = rng.randint(1, 4 - c0 + 1)
            g[r0:r0 + h, c0:c0 + w] = 0

    for (r, c) in CENTRE:
        g[r, c] = 0
    for side in sides:
        _carve_to_centre(g, side)
    _apply_edges(g, sides)
    _seal_islands(g)

    # акценты: часть внутренних стен становится деталями
    for r in range(1, TILE - 1):
        for c in range(1, TILE - 1):
            if g[r, c] == 1 and rng.random() < 0.2:
                g[r, c] = 3
    return g


# ─────────────────────────────────────────────────────────────
# Проверка
# ─────────────────────────────────────────────────────────────

def validate(g):
    """Причина отказа или None."""
    g = np.asarray(g)
    got = sockets(g)
    if not got:
        return 'нет ни одного гнезда'

    for side in SIDES:
        if side == 'N':   edge = g[0, :]
        elif side == 'S': edge = g[TILE - 1, :]
        elif side == 'W': edge = g[:, 0]
        else:             edge = g[:, TILE - 1]
        opened = {i for i in range(TILE) if edge[i] == 0}
        if opened and opened != set(DOOR):
            return f'нестандартная дверь на стороне {side}'

    comp = _largest_open_component(g)
    n_open = int(np.sum(g == 0))
    if len(comp) != n_open:
        return 'внутренность распадается на куски'
    if not (MIN_OPEN <= n_open <= MAX_OPEN):
        return f'плотность вне диапазона ({n_open} проходимых)'

    # каждое гнездо должно вести в общую внутренность
    for side in got:
        cells = ([(0, i) for i in DOOR] if side == 'N' else
                 [(TILE - 1, i) for i in DOOR] if side == 'S' else
                 [(i, 0) for i in DOOR] if side == 'W' else
                 [(i, TILE - 1) for i in DOOR])
        if not any(c in comp for c in cells):
            return f'дверь {side} никуда не ведёт'
    return None


def infer_role(g):
    n_sockets = len(sockets(g))
    n_open = int(np.sum(g == 0))
    if n_sockets == 1:
        return 'dead_end' if n_open < 14 else 'room'
    if n_sockets >= 3:
        return 'junction' if n_open < 18 else 'arena'
    return 'corridor' if n_open < 14 else 'room'


def decor_slots(g, rng, limit=4):
    inner = [(r, c) for r in range(1, TILE - 1) for c in range(1, TILE - 1)
             if g[r, c] == 0]
    rng.shuffle(inner)
    return [(r, c, 'any') for r, c in inner[:limit]]


def buildable_by_hands(name):
    """Достраивается ли модуль руками на 100%."""
    from genome import Genome, variants_for
    from levelgen import STYLES, MAP_W, MAP_H
    from hands import build_steps
    import copy as _copy

    rng = random.Random(0)
    cx, cy = MAP_W // 2, MAP_H - 1
    opts = variants_for(name, 'S', rng)
    if not opts:
        opts = variants_for(name, 'N', rng)
        if not opts:
            return False, 'нет подходящего поворота'

    # Тайлов должно быть не меньше четырёх: карта меньше декодер считает
    # мусором и отбрасывает целиком.
    spot = (cx, cy - 3)
    tiles = {
        (cx, cy): {'name': 'gate', 'rot': 0, 'flip': False, 'sym': False},
        (cx, cy - 1): {'name': 'corridor', 'rot': 0, 'flip': False, 'sym': False},
        (cx, cy - 2): {'name': 'corridor', 'rot': 0, 'flip': False, 'sym': False},
        spot: opts[0],
    }
    gm = Genome(tiles, (cx, cy), _copy.deepcopy(STYLES['castle']))
    lv = gm.decode()
    if lv is None:
        return False, 'карта с ним не собирается'
    if spot not in lv.tiles:
        return False, 'модуль отваливается при починке'
    rep = build_steps(lv).report()
    if rep['coverage'] < 1.0:
        return False, f'достраивается только на {rep["coverage"] * 100:.0f}%'
    return True, None


# ─────────────────────────────────────────────────────────────
# Пул изобретений
# ─────────────────────────────────────────────────────────────

def invented_names():
    return [n for n in MODULES if n not in BASE_MODULE_NAMES]


def invent(rng, tries=40):
    """Придумать один валидный модуль и зарегистрировать его."""
    for _ in range(tries):
        base = rng.choice(list(MODULES)) if rng.random() < 0.7 else None
        g = propose(rng, base)
        if validate(g) is not None:
            continue
        name = f'inv_{rng.randrange(10 ** 9):09d}'
        register_module(name, g, role=infer_role(g),
                        decor=decor_slots(g, rng),
                        height=round(rng.uniform(0.6, 2.6), 2))
        ok, why = buildable_by_hands(name)
        if not ok:
            unregister_module(name)
            continue
        return name
    return None


def save(path=INVENTED_PATH):
    data = [{'name': n, 'grid': np.asarray(MODULES[n]['grid']).tolist(),
             'role': MODULES[n]['role'], 'decor': MODULES[n]['decor'],
             'height': MODULES[n]['height']}
            for n in invented_names()]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return len(data)


def load(path=INVENTED_PATH):
    if not os.path.exists(path):
        return 0
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    for m in data:
        register_module(m['name'], m['grid'], role=m['role'],
                        decor=[tuple(d) for d in m['decor']], height=m['height'])
    return len(data)


def to_ascii(name):
    glyph = {0: '.', 1: '#', 2: '-', 3: '+'}
    g = np.asarray(MODULES[name]['grid'])
    return '\n'.join(''.join(glyph[int(v)] for v in row) for row in g)

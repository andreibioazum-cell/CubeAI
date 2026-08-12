"""Реквизит как данные: Кейн придумывает предметы, а не берёт мои восемь."""

import json
import math
import os
import random

import numpy as np

INVENTED_PATH = os.path.join(os.path.dirname(__file__), 'invented_props.json')

SHAPES = ('box', 'cyl', 'cone', 'sphere', 'torus')
TONES = ('accent', 'wall', 'floor', 'dark', 'light')
# Роли, которые заведомо контрастируют с постройкой вокруг.
VISIBLE_TONES = ('accent', 'accent', 'light')

MIN_PARTS, MAX_PARTS = 2, 6
MAX_REACH = 0.45        # половина клетки: дальше предмет вылезет на соседа
MAX_HEIGHT = 2.6
MIN_SIZE = 0.08
VOX = 14                # разрешение вокселизации для замеров силуэта

INVENTED = {}


# ─────────────────────────────────────────────────────────────
# Порождение и мутация
# ─────────────────────────────────────────────────────────────

def _part(rng, y=0.0):
    w = round(rng.uniform(0.12, 0.55), 3)
    d = round(rng.uniform(0.12, 0.55), 3)
    h = round(rng.uniform(0.15, 0.9), 3)
    return {
        'shape': rng.choice(SHAPES),
        'x': round(rng.uniform(-0.18, 0.18), 3),
        'y': round(y, 3),
        'z': round(rng.uniform(-0.18, 0.18), 3),
        'w': w, 'h': h, 'd': d,
        'rot': round(rng.choice([0, 0, 0, 0.785, 1.571]), 3),
        # Тон смещён к заметным: предмет цвета стены — это предмет,
        # которого зритель не увидит. Первая версия выбирала роль цвета
        # равновероятно, и половина реквизита сливалась с постройкой.
        'tone': rng.choice(VISIBLE_TONES + TONES),
    }


def propose(rng, base=None):
    """Новый предмет: либо с нуля стопкой деталей, либо мутацией готового."""
    if base is None:
        n = rng.randint(MIN_PARTS, 4)
        parts, y = [], 0.0
        for _ in range(n):
            p = _part(rng, y)
            parts.append(p)
            y += p['h'] * rng.uniform(0.55, 1.0)
        return {'parts': parts}
    return mutate(base, rng)


def mutate(prop, rng, k=1):
    p = json.loads(json.dumps(prop))
    for _ in range(k):
        parts = p['parts']
        ops = ['resize', 'move', 'tone', 'shape', 'rot']
        if len(parts) < MAX_PARTS:
            ops += ['add', 'add']
        if len(parts) > MIN_PARTS:
            ops.append('drop')
        op = rng.choice(ops)

        if op == 'add':
            top = max((q['y'] + q['h'] for q in parts), default=0.0)
            parts.append(_part(rng, top * rng.uniform(0.6, 1.0)))
        elif op == 'drop':
            parts.pop(rng.randrange(len(parts)))
        else:
            q = parts[rng.randrange(len(parts))]
            if op == 'resize':
                for key in rng.sample(['w', 'h', 'd'], rng.randint(1, 3)):
                    q[key] = round(max(MIN_SIZE, q[key] * rng.uniform(0.6, 1.6)), 3)
            elif op == 'move':
                for key in rng.sample(['x', 'y', 'z'], rng.randint(1, 2)):
                    lo = 0.0 if key == 'y' else -MAX_REACH
                    q[key] = round(min(MAX_HEIGHT, max(lo, q[key]
                                                       + rng.uniform(-0.2, 0.2))), 3)
            elif op == 'tone':
                q['tone'] = rng.choice(TONES)
            elif op == 'shape':
                q['shape'] = rng.choice(SHAPES)
            else:
                q['rot'] = round(rng.choice([0, 0.785, 1.571, 2.356]), 3)
    return p


def crossover(a, b, rng):
    """Взять низ у одного предмета и верх у другого."""
    pa = sorted(a['parts'], key=lambda q: q['y'])
    pb = sorted(b['parts'], key=lambda q: q['y'])
    cut = rng.uniform(0.3, 0.7)
    ha = max((q['y'] + q['h'] for q in pa), default=1.0)
    hb = max((q['y'] + q['h'] for q in pb), default=1.0)
    low = [q for q in pa if q['y'] <= ha * cut]
    high = [q for q in pb if q['y'] > hb * cut]
    parts = (low + high)[:MAX_PARTS]
    if len(parts) < MIN_PARTS:
        parts = (pa + pb)[:MIN_PARTS]
    return json.loads(json.dumps({'parts': parts}))


# ─────────────────────────────────────────────────────────────
# Жёсткие ворота
# ─────────────────────────────────────────────────────────────

def _single_body(g):
    """Составляет ли заполненный объём одно тело."""
    idx = np.argwhere(g)
    seed = idx[np.lexsort((idx[:, 0], idx[:, 2], idx[:, 1]))][0]
    grown = np.zeros_like(g)
    grown[tuple(seed)] = True
    total = int(g.sum())
    while True:
        n = int(grown.sum())
        if n == total:
            return True
        nxt = grown.copy()
        nxt[1:] |= grown[:-1]
        nxt[:-1] |= grown[1:]
        nxt[:, 1:] |= grown[:, :-1]
        nxt[:, :-1] |= grown[:, 1:]
        nxt[:, :, 1:] |= grown[:, :, :-1]
        nxt[:, :, :-1] |= grown[:, :, 1:]
        nxt &= g
        if int(nxt.sum()) == n:
            return False
        grown = nxt


def validate(prop):
    """Ворота физики. Возвращает причину отказа или None."""
    parts = prop.get('parts') or []
    if not (MIN_PARTS <= len(parts) <= MAX_PARTS):
        return 'деталей должно быть от 2 до 6'

    for q in parts:
        if q.get('shape') not in SHAPES or q.get('tone') not in TONES:
            return 'неизвестная форма или роль цвета'
        for key in ('w', 'h', 'd'):
            if not (MIN_SIZE <= q.get(key, 0) <= 1.0):
                return 'деталь вырожденного размера'
        if abs(q['x']) + q['w'] / 2 > MAX_REACH or abs(q['z']) + q['d'] / 2 > MAX_REACH:
            return 'предмет вылезает за свою клетку'
        if q['y'] < -1e-6 or q['y'] + q['h'] > MAX_HEIGHT:
            return 'предмет уходит под землю или слишком высок'

    if not any(q['y'] <= 0.05 for q in parts):
        return 'предмет висит в воздухе'

    # Связность по вокселям, а не по габаритам. Первая версия сравнивала
    # ограничивающие коробки — и пропускала предметы, у которых сфера
    # висела в воздухе: свою коробку сфера не заполняет, коробки касались,
    # а тела нет. В каталоге это было видно сразу.
    g = voxels(prop)
    if not g.any():
        return 'предмет почти невидим'
    if not _single_body(g):
        return 'детали не связаны друг с другом'

    if volume(prop) < 0.012:
        return 'предмет почти невидим'
    return None


# ─────────────────────────────────────────────────────────────
# Замеры формы
# ─────────────────────────────────────────────────────────────

def volume(prop):
    v = 0.0
    for q in prop['parts']:
        if q['shape'] == 'box':
            v += q['w'] * q['h'] * q['d']
        elif q['shape'] == 'sphere':
            v += math.pi / 6 * q['w'] * q['h'] * q['d']
        elif q['shape'] == 'cone':
            v += math.pi / 12 * q['w'] * q['d'] * q['h']
        elif q['shape'] == 'torus':
            v += 0.35 * q['w'] * q['h'] * q['d']
        else:
            v += math.pi / 4 * q['w'] * q['d'] * q['h']
    return v


def voxels(prop, n=VOX):
    """Грубая вокселизация в куб n³ над областью предмета."""
    grid = np.zeros((n, n, n), dtype=bool)
    xs = (np.arange(n) + 0.5) / n * 2 * MAX_REACH - MAX_REACH
    ys = (np.arange(n) + 0.5) / n * MAX_HEIGHT
    zs = (np.arange(n) + 0.5) / n * 2 * MAX_REACH - MAX_REACH
    X, Y, Z = np.meshgrid(xs, ys, zs, indexing='ij')

    for q in prop['parts']:
        dx = (X - q['x']) / max(q['w'] / 2, 1e-6)
        dz = (Z - q['z']) / max(q['d'] / 2, 1e-6)
        dy = (Y - q['y']) / max(q['h'], 1e-6)
        inside_y = (dy >= 0) & (dy <= 1)
        if q['shape'] == 'box':
            m = (np.abs(dx) <= 1) & (np.abs(dz) <= 1) & inside_y
        elif q['shape'] == 'sphere':
            c = (Y - q['y'] - q['h'] / 2) / max(q['h'] / 2, 1e-6)
            m = (dx ** 2 + dz ** 2 + c ** 2) <= 1
        elif q['shape'] == 'cone':
            r = np.clip(1 - dy, 0, 1)
            m = (dx ** 2 + dz ** 2) <= np.maximum(r, 1e-6) ** 2
            m &= inside_y
        elif q['shape'] == 'torus':
            rr = np.sqrt(dx ** 2 + dz ** 2)
            c = (Y - q['y'] - q['h'] / 2) / max(q['h'] / 2, 1e-6)
            m = ((rr - 0.7) ** 2 + c ** 2 * 0.25) <= 0.09
        else:
            m = (dx ** 2 + dz ** 2 <= 1) & inside_y
        grid |= m
    return grid


def descriptor(prop):
    """Оси архива: во что предмет вырос и насколько он раскидист."""
    g = voxels(prop)
    filled = g.sum()
    if not filled:
        return {'height': 0.0, 'width': 0.0, 'parts': len(prop['parts'])}
    ys = np.where(g.any(axis=(0, 2)))[0]
    height = (ys.max() + 1) / VOX
    cols = g.any(axis=1)
    width = math.sqrt(cols.sum() / (VOX * VOX))
    return {'height': round(float(height), 3),
            'width': round(float(width), 3),
            'parts': len(prop['parts'])}


def quality(prop):
    """Насколько предмет читается силуэтом."""
    g = voxels(prop)
    if not g.any():
        return 0.0

    # 1. Силуэт меняется по высоте
    per_level = g.sum(axis=(0, 2)).astype(float)
    live = per_level[per_level > 0]
    if len(live) < 2:
        return 0.0
    rel = live / live.max()
    variety = float(np.clip(rel.std() * 2.6, 0, 1))

    # 2. Устойчивость: основание не уже верхушки
    half = max(1, len(live) // 2)
    base, top = live[:half].mean(), live[half:].mean()
    stability = float(np.clip(base / max(top, 1e-6) / 2.0, 0, 1))

    # 3. Читаемая сложность
    n = len(prop['parts'])
    complexity = 1.0 - abs(n - 3.5) / 4.0

    # 4. Заметность: слишком тощий предмет теряется в кадре
    presence = float(np.clip(g.sum() / (VOX ** 3) * 12.0, 0, 1))

    # 5. Контраст с постройкой. Предмет цвета стены зритель не увидит,
    # каким бы удачным ни был его силуэт — а значит, и смысла в нём нет.
    vis = sum(1 for q in prop['parts'] if q['tone'] in ('accent', 'light'))
    contrast = float(np.clip(vis / max(len(prop['parts']), 1) * 2.0, 0, 1))

    return round(0.28 * variety + 0.18 * stability + 0.16 * complexity
                 + 0.16 * presence + 0.22 * contrast, 4)


def silhouette(prop):
    """Плоский силуэт для сравнения предметов между собой."""
    return voxels(prop).any(axis=2).astype(np.float32).ravel()


def distance(a, b):
    sa, sb = silhouette(a), silhouette(b)
    inter = float((sa * sb).sum())
    union = float(((sa + sb) > 0).sum())
    return 1.0 - inter / union if union else 1.0


# ─────────────────────────────────────────────────────────────
# Пул изобретений
# ─────────────────────────────────────────────────────────────

def register(name, prop):
    INVENTED[name] = prop
    return name


def names():
    return sorted(INVENTED)


def save(path=INVENTED_PATH):
    tmp = path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump([{'name': n, **INVENTED[n]} for n in sorted(INVENTED)],
                  f, ensure_ascii=False)
    try:
        os.replace(tmp, path)
    except OSError:
        pass            # файл держит работающий сервер — не беда
    return path


def load(path=INVENTED_PATH):
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding='utf-8') as f:
            rows = json.load(f)
    except (OSError, json.JSONDecodeError):
        return []
    INVENTED.clear()
    for r in rows:
        INVENTED[r['name']] = {'parts': r['parts']}
    return names()


def invent(rng, tries=60):
    """Придумать один валидный предмет."""
    for _ in range(tries):
        base = INVENTED[rng.choice(names())] if (names() and rng.random() < 0.5) else None
        p = propose(rng, base)
        if validate(p) is None:
            return p
    return None

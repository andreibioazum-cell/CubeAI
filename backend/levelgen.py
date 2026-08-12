"""Генератор осмысленных карт."""

import random
from collections import deque

import numpy as np

import props

from modules import (
    MODULES, VARIANTS, TILE, SIDES, DELTA, OPPOSITE,
    variants_with_socket, rotate_cell, sockets,
)

# ─────────────────────────────────────────────────────────────
# Стили: характер локации в числах
# ─────────────────────────────────────────────────────────────
# weights   — насколько охотно берётся модуль
# branching — 0 длинные линейные ветки, 1 густое ветвление
# symmetry  — >= 0.5 карта строится зеркально относительно оси входа
# verticality — высота стен
# size      — целевое число модулей

STYLES = {
    'city': {
        'name': 'Город',
        'palette': {'wall': '#8a8f9c', 'floor': '#4a4e58', 'accent': '#d8b45a'},
        'weights': {'corridor': 1.4, 'turn': 1.0, 'tee': 1.2, 'cross': 1.6,
                    'room_small': 0.3, 'room_large': 0.2, 'tower': 0.5,
                    'dead_end': 0.4, 'arena': 0.0, 'yard': 0.3,
                    'block': 3.2, 'block_corner': 2.4, 'avenue': 2.6,
                    'plaza': 1.2, 'park': 1.4},
        'branching': 0.7, 'symmetry': 0.15, 'verticality': 0.75, 'size': 46,
        'props': {'outdoor': 'tree', 'feature': 'statue', 'density': 0.45,
                  'any': ['lantern', 'flag', 'barrel', 'statue', 'bush']},
        'moods': [('утреннее', '#4a6fa5'), ('пасмурное', '#5c6b80'), ('закатное', '#c96f4a')],
    },
    'cave': {
        'name': 'Пещера',
        'palette': {'wall': '#4a3f5c', 'floor': '#2f2a3a', 'accent': '#7b5fa8'},
        'weights': {'corridor': 3.0, 'turn': 3.5, 'tee': 1.2, 'cross': 0.4,
                    'room_small': 1.0, 'room_large': 0.5, 'tower': 0.2,
                    'dead_end': 1.6, 'arena': 0.0, 'yard': 0.2,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0, 'plaza': 0.0, 'park': 0.0},
        'branching': 0.55, 'symmetry': 0.0, 'verticality': 0.35, 'size': 32,
        'props': {'outdoor': 'crystal', 'feature': 'crystal', 'density': 0.35,
                  'any': ['crystal', 'lantern', 'barrel', 'chest']},
        'moods': [('мрачное', '#2e2a52'), ('глухое', '#3d3470'), ('светлое', '#5b4b9e')],
    },
    'castle': {
        'name': 'Замок',
        'palette': {'wall': '#8c8c96', 'floor': '#5a5a66', 'accent': '#c9a227'},
        'weights': {'corridor': 2.0, 'turn': 1.0, 'tee': 1.5, 'cross': 1.0,
                    'room_small': 1.5, 'room_large': 2.5, 'tower': 2.0,
                    'dead_end': 0.4, 'arena': 0.3, 'yard': 0.5,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0, 'plaza': 0.0, 'park': 0.0},
        'branching': 0.35, 'symmetry': 0.9, 'verticality': 0.75, 'size': 26,
        'props': {'outdoor': 'tree', 'feature': 'statue', 'density': 0.3,
                  'any': ['statue', 'flag', 'barrel', 'lantern', 'chest']},
        'moods': [('грозовое', '#3a4260'), ('сумеречное', '#5061a0'), ('парадное', '#7a92d4')],
    },
    'mansion': {
        'name': 'Особняк',
        'palette': {'wall': '#8a5a3c', 'floor': '#c8a97e', 'accent': '#d94f8a'},
        'weights': {'corridor': 3.0, 'turn': 1.5, 'tee': 2.0, 'cross': 0.8,
                    'room_small': 3.5, 'room_large': 2.0, 'tower': 0.4,
                    'dead_end': 0.8, 'arena': 0.0, 'yard': 0.3,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0, 'plaza': 0.0, 'park': 0.0},
        'branching': 0.5, 'symmetry': 0.5, 'verticality': 0.45, 'size': 30,
        'props': {'outdoor': 'tree', 'feature': 'statue', 'density': 0.32,
                  'any': ['statue', 'lantern', 'barrel', 'bush', 'chest']},
        'moods': [('тревожное', '#5c3a3a'), ('уютное', '#a06848'), ('тёплое', '#d99055')],
    },
    'island': {
        'name': 'Остров',
        'palette': {'wall': '#4e9d5a', 'floor': '#d9c48a', 'accent': '#2f8fd0'},
        'weights': {'corridor': 1.0, 'turn': 1.5, 'tee': 1.0, 'cross': 0.8,
                    'room_small': 0.8, 'room_large': 0.8, 'tower': 0.6,
                    'dead_end': 1.5, 'arena': 0.2, 'yard': 4.0,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0, 'plaza': 0.0, 'park': 0.0},
        'branching': 0.65, 'symmetry': 0.0, 'verticality': 0.35, 'size': 28,
        'props': {'outdoor': 'tree', 'feature': 'tent', 'density': 0.26,
                  'any': ['tree', 'bush', 'barrel', 'chest', 'lantern']},
        'moods': [('штормовое', '#3d6580'), ('ясное', '#4fb0e0'), ('закатное', '#e88a5a')],
    },
    'circus': {
        'name': 'Цирк',
        'palette': {'wall': '#d93b3b', 'floor': '#f2e7d5', 'accent': '#ffd23f'},
        'weights': {'corridor': 2.0, 'turn': 0.8, 'tee': 1.5, 'cross': 2.0,
                    'room_small': 1.0, 'room_large': 1.5, 'tower': 1.5,
                    'dead_end': 0.6, 'arena': 4.0, 'yard': 1.0,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0, 'plaza': 0.0, 'park': 0.0},
        'branching': 0.75, 'symmetry': 0.95, 'verticality': 0.8, 'size': 26,
        'props': {'outdoor': 'tent', 'feature': 'tent', 'density': 0.2,
                  'any': ['flag', 'lantern', 'tent', 'barrel', 'chest']},
        'moods': [('зловещее', '#6b1f45'), ('праздничное', '#b8306b'), ('карнавальное', '#e8508f')],
    },
    'candy': {
        'name': 'Королевство сладостей',
        'palette': {'wall': '#ff9ecb', 'floor': '#fff0f6', 'accent': '#7ad7f0'},
        'weights': {'corridor': 1.5, 'turn': 3.0, 'tee': 1.5, 'cross': 0.8,
                    'room_small': 1.5, 'room_large': 1.0, 'tower': 3.0,
                    'dead_end': 1.5, 'arena': 0.5, 'yard': 2.0,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0, 'plaza': 0.0, 'park': 0.0},
        'branching': 0.6, 'symmetry': 0.3, 'verticality': 0.55, 'size': 26,
        'props': {'outdoor': 'lollipop', 'feature': 'lollipop', 'density': 0.5,
                  'any': ['lollipop', 'bush', 'lantern', 'chest', 'tree']},
        'moods': [('приторное', '#8a4ba8'), ('нежное', '#d47ac0'), ('сахарное', '#f2a0d8')],
    },
}

INVENTED_PROP_RATE = 0.45   # какая доля слотов достаётся изобретённому
MAP_W, MAP_H = 13, 13        # размер карты в модулях (78×78 клеток)
MAX_HEIGHT = 9

# Базовый множитель высоты стен. При старом значении стены выходили
# в 1–2 блока и карта читалась как плоский чертёж, а не как постройка.
HEIGHT_BASE = 2.5


# ─────────────────────────────────────────────────────────────
# Смешивание стилей
# ─────────────────────────────────────────────────────────────

def _mix_hex(a, b, t):
    ca = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
    cb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
    return '#%02x%02x%02x' % tuple(round(x + (y - x) * t) for x, y in zip(ca, cb))


def style_mix(style):
    """Из каких базовых стилей собран этот, и в каких долях."""
    mix = style.get('mix')
    if mix:
        total = sum(mix.values()) or 1.0
        return {k: round(v / total, 4) for k, v in mix.items() if v > 0.01}
    # Карты, сложенные до появления этого поля, состав не хранят — но
    # хранят родословную в имени. Разбираем её: «Пещера × Цирк» это
    # половина одного и половина другого.
    by_name = {base['name']: key for key, base in STYLES.items()}
    parts = [p.strip() for p in str(style.get('name', '')).split('×')]
    found = [by_name[p] for p in parts if p in by_name]
    if not found:
        return {}
    share = 1.0 / len(found)
    out = {}
    for k in found:
        out[k] = round(out.get(k, 0.0) + share, 4)
    return out


def _mix_maps(ma, mb, t):
    keys = set(ma) | set(mb)
    out = {k: ma.get(k, 0.0) * (1 - t) + mb.get(k, 0.0) * t for k in keys}
    total = sum(out.values()) or 1.0
    return {k: round(v / total, 4) for k, v in out.items() if v > 0.01}


def blend_styles(a, b, t=0.5, name=None):
    """Полу-A-полу-B: параметры интерполируются, палитра смешивается."""
    sa, sb = STYLES[a], STYLES[b]
    return {
        'mix': _mix_maps(style_mix(sa), style_mix(sb), t),
        'name': name or f'{sa["name"]} × {sb["name"]}',
        'palette': {k: _mix_hex(sa['palette'][k], sb['palette'][k], t)
                    for k in sa['palette']},
        'weights': {k: sa['weights'].get(k, 0.0) * (1 - t)
                       + sb['weights'].get(k, 0.0) * t
                    for k in set(sa['weights']) | set(sb['weights'])},
        'branching':   sa['branching'] * (1 - t) + sb['branching'] * t,
        'symmetry':    sa['symmetry'] * (1 - t) + sb['symmetry'] * t,
        'verticality': sa['verticality'] * (1 - t) + sb['verticality'] * t,
        'size':  round(sa['size'] * (1 - t) + sb['size'] * t),
        # у гибрида набор реквизита и палитра неба берутся от обоих родителей
        'props': {
            'outdoor': (sa if t < 0.5 else sb)['props']['outdoor'],
            'feature': (sa if t < 0.5 else sb)['props']['feature'],
            'density': sa['props']['density'] * (1 - t) + sb['props']['density'] * t,
            'any': sorted(set(sa['props']['any']) | set(sb['props']['any'])),
        },
        # Настроение неба у гибрида НЕ усредняется по цвету: розовое
        # с бирюзовым в среднем дают серость, и все гибриды получали
        # одинаково унылое серо-лиловое небо. Берётся небо того родителя,
        # чья доля больше — так у гибрида сохраняется характер.
        'moods': [(f'{ma[0]}/{mb[0]}', mb[1] if t > 0.5 else ma[1])
                  for ma, mb in zip(sa['moods'], sb['moods'])],
    }


# ─────────────────────────────────────────────────────────────
# Уровень
# ─────────────────────────────────────────────────────────────

class Level:
    def __init__(self, style, tiles, gate, w, h, rng=None):
        self.style = style
        self.tiles = tiles          # (tx,ty) -> {'name','grid','style'}
        self.gate = gate
        self.w, self.h = w, h
        self.rng = rng or random.Random()
        self.mood = None            # настроение постройки → цвет неба
        self.sky = '#111111'
        self.roles = None           # np.array (h*TILE, w*TILE) кодов клеток
        self.blueprint = []         # что и где строить
        self.decorations = []
        self.descriptor = {}

    # ── сборка сетки клеток ──────────────────────────────────
    def assemble(self):
        self.roles = np.ones((self.h * TILE, self.w * TILE), dtype=np.int8)
        self.styles_at = {}
        for (tx, ty), t in self.tiles.items():
            self.roles[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE] = t['grid']
            self.styles_at[(tx, ty)] = t['style']
        # клетки вне построенных модулей — не стены, а пустота
        mask = np.zeros_like(self.roles, dtype=bool)
        for (tx, ty) in self.tiles:
            mask[ty * TILE:(ty + 1) * TILE, tx * TILE:(tx + 1) * TILE] = True
        self.roles[~mask] = -1      # -1 = ничего не строим

    def seal(self):
        """Заглушить двери, ведущие в никуда."""
        for (tx, ty), t in self.tiles.items():
            grid = t['grid']
            for side in SIDES:
                if side not in sockets(grid):
                    continue
                if (tx, ty) == self.gate and side == t['outer']:
                    continue        # наружная дверь входа остаётся открытой
                dx, dy = DELTA[side]
                nb = self.tiles.get((tx + dx, ty + dy))
                if nb is not None and OPPOSITE[side] in sockets(nb['grid']):
                    continue        # стыковка есть, всё хорошо
                if side == 'N':   grid[0, :] = np.where(grid[0, :] == 0, 1, grid[0, :])
                elif side == 'S': grid[TILE - 1, :] = np.where(grid[TILE - 1, :] == 0, 1, grid[TILE - 1, :])
                elif side == 'W': grid[:, 0] = np.where(grid[:, 0] == 0, 1, grid[:, 0])
                else:             grid[:, TILE - 1] = np.where(grid[:, TILE - 1] == 0, 1, grid[:, TILE - 1])

    # ── проверки и метрики ───────────────────────────────────
    def entry_cell(self):
        tx, ty = self.gate
        return (ty * TILE + TILE - 2, tx * TILE + 2)

    def distances(self):
        """BFS по проходимым клеткам от входа."""
        H, W = self.roles.shape
        start = self.entry_cell()
        dist = {start: 0}
        q = deque([start])
        while q:
            r, c = q.popleft()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < H and 0 <= nc < W and (nr, nc) not in dist \
                        and self.roles[nr, nc] == 0:
                    dist[(nr, nc)] = dist[(r, c)] + 1
                    q.append((nr, nc))
        return dist

    def reachability(self):
        walkable = int(np.sum(self.roles == 0))
        return len(self.distances()) / walkable if walkable else 0.0

    def prune_unreachable(self):
        """Выкинуть модули, до которых нельзя дойти от входа."""
        for _ in range(3):
            reach = set(self.distances())
            drop = []
            for (tx, ty), t in self.tiles.items():
                cells = [(ty * TILE + r, tx * TILE + c)
                         for r in range(TILE) for c in range(TILE)
                         if t['grid'][r, c] == 0]
                if cells and not any(cell in reach for cell in cells):
                    drop.append((tx, ty))
            if not drop:
                break
            for k in drop:
                del self.tiles[k]
            self.assemble()
            self.seal()
            self.assemble()

    def pick_mood(self):
        """Настроение постройки задаёт цвет неба."""
        moods = self.style.get('moods') or [('обычное', '#111111')]
        d = self.descriptor
        openness = min(max((d['openness'] - 0.30) / 0.18, 0.0), 1.0)
        shallow = 1.0 - min(max((d['depth'] - 20) / 70.0, 0.0), 1.0)
        branch = min(max(d['branching'] / 0.4, 0.0), 1.0)

        score = 0.45 * openness + 0.3 * shallow + 0.25 * branch
        score += self.rng.uniform(-0.18, 0.18)
        idx = min(max(int(score * len(moods)), 0), len(moods) - 1)
        self.mood, self.sky = moods[idx]
        return self.mood

    def compute_descriptor(self):
        dist = self.distances()
        roles = [t['role'] for t in self.tiles.values()]
        built = np.sum(self.roles >= 0)
        self.descriptor = {
            'size': len(self.tiles),
            'openness': round(float(np.sum(self.roles == 0) / built), 3) if built else 0,
            'verticality': round(self.style['verticality'], 3),
            'branching': round(sum(1 for t in self.tiles.values()
                                   if len(sockets(t['grid'])) >= 3) / len(self.tiles), 3),
            'room_ratio': round(roles.count('room') / len(roles), 3),
            'dead_ends': roles.count('dead_end'),
            'depth': max(dist.values()) if dist else 0,
            'reachability': round(self.reachability(), 3),
        }
        return self.descriptor

    # ── чертёж и декор ───────────────────────────────────────
    def build_blueprint(self):
        """Чертёж: что и какого цвета должно стоять. Руки Кейна работают"""
        self.blueprint = []
        for (tx, ty), t in self.tiles.items():
            st = t['style']
            pal = st['palette']
            mh = MODULES[t['name']]['height']
            wall_h = max(2, min(MAX_HEIGHT,
                                int(round(mh * HEIGHT_BASE
                                          * (1 + 1.6 * st['verticality'])))))
            for r in range(TILE):
                for c in range(TILE):
                    role = int(t['grid'][r, c])
                    if role == 0:
                        continue
                    x = tx * TILE + c
                    z = ty * TILE + r
                    if role == 1:
                        color, height = pal['wall'], wall_h
                    elif role == 2:
                        color, height = pal['floor'], 1
                    else:
                        color, height = pal['accent'], max(1, wall_h - 1)
                    for y in range(height):
                        self.blueprint.append({'x': x, 'y': y, 'z': z,
                                               'color': color, 'role': role})
        return self.blueprint

    def _prop_record(self, name, x, z, kind):
        """Запись о предмете. У изобретённого едет описание из примитивов —"""
        rec = {'type': name, 'x': float(x), 'y': 0.0, 'z': float(z)}
        invented = props.names()
        if invented and self.rng.random() < INVENTED_PROP_RATE:
            pick = self.rng.choice(invented)
            rec['type'] = pick
            rec['spec'] = props.INVENTED[pick]['parts']
        return rec

    def place_decorations(self):
        """Декор по слотам модулей, а не по случайным координатам."""
        dist = self.distances()
        self.decorations = []
        candidates = []           # (приоритет, расстояние, x, z) для сундука

        # Тупик — лучшее место для награды, но в симметричных замках тупиков
        # может не быть вовсе, поэтому есть запасные варианты.
        PRIORITY = {'dead_end': 3, 'tower': 2, 'room': 2, 'arena': 1}

        for (tx, ty), t in self.tiles.items():
            k = t['rot']
            for (r0, c0, kind) in MODULES[t['name']]['decor']:
                r, c = rotate_cell(r0, c0, k)
                if t['grid'][r, c] != 0:
                    continue      # слот перекрыт поворотом — пропускаем
                x, z = tx * TILE + c, ty * TILE + r
                d = dist.get((z, x))
                if d is None:
                    continue      # до слота нельзя дойти
                props_of = t['style'].get('props', {})
                if kind in ('outdoor', 'feature'):
                    prop = props_of.get(kind)
                    if prop:
                        self.decorations.append(
                            self._prop_record(prop, x, z, kind))
                else:
                    candidates.append((PRIORITY.get(t['role'], 0), d, x, z,
                                       props_of))

        if candidates:
            # Сначала расстояние, потом тип модуля. Первая версия сортировала
            # наоборот, и ближний тупик всегда обыгрывал дальний зал: цель
            # оказывалась на 28% глубины карты вместо конца маршрута — то
            # есть «дойти до сундука» почти ничего не проверяло.
            far = sorted(candidates, key=lambda c: -c[1])
            cut = max(1, len(far) // 4)
            _, _, x, z, _ = max(far[:cut], key=lambda c: (c[0], c[1]))
        elif dist:
            # Карта из одних коридоров: слотов нет, но цель для гуляк
            # обязана быть — кладём в самую дальнюю точку маршрута.
            (z, x), _ = max(dist.items(), key=lambda kv: kv[1])
        else:
            return self.decorations
        self.decorations.append({'type': 'chest', 'x': float(x),
                                 'y': 0.0, 'z': float(z), 'goal': True})

        # Остальные свободные слоты обставляем реквизитом стиля: пустая
        # карта с одним сундуком выглядит нежилой.
        for _, _, cx, cz, pr in candidates[1:]:
            kinds = pr.get('any') or []
            if not kinds or self.rng.random() > pr.get('density', 0.5):
                continue
            self.decorations.append(
                self._prop_record(self.rng.choice(kinds), cx, cz, 'any'))
        return self.decorations

    # ── отладочный вывод ─────────────────────────────────────
    def to_ascii(self):
        glyph = {-1: ' ', 0: '.', 1: '#', 2: '-', 3: '+'}
        deco = {(int(d['z']), int(d['x'])): ('$' if d['type'] == 'chest' else 'T')
                for d in self.decorations}
        er, ec = self.entry_cell()
        lines = []
        for r in range(self.roles.shape[0]):
            row = ''
            for c in range(self.roles.shape[1]):
                if (r, c) == (er, ec):        row += '@'
                elif (r, c) in deco:          row += deco[(r, c)]
                else:                         row += glyph[int(self.roles[r, c])]
            if row.strip():
                lines.append(row)
        return '\n'.join(lines)


# ─────────────────────────────────────────────────────────────
# Генерация
# ─────────────────────────────────────────────────────────────

# Модули, у которых всего одно гнездо: ветка на них заканчивается.
TERMINAL = {n for n, vs in VARIANTS.items()
            if all(len(v['sockets']) == 1 for v in vs)}


def _pick_module(style, rng, exclude=()):
    names, weights = [], []
    for n, w in style['weights'].items():
        if w > 0 and n not in exclude:
            names.append(n)
            weights.append(w)
    if not names:
        return 'corridor'
    return rng.choices(names, weights=weights)[0]


def _style_at(style, tx, ty, zoned):
    """Для сшитых гибридов стиль зависит от места на карте."""
    if not zoned:
        return style
    a, b, axis = zoned
    if axis == 'z':
        return a if ty >= MAP_H // 2 else b
    return a if tx < MAP_W // 2 else b


def generate(style, seed=None, zoned=None, mirror=None):
    """Вырастить карту от входа."""
    rng = random.Random(seed)
    base = style
    symmetric = base['symmetry'] >= 0.5 if mirror is None else mirror

    cx = MAP_W // 2
    limit_x = cx if symmetric else MAP_W - 1   # при симметрии строим половину

    tiles = {}
    gate = (cx, MAP_H - 1)
    gate_st = _style_at(base, *gate, zoned)
    gv = VARIANTS['gate'][0]
    tiles[gate] = {'name': 'gate', 'rot': gv['rot'], 'grid': gv['grid'].copy(),
                   'role': 'gate', 'style': gate_st, 'outer': 'S'}

    frontier = [(gate[0], gate[1], 'N')]
    target = base['size']

    while frontier and len(tiles) < target:
        # ветвистость: при низкой берём последнее гнездо (длинные ветки),
        # при высокой — случайное (карта кустится)
        idx = -1 if rng.random() > base['branching'] else rng.randrange(len(frontier))
        tx, ty, side = frontier.pop(idx)
        dx, dy = DELTA[side]
        nx, ny = tx + dx, ty + dy

        if not (0 <= nx <= limit_x and 0 <= ny < MAP_H) or (nx, ny) in tiles:
            continue

        st = _style_at(base, nx, ny, zoned)
        need = OPPOSITE[side]

        remaining = target - len(tiles)
        if remaining <= 2:
            # к концу охотнее закрываем ветки, чем плодим новые
            exclude = ('cross', 'tee')
        elif not frontier:
            # это последняя открытая дверь: тупик здесь убил бы карту
            exclude = tuple(TERMINAL)
        else:
            exclude = ()
        for _ in range(8):
            name = _pick_module(st, rng, exclude)
            opts = variants_with_socket(name, need)
            if opts:
                v = rng.choice(opts)
                tiles[(nx, ny)] = {'name': name, 'rot': v['rot'],
                                   'grid': v['grid'].copy(),
                                   'role': MODULES[name]['role'], 'style': st,
                                   'outer': None}
                for s in v['sockets']:
                    if s != need:
                        frontier.append((nx, ny, s))
                break

    if symmetric:
        _mirror(tiles, cx)

    level = Level(base, tiles, gate, MAP_W, MAP_H, rng=rng)
    level.assemble()
    level.seal()
    level.assemble()          # пересобрать после заглушек
    level.prune_unreachable()  # страховка: до каждого модуля можно дойти
    level.build_blueprint()
    level.compute_descriptor()
    level.pick_mood()
    level.place_decorations()
    return level


def _mirror(tiles, cx):
    """Отразить построенную половину относительно оси входа."""
    # Флаги sym/flip нужны, чтобы карту можно было точно разложить в геном
    # и собрать обратно: после зеркалирования сетка тайла уже не совпадает
    # ни с одним поворотом из словаря.
    for (tx, ty), t in tiles.items():
        if tx == cx:
            g = t['grid']
            fl = np.fliplr(g)
            t['grid'] = np.where((g == 0) | (fl == 0), 0, g).astype(np.int8)
            t['sym'] = True

    for (tx, ty), t in list(tiles.items()):
        if tx >= cx:
            continue
        mx = 2 * cx - tx
        if (mx, ty) in tiles:
            continue
        tiles[(mx, ty)] = {**t, 'grid': np.fliplr(t['grid']).copy(),
                           'flip': not t.get('flip', False)}


# ─────────────────────────────────────────────────────────────
# Разнообразие: Кейн не должен строить одно и то же
# ─────────────────────────────────────────────────────────────

_MEMORY = deque(maxlen=12)
_DESC_KEYS = ('openness', 'branching', 'room_ratio', 'depth', 'size')


def _vec(desc):
    return np.array([desc['openness'], desc['branching'], desc['room_ratio'],
                     desc['depth'] / 60.0, desc['size'] / 20.0], dtype=float)


def novelty(desc):
    """Насколько карта не похожа на последние построенные."""
    if not _MEMORY:
        return 1.0
    v = _vec(desc)
    return float(min(np.linalg.norm(v - m) for m in _MEMORY))


def generate_novel(style, seed=None, tries=12, min_novelty=0.12, **kw):
    """Перебирать варианты, пока карта не окажется достаточно непохожей"""
    rng = random.Random(seed)
    best, best_n = None, -1.0
    fallback, fallback_size = None, -1
    min_size = max(4, int(style['size'] * 0.6))
    for _ in range(tries):
        lv = generate(style, seed=rng.randrange(10 ** 9), **kw)
        # запасной вариант выбираем по размеру среди проходимых, а не
        # первый попавшийся: иначе на выход может уйти непроверенная карта
        if lv.descriptor['reachability'] >= 0.99 and lv.descriptor['size'] > fallback_size:
            fallback, fallback_size = lv, lv.descriptor['size']
        if lv.descriptor['reachability'] < 0.99 or lv.descriptor['size'] < min_size:
            continue
        n = novelty(lv.descriptor)
        if n > best_n:
            best, best_n = lv, n
        if n >= min_novelty:
            break
    if best is None:
        best = fallback or generate(style, seed=rng.randrange(10 ** 9), **kw)
        best_n = novelty(best.descriptor)
    _MEMORY.append(_vec(best.descriptor))
    best.novelty = round(best_n, 3)
    return best

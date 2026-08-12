"""Геном карты и операторы эволюции."""

import copy
import random

import numpy as np

from modules import (
    MODULES, VARIANTS, TILE, SIDES, DELTA, OPPOSITE, sockets,
)
from levelgen import Level, STYLES, MAP_W, MAP_H, _mix_hex

def buildable():
    """Чем можно достраивать. Считается каждый раз, а не один раз при"""
    return [n for n in MODULES if n != 'gate']


def variant_grid(name, rot, flip=False, sym=False):
    """Сетка тайла по его гену. Всегда собирается заново из словаря,"""
    grid = None
    for v in VARIANTS[name]:
        if v['rot'] == rot:
            grid = v['grid']
            break
    if grid is None:
        v = VARIANTS[name][0]
        grid, rot = v['grid'], v['rot']
    g = grid.copy()
    if sym:
        fl = np.fliplr(g)
        g = np.where((g == 0) | (fl == 0), 0, g).astype(np.int8)
    if flip:
        g = np.fliplr(g).copy()
    return g


def gene_sockets(gene):
    return sockets(variant_grid(gene['name'], gene['rot'],
                                gene.get('flip', False), gene.get('sym', False)))


def variants_for(name, need_side, rng):
    """Повороты модуля, у которых есть гнездо в нужную сторону (с учётом"""
    out = []
    for v in VARIANTS[name]:
        for flip in (False, True):
            g = variant_grid(name, v['rot'], flip=flip)
            if need_side in sockets(g):
                out.append({'name': name, 'rot': v['rot'], 'flip': flip,
                            'sym': False})
    rng.shuffle(out)
    return out


class Genome:
    def __init__(self, tiles, gate, style):
        self.tiles = tiles          # (tx,ty) -> {'name','rot','flip','sym'}
        self.gate = gate
        self.style = style

    # ── превращение в карту ──────────────────────────────────
    def decode(self, seed=None):
        """Геном → готовая карта. Здесь же происходит починка."""
        rng = random.Random(seed)
        tiles = {}
        for pos, g in self.tiles.items():
            tiles[pos] = {
                'name': g['name'], 'rot': g['rot'],
                'flip': g.get('flip', False), 'sym': g.get('sym', False),
                'grid': variant_grid(g['name'], g['rot'],
                                     g.get('flip', False), g.get('sym', False)),
                'role': MODULES[g['name']]['role'],
                'style': self.style,
                'outer': 'S' if pos == self.gate else None,
            }
        lv = Level(self.style, tiles, self.gate, MAP_W, MAP_H, rng=rng)
        lv.assemble()
        lv.seal()
        lv.assemble()
        lv.prune_unreachable()
        if self.gate not in lv.tiles or len(lv.tiles) < 4:
            return None
        lv.build_blueprint()
        lv.compute_descriptor()
        lv.pick_mood()
        lv.place_decorations()
        lv.novelty = 0.0
        # синхронизируем геном с тем, что пережило починку
        self.tiles = {p: self.tiles[p] for p in lv.tiles if p in self.tiles}
        return lv

    # ── сохранение ───────────────────────────────────────────
    def to_dict(self):
        return {
            'gate': list(self.gate),
            'tiles': [[list(p), g['name'], g['rot'],
                       int(g.get('flip', False)), int(g.get('sym', False))]
                      for p, g in self.tiles.items()],
            'style': {
                'name': self.style['name'],
                'roots': self.style.get('roots'),
                'palette': self.style['palette'],
                'verticality': self.style['verticality'],
                'props': self.style['props'],
                'moods': [list(m) for m in self.style['moods']],
            },
        }

    @staticmethod
    def from_dict(d):
        style = copy.deepcopy(STYLES['cave'])
        style.update(d['style'])
        style['moods'] = [tuple(m) for m in d['style']['moods']]
        tiles = {tuple(p): {'name': n, 'rot': r, 'flip': bool(f), 'sym': bool(s)}
                 for p, n, r, f, s in d['tiles']}
        return Genome(tiles, tuple(d['gate']), style)

    def copy(self):
        return Genome({p: dict(g) for p, g in self.tiles.items()},
                      self.gate, copy.deepcopy(self.style))

    @staticmethod
    def from_level(level):
        """Разложить сгенерированную грамматикой карту в геном — так"""
        tiles = {p: {'name': t['name'], 'rot': t['rot'],
                     'flip': bool(t.get('flip', False)),
                     'sym': bool(t.get('sym', False))}
                 for p, t in level.tiles.items()}
        return Genome(tiles, level.gate, copy.deepcopy(level.style))


# ─────────────────────────────────────────────────────────────
# Мутации
# ─────────────────────────────────────────────────────────────

def _free_sockets(gm):
    """Свободные двери: гнездо есть, а соседней клетки нет."""
    out = []
    for pos, gene in gm.tiles.items():
        for side in gene_sockets(gene):
            dx, dy = DELTA[side]
            nb = (pos[0] + dx, pos[1] + dy)
            if nb in gm.tiles:
                continue
            if 0 <= nb[0] < MAP_W and 0 <= nb[1] < MAP_H:
                out.append((pos, side, nb))
    return out


def mut_add(gm, rng):
    """Пристроить модуль к свободной двери."""
    spots = _free_sockets(gm)
    if not spots:
        return False
    _, side, nb = rng.choice(spots)
    need = OPPOSITE[side]
    names = buildable()
    for name in rng.sample(names, len(names)):
        opts = variants_for(name, need, rng)
        if opts:
            gm.tiles[nb] = opts[0]
            return True
    return False


def mut_remove(gm, rng):
    """Убрать модуль. Отрезанное починка выкинет сама."""
    cand = [p for p in gm.tiles if p != gm.gate]
    if len(cand) < 5:
        return False
    del gm.tiles[rng.choice(cand)]
    return True


def mut_replace(gm, rng):
    """Заменить модуль другим типом."""
    cand = [p for p in gm.tiles if p != gm.gate]
    if not cand:
        return False
    pos = rng.choice(cand)
    name = rng.choice(buildable())
    v = rng.choice(VARIANTS[name])
    gm.tiles[pos] = {'name': name, 'rot': v['rot'],
                     'flip': rng.random() < 0.5, 'sym': False}
    return True


def mut_rotate(gm, rng):
    """Повернуть или отразить модуль."""
    cand = [p for p in gm.tiles if p != gm.gate]
    if not cand:
        return False
    pos = rng.choice(cand)
    g = gm.tiles[pos]
    v = rng.choice(VARIANTS[g['name']])
    gm.tiles[pos] = {'name': g['name'], 'rot': v['rot'],
                     'flip': rng.random() < 0.5, 'sym': g.get('sym', False)}
    return True


def mut_grow(gm, rng, n=None):
    """Отрастить ветку: несколько модулей подряд от свободной двери."""
    n = n or rng.randint(2, 5)
    ok = False
    for _ in range(n):
        if not mut_add(gm, rng):
            break
        ok = True
    return ok


def mut_prune_branch(gm, rng):
    """Отрезать хвост: убрать тайл с одной связью и его соседей по цепочке."""
    for _ in range(6):
        cand = [p for p in gm.tiles if p != gm.gate]
        if len(cand) < 6:
            return False
        pos = rng.choice(cand)
        del gm.tiles[pos]
        if rng.random() < 0.5:
            break
    return True


PALETTE_FLOOR = 70          # минимально допустимая различимость цветов
SATURATION_FLOOR = 0.26     # минимальная живость цвета


def palette_saturation(pal):
    """Насколько цвета живые, а не серые."""
    out = []
    for k in ('wall', 'floor', 'accent'):
        h = pal[k].lstrip('#')
        c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
        out.append(max(c) - min(c))
    return sum(out) / len(out)


def saturate(pal, target=SATURATION_FLOOR):
    """Поднять живость цвета, не трогая светлоту: каждый канал отодвигается"""
    cur = palette_saturation(pal)
    if cur >= target or cur <= 1e-6:
        return dict(pal)
    k = min(3.0, target / cur)
    out = {}
    for name in ('wall', 'floor', 'accent'):
        h = pal[name].lstrip('#')
        c = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        m = sum(c) / 3
        c = [max(0, min(255, round(m + (x - m) * k))) for x in c]
        out[name] = '#%02x%02x%02x' % tuple(c)
    return out


def palette_contrast(pal):
    """Насколько различимы стена, пол и акцент между собой."""
    c = [tuple(int(pal[k][i:i + 2], 16) for i in (1, 3, 5))
         for k in ('wall', 'floor', 'accent')]
    return min(sum(abs(a - b) for a, b in zip(c[i], c[j]))
               for i in range(3) for j in range(i + 1, 3))


def _palette_ok(new, old):
    """Смешивание цветов сходится к среднему, и за десятки поколений палитра"""
    cn, co = palette_contrast(new), palette_contrast(old)
    if not (cn >= PALETTE_FLOOR or cn >= co * 0.9):
        return False
    sn, so = palette_saturation(new), palette_saturation(old)
    return sn >= SATURATION_FLOOR or sn >= so * 0.95


def mut_palette(gm, rng):
    """Сдвинуть цвета. Палитра — часть облика, её тоже эволюционируем."""
    pal = gm.style['palette']
    slot = rng.choice(['wall', 'floor', 'accent'])
    other = rng.choice(list(STYLES.values()))['palette']
    new = dict(pal)
    new[slot] = _mix_hex(pal[slot], other[slot], rng.uniform(0.2, 0.6))
    if not _palette_ok(new, pal):
        return False
    gm.style = copy.deepcopy(gm.style)
    gm.style['palette'] = new
    return True


def mut_verticality(gm, rng):
    gm.style = copy.deepcopy(gm.style)
    v = gm.style['verticality'] + rng.uniform(-0.25, 0.25)
    gm.style['verticality'] = float(min(1.0, max(0.05, v)))
    return True


OPERATORS = [
    (mut_add, 3.0), (mut_grow, 2.5), (mut_replace, 3.0), (mut_rotate, 2.0),
    (mut_remove, 1.5), (mut_prune_branch, 1.0),
    (mut_palette, 1.0), (mut_verticality, 1.0),
]


def mutate(gm, rng, k=None):
    """Применить одну-три мутации к копии генома."""
    child = gm.copy()
    ops = [o for o, _ in OPERATORS]
    w = [x for _, x in OPERATORS]
    for _ in range(k or rng.choice([1, 1, 2, 3])):
        op = rng.choices(ops, weights=w)[0]
        op(child, rng)
    return child


def crossover(a, b, rng):
    """Взять область карты у одного родителя, остальное у другого."""
    axis = rng.choice([0, 1])
    thr = rng.randrange(1, MAP_W - 1)
    tiles = {}
    for pos, g in a.tiles.items():
        if pos[axis] <= thr:
            tiles[pos] = dict(g)
    for pos, g in b.tiles.items():
        if pos[axis] > thr and pos not in tiles:
            tiles[pos] = dict(g)
    tiles[a.gate] = dict(a.tiles[a.gate])

    style = copy.deepcopy(a.style if rng.random() < 0.5 else b.style)
    t = rng.uniform(0.3, 0.7)
    mixed = {k: _mix_hex(a.style['palette'][k], b.style['palette'][k], t)
             for k in style['palette']}
    # Смешанная палитра берётся, только если родительские цвета не слились
    # в кашу; иначе потомок наследует палитру одного из родителей целиком.
    if (palette_contrast(mixed) >= PALETTE_FLOOR
            and palette_saturation(mixed) >= SATURATION_FLOOR):
        style['palette'] = mixed
    style['verticality'] = (a.style['verticality'] * (1 - t)
                            + b.style['verticality'] * t)
    # Состав текстур смешивается вместе с палитрой и по тому же t: иначе
    # у гибрида цвета от обоих родителей, а фактура — от одного.
    from levelgen import style_mix, _mix_maps
    style['mix'] = _mix_maps(style_mix(a.style), style_mix(b.style), t)

    # Родословная хранится списком и обрезается: иначе после десятка
    # скрещиваний имя разрастается в «Особняк × Замок × Пещера × Особняк × ...»
    roots = list(dict.fromkeys(_roots(a.style) + _roots(b.style)))[:2]
    style['roots'] = roots
    style['name'] = ' × '.join(roots)
    return Genome(tiles, a.gate, style)


def _roots(style):
    r = style.get('roots')
    if r:
        return list(r)
    return [n.strip() for n in style.get('name', '').split('×')][:2]

#qpy:webapp:CaineAI
#qpy://127.0.0.1:8080/
# -*- coding: utf-8 -*-
"""CaineAI для телефона: Кейн и Авель строят и судятся.

Один файл. Запускается в QPython (или обычным Python 3): поднимает
HTTP-сервер, отдаёт соседний index.html и считает карты. Никакого
numpy, FastAPI и архивов — грамматика, руки, наивные гуляки и дуэль.
"""
from __future__ import print_function

import json
import math
import os
import random
import sys
import threading
import time
from collections import Counter, deque

try:
    from urllib.parse import parse_qs, urlparse
except ImportError:
    from urlparse import parse_qs, urlparse

try:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from socketserver import ThreadingMixIn
except ImportError:
    from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
    from SocketServer import ThreadingMixIn


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass


HERE = os.path.dirname(os.path.abspath(__file__))
PORT = int(os.environ.get('CAINE_PORT', '8080'))
HOST = os.environ.get('CAINE_HOST', '0.0.0.0')

# На телефоне карта меньше и строится быстрее: полный 78×78 на слабом
# процессоре занимает минуты ещё до первого кадра.
TEMPO_MS = int(os.environ.get('CAINE_TEMPO', '80'))
TARGET_FRAMES = int(os.environ.get('CAINE_FRAMES', '420'))
AUTO_ADVANCE = os.environ.get('CAINE_AUTO', '0') == '1'
STYLE_CHOICE = os.environ.get('CAINE_STYLE', 'random').lower()
DUEL_ON = os.environ.get('CAINE_DUEL', '1').lower() in ('1', 'true', 'yes', 'on')
MATCH_ROUNDS = 5
MARGIN = 0.004

TILE = 6
MAP_W, MAP_H = 9, 9
MAX_HEIGHT = 7
HEIGHT_BASE = 2.2
OFFSET = -(MAP_W * TILE) // 2

SIDES = ('N', 'E', 'S', 'W')
DELTA = {'N': (0, -1), 'E': (1, 0), 'S': (0, 1), 'W': (-1, 0)}
OPPOSITE = {'N': 'S', 'S': 'N', 'E': 'W', 'W': 'E'}
MOVES = ((-1, 0), (0, 1), (1, 0), (0, -1))


# ── сетки без numpy ──────────────────────────────────────────

def rot90(grid, k=1):
    """Поворот против часовой, как np.rot90."""
    g = [list(row) for row in grid]
    for _ in range(k % 4):
        g = [list(row) for row in zip(*g)][::-1]
    return g


def fliplr(grid):
    return [list(reversed(row)) for row in grid]


def grid_copy(grid):
    return [list(row) for row in grid]


def _edge(grid, side):
    if side == 'N':
        return grid[0]
    if side == 'S':
        return grid[TILE - 1]
    if side == 'W':
        return [row[0] for row in grid]
    return [row[TILE - 1] for row in grid]


def sockets(grid):
    return set(s for s in SIDES if any(v == 0 for v in _edge(grid, s)))


def rotate_cell(r, c, k):
    for _ in range(k % 4):
        r, c = TILE - 1 - c, r
    return r, c


def _mix_hex(a, b, t):
    ca = tuple(int(a[i:i + 2], 16) for i in (1, 3, 5))
    cb = tuple(int(b[i:i + 2], 16) for i in (1, 3, 5))
    return '#%02x%02x%02x' % tuple(int(round(x + (y - x) * t)) for x, y in zip(ca, cb))


# ── словарь модулей ──────────────────────────────────────────

MODULES = {
    'gate': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 3, 0, 0, 3, 1],
            [1, 3, 0, 0, 3, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
        ],
        'role': 'gate', 'decor': [], 'height': 1.0,
    },
    'corridor': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
        ],
        'role': 'corridor', 'decor': [], 'height': 0.8,
    },
    'turn': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 0, 0],
            [1, 1, 0, 0, 0, 0],
            [1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1],
        ],
        'role': 'corridor', 'decor': [], 'height': 0.8,
    },
    'tee': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 0, 0],
            [1, 1, 0, 0, 0, 0],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
        ],
        'role': 'junction', 'decor': [], 'height': 0.8,
    },
    'cross': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
        ],
        'role': 'junction', 'decor': [], 'height': 0.8,
    },
    'room_small': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 1],
            [1, 1, 1, 1, 1, 1],
        ],
        'role': 'room',
        'decor': [(1, 1, 'any'), (1, 4, 'any'), (4, 1, 'any'), (4, 4, 'any')],
        'height': 1.0,
    },
    'room_large': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 0, 0, 0, 0, 1],
            [1, 0, 3, 3, 0, 1],
            [1, 0, 3, 3, 0, 1],
            [1, 0, 0, 0, 0, 1],
            [1, 1, 0, 0, 1, 1],
        ],
        'role': 'room',
        'decor': [(1, 1, 'any'), (1, 4, 'any'), (4, 1, 'any'), (4, 4, 'any')],
        'height': 1.2,
    },
    'tower': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 3, 0, 0, 3, 1],
            [1, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 1],
            [1, 3, 3, 3, 3, 1],
            [1, 1, 1, 1, 1, 1],
        ],
        'role': 'tower',
        'decor': [(2, 1, 'any'), (2, 4, 'any'), (3, 1, 'any'), (3, 4, 'any')],
        'height': 2.0,
    },
    'dead_end': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 0, 0, 0, 0, 1],
            [1, 0, 0, 0, 0, 1],
            [1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1],
            [1, 1, 1, 1, 1, 1],
        ],
        'role': 'dead_end',
        'decor': [(2, 2, 'chest'), (2, 3, 'any'), (1, 1, 'any'), (1, 4, 'any')],
        'height': 0.8,
    },
    'arena': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 0, 0, 0, 0, 1],
            [0, 0, 3, 3, 0, 0],
            [0, 0, 3, 3, 0, 0],
            [1, 0, 0, 0, 0, 1],
            [1, 1, 0, 0, 1, 1],
        ],
        'role': 'arena',
        'decor': [(1, 1, 'feature'), (1, 4, 'feature'), (4, 1, 'any'), (4, 4, 'any')],
        'height': 2.2,
    },
    'yard': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 0, 0, 0, 0, 1],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [1, 0, 0, 0, 0, 1],
            [1, 1, 0, 0, 1, 1],
        ],
        'role': 'yard',
        'decor': [(1, 1, 'outdoor'), (1, 4, 'outdoor'), (4, 1, 'outdoor'),
                  (4, 4, 'outdoor')],
        'height': 0.5,
    },
    'block': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 0, 0, 0, 0, 1],
            [0, 0, 1, 1, 0, 0],
            [0, 0, 1, 1, 0, 0],
            [1, 0, 0, 0, 0, 1],
            [1, 1, 0, 0, 1, 1],
        ],
        'role': 'block',
        'decor': [(1, 1, 'outdoor'), (1, 4, 'outdoor'), (4, 1, 'outdoor'),
                  (4, 4, 'outdoor')],
        'height': 1.8,
    },
    'block_corner': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 0, 0, 0, 0, 1],
            [0, 0, 1, 1, 0, 0],
            [0, 0, 1, 1, 0, 0],
            [1, 0, 1, 0, 0, 1],
            [1, 1, 0, 0, 1, 1],
        ],
        'role': 'block',
        'decor': [(1, 1, 'outdoor'), (1, 4, 'outdoor'), (4, 1, 'any')],
        'height': 1.5,
    },
    'avenue': {
        'grid': [
            [1, 3, 0, 0, 3, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 1, 0, 0, 1, 1],
            [1, 3, 0, 0, 3, 1],
        ],
        'role': 'avenue',
        'decor': [(1, 2, 'any'), (4, 3, 'any'), (2, 3, 'outdoor')],
        'height': 2.0,
    },
    'plaza': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 0, 0, 0, 0, 1],
            [0, 0, 3, 3, 0, 0],
            [0, 0, 3, 3, 0, 0],
            [1, 0, 0, 0, 0, 1],
            [1, 1, 0, 0, 1, 1],
        ],
        'role': 'plaza',
        'decor': [(1, 1, 'outdoor'), (1, 4, 'outdoor'), (4, 1, 'outdoor'),
                  (4, 4, 'outdoor')],
        'height': 0.9,
    },
    'park': {
        'grid': [
            [1, 1, 0, 0, 1, 1],
            [1, 0, 0, 0, 0, 1],
            [0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0],
            [1, 0, 0, 0, 0, 1],
            [1, 1, 0, 0, 1, 1],
        ],
        'role': 'park',
        'decor': [(1, 1, 'outdoor'), (1, 4, 'outdoor'), (4, 1, 'outdoor'),
                  (4, 4, 'outdoor'), (2, 2, 'outdoor')],
        'height': 0.35,
    },
}

VARIANTS = {}


def _build_variants(name):
    out, seen = [], set()
    for k in range(4):
        g = rot90(MODULES[name]['grid'], k)
        key = tuple(tuple(row) for row in g)
        if key in seen:
            continue
        seen.add(key)
        out.append({'rot': k, 'grid': g, 'sockets': sockets(g)})
    return out


for _name in list(MODULES):
    VARIANTS[_name] = _build_variants(_name)

TERMINAL = set(n for n, vs in VARIANTS.items()
               if all(len(v['sockets']) == 1 for v in vs))


def variants_with_socket(name, side):
    return [v for v in VARIANTS[name] if side in v['sockets']]


# ── стили ────────────────────────────────────────────────────

STYLES = {
    'city': {
        'name': 'Город',
        'palette': {'wall': '#8a8f9c', 'floor': '#4a4e58', 'accent': '#d8b45a'},
        'weights': {'corridor': 1.4, 'turn': 1.0, 'tee': 1.2, 'cross': 1.6,
                    'room_small': 0.3, 'room_large': 0.2, 'tower': 0.5,
                    'dead_end': 0.4, 'arena': 0.0, 'yard': 0.3,
                    'block': 3.2, 'block_corner': 2.4, 'avenue': 2.6,
                    'plaza': 1.2, 'park': 1.4},
        'branching': 0.7, 'symmetry': 0.15, 'verticality': 0.75, 'size': 22,
        'props': {'outdoor': 'tree', 'feature': 'statue', 'density': 0.45,
                  'any': ['lantern', 'flag', 'barrel', 'statue', 'bush']},
        'moods': [('утреннее', '#4a6fa5'), ('пасмурное', '#5c6b80'),
                  ('закатное', '#c96f4a')],
    },
    'cave': {
        'name': 'Пещера',
        'palette': {'wall': '#4a3f5c', 'floor': '#2f2a3a', 'accent': '#7b5fa8'},
        'weights': {'corridor': 3.0, 'turn': 3.5, 'tee': 1.2, 'cross': 0.4,
                    'room_small': 1.0, 'room_large': 0.5, 'tower': 0.2,
                    'dead_end': 1.6, 'arena': 0.0, 'yard': 0.2,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0,
                    'plaza': 0.0, 'park': 0.0},
        'branching': 0.55, 'symmetry': 0.0, 'verticality': 0.35, 'size': 16,
        'props': {'outdoor': 'crystal', 'feature': 'crystal', 'density': 0.35,
                  'any': ['crystal', 'lantern', 'barrel', 'chest']},
        'moods': [('мрачное', '#2e2a52'), ('глухое', '#3d3470'),
                  ('светлое', '#5b4b9e')],
    },
    'castle': {
        'name': 'Замок',
        'palette': {'wall': '#8c8c96', 'floor': '#5a5a66', 'accent': '#c9a227'},
        'weights': {'corridor': 2.0, 'turn': 1.0, 'tee': 1.5, 'cross': 1.0,
                    'room_small': 1.5, 'room_large': 2.5, 'tower': 2.0,
                    'dead_end': 0.4, 'arena': 0.3, 'yard': 0.5,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0,
                    'plaza': 0.0, 'park': 0.0},
        'branching': 0.35, 'symmetry': 0.9, 'verticality': 0.75, 'size': 14,
        'props': {'outdoor': 'tree', 'feature': 'statue', 'density': 0.3,
                  'any': ['statue', 'flag', 'barrel', 'lantern', 'chest']},
        'moods': [('грозовое', '#3a4260'), ('сумеречное', '#5061a0'),
                  ('парадное', '#7a92d4')],
    },
    'mansion': {
        'name': 'Особняк',
        'palette': {'wall': '#8a5a3c', 'floor': '#c8a97e', 'accent': '#d94f8a'},
        'weights': {'corridor': 3.0, 'turn': 1.5, 'tee': 2.0, 'cross': 0.8,
                    'room_small': 3.5, 'room_large': 2.0, 'tower': 0.4,
                    'dead_end': 0.8, 'arena': 0.0, 'yard': 0.3,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0,
                    'plaza': 0.0, 'park': 0.0},
        'branching': 0.5, 'symmetry': 0.5, 'verticality': 0.45, 'size': 16,
        'props': {'outdoor': 'tree', 'feature': 'statue', 'density': 0.32,
                  'any': ['statue', 'lantern', 'barrel', 'bush', 'chest']},
        'moods': [('тревожное', '#5c3a3a'), ('уютное', '#a06848'),
                  ('тёплое', '#d99055')],
    },
    'island': {
        'name': 'Остров',
        'palette': {'wall': '#4e9d5a', 'floor': '#d9c48a', 'accent': '#2f8fd0'},
        'weights': {'corridor': 1.0, 'turn': 1.5, 'tee': 1.0, 'cross': 0.8,
                    'room_small': 0.8, 'room_large': 0.8, 'tower': 0.6,
                    'dead_end': 1.5, 'arena': 0.2, 'yard': 4.0,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0,
                    'plaza': 0.0, 'park': 0.0},
        'branching': 0.65, 'symmetry': 0.0, 'verticality': 0.35, 'size': 14,
        'props': {'outdoor': 'tree', 'feature': 'tent', 'density': 0.26,
                  'any': ['tree', 'bush', 'barrel', 'chest', 'lantern']},
        'moods': [('штормовое', '#3d6580'), ('ясное', '#4fb0e0'),
                  ('закатное', '#e88a5a')],
    },
    'circus': {
        'name': 'Цирк',
        'palette': {'wall': '#d93b3b', 'floor': '#f2e7d5', 'accent': '#ffd23f'},
        'weights': {'corridor': 2.0, 'turn': 0.8, 'tee': 1.5, 'cross': 2.0,
                    'room_small': 1.0, 'room_large': 1.5, 'tower': 1.5,
                    'dead_end': 0.6, 'arena': 4.0, 'yard': 1.0,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0,
                    'plaza': 0.0, 'park': 0.0},
        'branching': 0.75, 'symmetry': 0.95, 'verticality': 0.8, 'size': 14,
        'props': {'outdoor': 'tent', 'feature': 'tent', 'density': 0.2,
                  'any': ['flag', 'lantern', 'tent', 'barrel', 'chest']},
        'moods': [('зловещее', '#6b1f45'), ('праздничное', '#b8306b'),
                  ('карнавальное', '#e8508f')],
    },
    'candy': {
        'name': 'Королевство сладостей',
        'palette': {'wall': '#ff9ecb', 'floor': '#fff0f6', 'accent': '#7ad7f0'},
        'weights': {'corridor': 1.5, 'turn': 3.0, 'tee': 1.5, 'cross': 0.8,
                    'room_small': 1.5, 'room_large': 1.0, 'tower': 3.0,
                    'dead_end': 1.5, 'arena': 0.5, 'yard': 2.0,
                    'block': 0.0, 'block_corner': 0.0, 'avenue': 0.0,
                    'plaza': 0.0, 'park': 0.0},
        'branching': 0.6, 'symmetry': 0.3, 'verticality': 0.55, 'size': 14,
        'props': {'outdoor': 'lollipop', 'feature': 'lollipop', 'density': 0.5,
                  'any': ['lollipop', 'bush', 'lantern', 'chest', 'tree']},
        'moods': [('приторное', '#8a4ba8'), ('нежное', '#d47ac0'),
                  ('сахарное', '#f2a0d8')],
    },
}

HYBRID_PAIRS = [
    ('cave', 'mansion'), ('castle', 'candy'), ('circus', 'island'),
    ('cave', 'circus'), ('mansion', 'circus'), ('castle', 'cave'),
    ('candy', 'island'), ('mansion', 'candy'),
    ('city', 'castle'), ('city', 'candy'), ('city', 'island'), ('city', 'cave'),
]


def style_mix(style):
    mix = style.get('mix')
    if mix:
        total = sum(mix.values()) or 1.0
        return dict((k, round(v / total, 4)) for k, v in mix.items() if v > 0.01)
    by_name = dict((base['name'], key) for key, base in STYLES.items())
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
    out = dict((k, ma.get(k, 0.0) * (1 - t) + mb.get(k, 0.0) * t) for k in keys)
    total = sum(out.values()) or 1.0
    return dict((k, round(v / total, 4)) for k, v in out.items() if v > 0.01)


def blend_styles(a, b, t=0.5, name=None):
    sa, sb = STYLES[a], STYLES[b]
    return {
        'mix': _mix_maps(style_mix(sa), style_mix(sb), t),
        'name': name or (sa['name'] + ' × ' + sb['name']),
        'palette': dict((k, _mix_hex(sa['palette'][k], sb['palette'][k], t))
                        for k in sa['palette']),
        'weights': dict((k, sa['weights'].get(k, 0.0) * (1 - t)
                         + sb['weights'].get(k, 0.0) * t)
                        for k in set(sa['weights']) | set(sb['weights'])),
        'branching': sa['branching'] * (1 - t) + sb['branching'] * t,
        'symmetry': sa['symmetry'] * (1 - t) + sb['symmetry'] * t,
        'verticality': sa['verticality'] * (1 - t) + sb['verticality'] * t,
        'size': int(round(sa['size'] * (1 - t) + sb['size'] * t)),
        'props': {
            'outdoor': (sa if t < 0.5 else sb)['props']['outdoor'],
            'feature': (sa if t < 0.5 else sb)['props']['feature'],
            'density': sa['props']['density'] * (1 - t) + sb['props']['density'] * t,
            'any': sorted(set(sa['props']['any']) | set(sb['props']['any'])),
        },
        'moods': [(ma[0] + '/' + mb[0], mb[1] if t > 0.5 else ma[1])
                  for ma, mb in zip(sa['moods'], sb['moods'])],
    }


# ── уровень ──────────────────────────────────────────────────

class Level(object):
    def __init__(self, style, tiles, gate, w, h, rng=None):
        self.style = style
        self.tiles = tiles
        self.gate = gate
        self.w, self.h = w, h
        self.rng = rng or random.Random()
        self.mood = None
        self.sky = '#111111'
        self.roles = None
        self.blueprint = []
        self.decorations = []
        self.descriptor = {}
        self.novelty = 0.0

    def assemble(self):
        H, W = self.h * TILE, self.w * TILE
        self.roles = [[-1] * W for _ in range(H)]
        for (tx, ty), t in self.tiles.items():
            g = t['grid']
            for r in range(TILE):
                for c in range(TILE):
                    self.roles[ty * TILE + r][tx * TILE + c] = int(g[r][c])

    def seal(self):
        for (tx, ty), t in self.tiles.items():
            grid = t['grid']
            for side in SIDES:
                if side not in sockets(grid):
                    continue
                if (tx, ty) == self.gate and side == t.get('outer'):
                    continue
                dx, dy = DELTA[side]
                nb = self.tiles.get((tx + dx, ty + dy))
                if nb is not None and OPPOSITE[side] in sockets(nb['grid']):
                    continue
                if side == 'N':
                    grid[0] = [1 if v == 0 else v for v in grid[0]]
                elif side == 'S':
                    grid[TILE - 1] = [1 if v == 0 else v for v in grid[TILE - 1]]
                elif side == 'W':
                    for row in grid:
                        if row[0] == 0:
                            row[0] = 1
                else:
                    for row in grid:
                        if row[TILE - 1] == 0:
                            row[TILE - 1] = 1

    def entry_cell(self):
        tx, ty = self.gate
        return (ty * TILE + TILE - 2, tx * TILE + 2)

    def distances(self):
        H, W = len(self.roles), len(self.roles[0])
        start = self.entry_cell()
        dist = {start: 0}
        q = deque([start])
        while q:
            r, c = q.popleft()
            for dr, dc in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nr, nc = r + dr, c + dc
                if 0 <= nr < H and 0 <= nc < W and (nr, nc) not in dist \
                        and self.roles[nr][nc] == 0:
                    dist[(nr, nc)] = dist[(r, c)] + 1
                    q.append((nr, nc))
        return dist

    def reachability(self):
        walkable = sum(1 for row in self.roles for v in row if v == 0)
        return (len(self.distances()) / float(walkable)) if walkable else 0.0

    def prune_unreachable(self):
        for _ in range(3):
            reach = set(self.distances())
            drop = []
            for (tx, ty), t in self.tiles.items():
                cells = [(ty * TILE + r, tx * TILE + c)
                         for r in range(TILE) for c in range(TILE)
                         if t['grid'][r][c] == 0]
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
        moods = self.style.get('moods') or [('обычное', '#111111')]
        d = self.descriptor
        openness = min(max((d.get('openness', 0.3) - 0.30) / 0.18, 0.0), 1.0)
        shallow = 1.0 - min(max((d.get('depth', 20) - 20) / 70.0, 0.0), 1.0)
        branch = min(max(d.get('branching', 0) / 0.4, 0.0), 1.0)
        score = 0.45 * openness + 0.3 * shallow + 0.25 * branch
        score += self.rng.uniform(-0.18, 0.18)
        idx = min(max(int(score * len(moods)), 0), len(moods) - 1)
        self.mood, self.sky = moods[idx]
        return self.mood

    def compute_descriptor(self):
        dist = self.distances()
        roles = [t['role'] for t in self.tiles.values()]
        built = sum(1 for row in self.roles for v in row if v >= 0)
        walk = sum(1 for row in self.roles for v in row if v == 0)
        n = max(len(self.tiles), 1)
        self.descriptor = {
            'size': len(self.tiles),
            'openness': round(walk / float(built), 3) if built else 0,
            'verticality': round(self.style['verticality'], 3),
            'branching': round(sum(1 for t in self.tiles.values()
                                   if len(sockets(t['grid'])) >= 3) / float(n), 3),
            'room_ratio': round(roles.count('room') / float(n), 3),
            'dead_ends': roles.count('dead_end'),
            'depth': max(dist.values()) if dist else 0,
            'reachability': round(self.reachability(), 3),
        }
        return self.descriptor

    def build_blueprint(self):
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
                    role = int(t['grid'][r][c])
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
                        self.blueprint.append({
                            'x': x, 'y': y, 'z': z,
                            'color': color, 'role': role,
                        })
        return self.blueprint

    def place_decorations(self):
        dist = self.distances()
        self.decorations = []
        candidates = []
        PRIORITY = {'dead_end': 3, 'tower': 2, 'room': 2, 'arena': 1}
        for (tx, ty), t in self.tiles.items():
            k = t.get('rot', 0)
            for (r0, c0, kind) in MODULES[t['name']]['decor']:
                r, c = rotate_cell(r0, c0, k)
                if t['grid'][r][c] != 0:
                    continue
                x, z = tx * TILE + c, ty * TILE + r
                d = dist.get((z, x))
                if d is None:
                    continue
                props_of = t['style'].get('props', {})
                if kind in ('outdoor', 'feature'):
                    prop = props_of.get(kind)
                    if prop:
                        self.decorations.append({
                            'type': prop, 'x': float(x), 'y': 0.0, 'z': float(z),
                        })
                else:
                    candidates.append((PRIORITY.get(t['role'], 0), d, x, z, props_of))
        if candidates:
            far = sorted(candidates, key=lambda c: -c[1])
            cut = max(1, len(far) // 4)
            _, _, x, z, _ = max(far[:cut], key=lambda c: (c[0], c[1]))
        elif dist:
            (z, x), _ = max(dist.items(), key=lambda kv: kv[1])
        else:
            return self.decorations
        self.decorations.append({
            'type': 'chest', 'x': float(x), 'y': 0.0, 'z': float(z), 'goal': True,
        })
        for _, _, cx, cz, pr in candidates[1:]:
            kinds = pr.get('any') or []
            if not kinds or self.rng.random() > pr.get('density', 0.5):
                continue
            self.decorations.append({
                'type': self.rng.choice(kinds),
                'x': float(cx), 'y': 0.0, 'z': float(cz),
            })
        return self.decorations


def _pick_module(style, rng, exclude=()):
    names, weights = [], []
    for n, w in style['weights'].items():
        if w > 0 and n not in exclude and n in MODULES:
            names.append(n)
            weights.append(w)
    if not names:
        return 'corridor'
    return rng.choices(names, weights=weights)[0]


def _style_at(style, tx, ty, zoned):
    if not zoned:
        return style
    a, b, axis = zoned
    if axis == 'z':
        return a if ty >= MAP_H // 2 else b
    return a if tx < MAP_W // 2 else b


def _mirror(tiles, cx):
    for (tx, ty), t in tiles.items():
        if tx == cx:
            g = t['grid']
            fl = fliplr(g)
            t['grid'] = [[0 if (g[r][c] == 0 or fl[r][c] == 0) else g[r][c]
                          for c in range(TILE)] for r in range(TILE)]
            t['sym'] = True
    for (tx, ty), t in list(tiles.items()):
        if tx >= cx:
            continue
        mx = 2 * cx - tx
        if (mx, ty) in tiles:
            continue
        tiles[(mx, ty)] = dict(t)
        tiles[(mx, ty)]['grid'] = fliplr(t['grid'])
        tiles[(mx, ty)]['flip'] = not t.get('flip', False)


def generate(style, seed=None, zoned=None, mirror=None):
    rng = random.Random(seed)
    base = style
    symmetric = base['symmetry'] >= 0.5 if mirror is None else mirror
    cx = MAP_W // 2
    limit_x = cx if symmetric else MAP_W - 1
    tiles = {}
    gate = (cx, MAP_H - 1)
    gate_st = _style_at(base, gate[0], gate[1], zoned)
    gv = VARIANTS['gate'][0]
    tiles[gate] = {
        'name': 'gate', 'rot': gv['rot'], 'grid': grid_copy(gv['grid']),
        'role': 'gate', 'style': gate_st, 'outer': 'S',
    }
    frontier = [(gate[0], gate[1], 'N')]
    target = base['size']
    while frontier and len(tiles) < target:
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
            exclude = ('cross', 'tee')
        elif not frontier:
            exclude = tuple(TERMINAL)
        else:
            exclude = ()
        for _ in range(8):
            name = _pick_module(st, rng, exclude)
            opts = variants_with_socket(name, need)
            if opts:
                v = rng.choice(opts)
                tiles[(nx, ny)] = {
                    'name': name, 'rot': v['rot'], 'grid': grid_copy(v['grid']),
                    'role': MODULES[name]['role'], 'style': st, 'outer': None,
                }
                for s in v['sockets']:
                    if s != need:
                        frontier.append((nx, ny, s))
                break
    if symmetric:
        _mirror(tiles, cx)
    level = Level(base, tiles, gate, MAP_W, MAP_H, rng=rng)
    level.assemble()
    level.seal()
    level.assemble()
    level.prune_unreachable()
    level.build_blueprint()
    level.compute_descriptor()
    level.pick_mood()
    level.place_decorations()
    return level


_MEMORY = deque(maxlen=12)


def _vec(desc):
    return (
        desc.get('openness', 0),
        desc.get('branching', 0),
        desc.get('room_ratio', 0),
        desc.get('depth', 0) / 60.0,
        desc.get('size', 0) / 20.0,
    )


def novelty(desc):
    if not _MEMORY:
        return 1.0
    v = _vec(desc)
    best = 1e9
    for m in _MEMORY:
        d = math.sqrt(sum((a - b) ** 2 for a, b in zip(v, m)))
        if d < best:
            best = d
    return float(best)


def generate_novel(style, seed=None, tries=8, min_novelty=0.12, **kw):
    rng = random.Random(seed)
    best, best_n = None, -1.0
    fallback, fallback_size = None, -1
    min_size = max(4, int(style['size'] * 0.6))
    for _ in range(tries):
        lv = generate(style, seed=rng.randrange(10 ** 9), **kw)
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


# ── руки ─────────────────────────────────────────────────────

REACH = 3


class Hands(object):
    def __init__(self, level, reach=REACH):
        self.level = level
        self.reach = reach
        self.start = level.entry_cell()
        self.walkable = set(level.distances())
        self.columns = self._columns()
        self.serves = self._serves()
        self.steps = []
        self.unreachable = []

    def _columns(self):
        cols = {}
        for b in self.level.blueprint:
            cols.setdefault((b['z'], b['x']), []).append(b)
        for key in cols:
            cols[key].sort(key=lambda b: b['y'])
        return cols

    def _serves(self):
        gate_dist = self.level.distances()
        best = {}
        r = self.reach
        for cell in self.walkable:
            cz, cx = cell
            for dz in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    key = (cz + dz, cx + dx)
                    if key not in self.columns:
                        continue
                    rank = (max(abs(dz), abs(dx)), gate_dist.get(cell, 10 ** 6))
                    if key not in best or rank < best[key][0]:
                        best[key] = (rank, cell)
        serves = {}
        for key, pair in best.items():
            serves.setdefault(pair[1], []).append(key)
        return serves

    def _bfs(self, origin, targets):
        if origin in targets:
            return origin, []
        prev = {origin: None}
        q = deque([origin])
        while q:
            cur = q.popleft()
            cz, cx = cur
            for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nxt = (cz + dz, cx + dx)
                if nxt in prev or nxt not in self.walkable:
                    continue
                prev[nxt] = cur
                if nxt in targets:
                    path = []
                    node = nxt
                    while node != origin:
                        path.append(node)
                        node = prev[node]
                    path.reverse()
                    return nxt, path
                q.append(nxt)
        return None, None

    def plan(self):
        self.steps = []
        pending = set(self.columns)
        pos = self.start
        self._emit_move(pos)
        while pending:
            targets = set(cell for cell, cols in self.serves.items()
                          if any(k in pending for k in cols))
            if not targets:
                break
            cell, path = self._bfs(pos, targets)
            if cell is None:
                break
            for node in path:
                self._emit_move(node)
            pos = cell
            here = [k for k in self.serves[cell] if k in pending]
            here.sort(key=lambda k: (abs(k[0] - cell[0]) + abs(k[1] - cell[1]), k))
            for key in here:
                for block in self.columns[key]:
                    self._emit_place(pos, block)
                pending.discard(key)
        self.unreachable = sorted(pending)
        self._plan_decor(pos)
        return self.steps

    def _plan_decor(self, pos):
        r = self.reach
        for d in self.level.decorations:
            goal = (int(d['z']), int(d['x']))
            cands = set(c for c in self.walkable
                        if max(abs(c[0] - goal[0]), abs(c[1] - goal[1])) <= r)
            if not cands:
                continue
            cell, path = self._bfs(pos, cands)
            if cell is None:
                continue
            for node in path:
                self._emit_move(node)
            pos = cell
            self.steps.append({
                'kind': 'decor',
                'x': float(cell[1]), 'y': 0.0, 'z': float(cell[0]),
                'decor': dict(d),
            })
        return pos

    def _emit_move(self, cell):
        cz, cx = cell
        self.steps.append({'kind': 'move', 'x': float(cx), 'y': 0.0, 'z': float(cz)})

    def _emit_place(self, cell, block):
        cz, cx = cell
        self.steps.append({
            'kind': 'place',
            'x': float(cx), 'y': 0.0, 'z': float(cz),
            'block': {
                'x': float(block['x']), 'y': float(block['y']),
                'z': float(block['z']), 'color': block['color'],
                'role': block.get('role', 1),
            },
        })

    def report(self):
        placed = sum(1 for s in self.steps if s['kind'] == 'place')
        moves = sum(1 for s in self.steps if s['kind'] == 'move')
        total = len(self.level.blueprint)
        missed = sum(len(self.columns[k]) for k in self.unreachable)
        return {
            'blocks_total': total,
            'blocks_placed': placed,
            'blocks_missed': missed,
            'coverage': round(placed / float(total), 4) if total else 1.0,
            'moves': moves,
            'steps': len(self.steps),
            'columns': len(self.columns),
            'unreachable_columns': len(self.unreachable),
        }


def build_steps(level, reach=REACH):
    b = Hands(level, reach)
    b.plan()
    return b


# ── гуляки и критик ──────────────────────────────────────────

WEIGHTS = {
    'reach_rate': 0.22, 'coverage': 0.16, 'winding': 0.14,
    'loops': 0.12, 'depth': 0.12, 'variety': 0.14, 'spread': 0.10,
}
PENALTIES = {
    'open_blob': 0.45, 'snake': 0.40, 'huddle': 0.30,
    'monotony': 0.35, 'trivial': 0.50,
}


def goal_cell(level):
    for d in level.decorations:
        if d.get('goal'):
            return (int(d['z']), int(d['x']))
    return None


def naive_walk(level, dist, goal, n=12, steps=220, rng=None, trace=False, every=3):
    rng = rng or random.Random(0)
    cells = set(dist)
    start = level.entry_cell()
    visited, found, times = set(), 0, []
    traces = [[] for _ in range(n)] if trace else None
    for i in range(n):
        pos, d = start, rng.randrange(4)
        seen = set([start])
        for t in range(steps):
            if trace and t % every == 0:
                traces[i].append((pos[0], pos[1]))
            opts = []
            for j in range(4):
                cand = (pos[0] + MOVES[j][0], pos[1] + MOVES[j][1])
                if cand in cells:
                    opts.append((0 if cand not in seen else 1, j, cand))
            if not opts:
                break
            roll = rng.random()
            # Слабо тянемся к сундуку: иначе за 200 шагов его почти
            # никто не находит, и раунды перестают отличаться.
            if goal and roll < 0.28:
                gz, gx = goal
                best = min(opts, key=lambda o: abs(o[2][0] - gz) + abs(o[2][1] - gx))
                _, d, nxt = best
            elif roll < 0.8:
                fresh = [o for o in opts if o[0] == 0] or opts
                _, d, nxt = rng.choice(fresh)
            else:
                _, d, nxt = rng.choice(opts)
            pos = nxt
            seen.add(pos)
            visited.add(pos)
            if goal and pos == goal:
                found += 1
                times.append(t / float(steps))
                if trace:
                    traces[i].append((pos[0], pos[1]))
                break
    reach = found / float(n)
    mt = (sum(times) / float(len(times))) if times else 1.0
    cov = len(visited) / float(max(len(cells), 1))
    if not trace:
        return reach, mt, cov
    # frames[t][walker] = [x, z] в мировых координатах
    longest = max((len(p) for p in traces), default=0)
    frames = []
    for t in range(longest):
        row = []
        for p in traces:
            z, x = p[t] if t < len(p) else (p[-1] if p else start)
            row.append([int(x) + OFFSET, int(z) + OFFSET])
        frames.append(row)
    return reach, mt, cov, frames


def loop_ratio(level):
    v = len(level.tiles)
    if v < 3:
        return 0.0
    e = 0
    for (tx, ty), t in level.tiles.items():
        for side in ('E', 'S'):
            dx, dy = DELTA[side]
            nb = level.tiles.get((tx + dx, ty + dy))
            if nb and side in sockets(t['grid']) \
                    and OPPOSITE[side] in sockets(nb['grid']):
                e += 1
    cycles = max(0, e - v + 1)
    return min(1.0, cycles / max(v / 10.0, 1.0))


def open_blob_ratio(level, dist):
    walk = set(dist)
    if not walk:
        return 0.0
    wide = sum(1 for (z, x) in walk
               if all((z + dz, x + dx) in walk
                      for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1))))
    return wide / float(len(walk))


def module_entropy(level):
    names = [t['name'] for t in level.tiles.values()]
    if not names:
        return 0.0
    counts = Counter(names)
    total = float(len(names))
    h = -sum((c / total) * math.log(c / total) for c in counts.values())
    return min(1.0, h / math.log(max(len(MODULES), 2)))


def spread_ratio(level):
    if not level.tiles:
        return 0.0
    xs = [tx for (tx, _) in level.tiles]
    zs = [ty for (_, ty) in level.tiles]
    box = (max(xs) - min(xs) + 1) * (max(zs) - min(zs) + 1)
    return min(1.0, box / max(len(level.tiles) * 2.2, 1.0))


def evaluate(level, rng=None):
    rng = rng or random.Random(0)
    dist = level.distances()
    d = level.descriptor
    goal = goal_cell(level)
    if d.get('reachability', 0) < 0.999:
        return {'score': 0.0, 'rejected': 'карта не проходима целиком',
                'terms': {}, 'penalties': {}}
    if goal is None:
        return {'score': 0.0, 'rejected': 'нет цели', 'terms': {}, 'penalties': {}}
    if len(dist) < 20:
        return {'score': 0.0, 'rejected': 'слишком мало проходимых клеток',
                'terms': {}, 'penalties': {}}
    reach_rate, mean_time, coverage = naive_walk(level, dist, goal, rng=rng)
    path = dist.get(goal, 0)
    er, ec = level.entry_cell()
    straight = abs(goal[0] - er) + abs(goal[1] - ec)
    winding = min(1.0, (path / float(max(straight, 1)) - 1.0) / 1.5) if straight else 0.0
    loops = loop_ratio(level)
    depth = min(1.0, d['depth'] / 90.0)
    variety = module_entropy(level)
    spread = spread_ratio(level)
    terms = {
        'reach_rate': reach_rate, 'coverage': coverage,
        'winding': max(0.0, winding), 'loops': loops,
        'depth': depth, 'variety': variety, 'spread': spread,
    }
    score = sum(WEIGHTS[k] * v for k, v in terms.items())
    blob = open_blob_ratio(level, dist)
    pen = {}
    if blob > 0.35:
        pen['open_blob'] = PENALTIES['open_blob'] * min(1.0, (blob - 0.35) / 0.35)
    if d['branching'] < 0.03 and loops < 0.02 and variety < 0.45:
        pen['snake'] = PENALTIES['snake']
    if spread < 0.35:
        pen['huddle'] = PENALTIES['huddle'] * (1.0 - spread / 0.35)
    if variety < 0.45:
        pen['monotony'] = PENALTIES['monotony'] * (1.0 - variety / 0.45)
    if path < 12:
        pen['trivial'] = PENALTIES['trivial']
    score -= sum(pen.values())
    return {
        'score': round(max(0.0, score), 4),
        'rejected': None,
        'terms': dict((k, round(v, 3)) for k, v in terms.items()),
        'penalties': dict((k, round(v, 3)) for k, v in pen.items()),
        'path_len': path,
        'mean_time': round(mean_time, 3),
    }


# ── дуэль ────────────────────────────────────────────────────

class Duel(object):
    def __init__(self):
        self.round = 0
        self.history = []
        self.last = None
        self.resolved_for = None
        self._lock = threading.Lock()

    def resolve_once(self, world_a, world_b, key, rng=None):
        with self._lock:
            if self.resolved_for == key:
                return self.last
            self.resolved_for = key
            return self.resolve(world_a, world_b, rng)

    def resolve(self, world_a, world_b, rng=None):
        res = []
        for lv in (world_a.level, world_b.level):
            if lv is None:
                res.append(None)
                continue
            dist = lv.distances()
            goal = goal_cell(lv)
            reach, _mt, cov = naive_walk(lv, dist, goal, rng=rng)
            r = evaluate(lv, rng=rng)
            res.append({
                'score': round(r['score'], 4),
                'reach': round(reach, 3),
                'coverage': round(cov, 3),
                'rejected': r['rejected'],
            })
        res_a, res_b = res
        if res_a is None or res_b is None or res_a['rejected'] or res_b['rejected']:
            who = 'нет карты'
        elif abs(res_a['score'] - res_b['score']) < MARGIN:
            who = 'ничья'
        else:
            who = 'a' if res_a['score'] > res_b['score'] else 'b'
        self.round += 1
        if who in ('a', 'b'):
            win = world_a if who == 'a' else world_b
            win.wins += 1
        self.last = {
            'round': self.round,
            'winner': (world_a.key if who == 'a' else
                       world_b.key if who == 'b' else who),
            'a': res_a, 'b': res_b, 'stolen': {'tried': 0, 'kept': [], 'why': 'нет архива'},
        }
        self.history.append(self.last)
        del self.history[:-24]
        return self.last

    def reset(self, world_a, world_b):
        with self._lock:
            self.round = 0
            self.history = []
            self.last = None
            self.resolved_for = None
            world_a.wins = 0
            world_b.wins = 0

    def champion(self, world_a, world_b):
        if self.round < MATCH_ROUNDS:
            return None
        if world_a.wins == world_b.wins:
            return 'ничья'
        return world_a.key if world_a.wins > world_b.wins else world_b.key

    def snapshot(self, world_a, world_b):
        def _mean(side):
            vals = [h[side]['score'] for h in self.history if h.get(side)]
            if not vals:
                return None
            return round(sum(vals) / float(len(vals)), 4)
        return {
            'round': self.round,
            'match_rounds': MATCH_ROUNDS,
            'over': self.round >= MATCH_ROUNDS,
            'champion': self.champion(world_a, world_b),
            'wins': {world_a.key: world_a.wins, world_b.key: world_b.wins},
            'last': self.last,
            'mean': {'a': _mean('a'), 'b': _mean('b')},
        }


# ── строитель ────────────────────────────────────────────────

BUILDERS = {
    'caine': {'name': 'Кейн', 'platform': 0,
              'bias': ['cave', 'castle', 'mansion', 'circus']},
    'abel': {'name': 'Авель', 'platform': 1,
             'bias': ['city', 'island', 'candy', 'castle']},
}


def pick_style(rng, bias=None):
    if STYLE_CHOICE in STYLES:
        return STYLES[STYLE_CHOICE], None, 'pure'
    pool = [STYLES[k] for k in (bias or []) if k in STYLES] or list(STYLES.values())
    r = rng.random()
    if STYLE_CHOICE != 'hybrid' and r < 0.6:
        return rng.choice(pool), None, 'pure'
    a, b = rng.choice(HYBRID_PAIRS)
    t = rng.choice([0.35, 0.5, 0.65])
    base = blend_styles(a, b, t)
    if rng.random() < 0.5:
        return base, None, 'blend'
    axis = rng.choice(['z', 'x'])
    return base, (STYLES[a], STYLES[b], axis), 'zoned'


class World(object):
    def __init__(self, name='Кейн', key='caine', style_bias=None, platform=0):
        self.name = name
        self.key = key
        self.style_bias = style_bias
        self.platform = platform
        self.wins = 0
        self.rng = random.Random()
        self.map_index = 0
        self.live = None
        self._lock = threading.RLock()
        self.new_map()

    def new_map(self):
        st, zoned, kind = pick_style(self.rng, self.style_bias)
        level = generate_novel(st, zoned=zoned)
        builder = build_steps(level)
        report = builder.report()
        with self._lock:
            self.level = level
            self.style = st
            self.source = 'grammar'
            self.hybrid_kind = kind
            self.elite_score = None
            self.elite_desc = None
            self.found_name = None
            self.builder = builder
            self.report = report
            self.cursor = 0
            self.placed = 0
            self.finished = False
            self.map_index += 1
            self.batch = max(1, int(round(report['steps'] / float(TARGET_FRAMES))))
        print('[%s] карта #%s: %s (%s), настроение %s, модулей %s, блоков %s, пачка %s'
              % (self.name, self.map_index, self.style['name'], kind,
                 self.level.mood, self.level.descriptor['size'],
                 report['blocks_placed'], self.batch))

    def built_so_far(self):
        blocks, decor = [], []
        for s in self.builder.steps[:self.cursor]:
            if s['kind'] == 'place':
                b = s['block']
                blocks.append({
                    'x': b['x'] + OFFSET, 'y': b['y'], 'z': b['z'] + OFFSET,
                    'color': b['color'], 'role': b.get('role', 1),
                })
            elif s['kind'] == 'decor':
                decor.append(self._shift_decor(s['decor']))
        return blocks, decor

    def bounds(self):
        bp = self.level.blueprint
        if not bp:
            return {'minx': OFFSET, 'maxx': -OFFSET, 'minz': OFFSET, 'maxz': -OFFSET}
        xs = [b['x'] for b in bp]
        zs = [b['z'] for b in bp]
        return {
            'minx': min(xs) + OFFSET, 'maxx': max(xs) + OFFSET,
            'minz': min(zs) + OFFSET, 'maxz': max(zs) + OFFSET,
        }

    def _shift_decor(self, d):
        out = dict(d)
        out['x'] = d['x'] + OFFSET
        out['z'] = d['z'] + OFFSET
        return out

    def level_info(self):
        d = self.level.descriptor
        blocks, decor = self.built_so_far()
        gz, gx = self.level.entry_cell()
        return {
            'index': self.map_index,
            'style_name': self.style['name'],
            'hybrid': self.hybrid_kind,
            'palette': self.style['palette'],
            'mood': self.level.mood,
            'sky': self.level.sky,
            'source': self.source,
            'found_style': self.found_name,
            'score': None,
            'niche': None,
            'bounds': self.bounds(),
            'awaiting': self.finished,
            'descriptor': d,
            'novelty': self.level.novelty,
            'blocks': self.report['blocks_placed'],
            'total_steps': self.report['steps'],
            'size_cells': MAP_W * TILE,
            'offset': OFFSET,
            'style_mix': style_mix(self.style) if self.style else {},
            'gate': {'x': gx + OFFSET, 'z': gz + OFFSET},
            'decorations': decor,
            'decorations_total': len(self.level.decorations),
            'built': blocks,
            'progress': round(self.placed / float(self.report['blocks_placed'] or 1), 3),
        }

    def _idle_frame(self):
        gz, gx = self.level.entry_cell()
        return {
            'kind': 'idle', 'x': float(gx + OFFSET), 'y': 0.0,
            'z': float(gz + OFFSET), 'blocks': [], 'decor': [],
            'progress': 1.0, 'map_done': True, 'awaiting': True,
            'world_reset': False, 'level': None,
        }

    def start_new(self):
        self.new_map()
        gz, gx = self.level.entry_cell()
        return {
            'kind': 'move', 'x': float(gx + OFFSET), 'y': 0.0,
            'z': float(gz + OFFSET), 'blocks': [], 'decor': [],
            'progress': 0.0, 'map_done': False, 'awaiting': False,
            'world_reset': True, 'level': self.level_info(),
        }

    def step(self):
        with self._lock:
            return self._step_locked()

    def _step_locked(self):
        steps = self.builder.steps
        if self.cursor >= len(steps):
            self.finished = True
            if not AUTO_ADVANCE:
                return self._idle_frame()
            return self.start_new()
        blocks, decor = [], []
        kind = 'move'
        x = y = z = 0.0
        for _ in range(self.batch):
            if self.cursor >= len(steps):
                break
            s = steps[self.cursor]
            self.cursor += 1
            x, y, z = s['x'] + OFFSET, s['y'], s['z'] + OFFSET
            if s['kind'] == 'place':
                b = s['block']
                self.placed += 1
                blocks.append({
                    'x': b['x'] + OFFSET, 'y': b['y'], 'z': b['z'] + OFFSET,
                    'color': b['color'], 'role': b.get('role', 1),
                })
                kind = 'place'
            elif s['kind'] == 'decor':
                decor.append(self._shift_decor(s['decor']))
                if kind != 'place':
                    kind = 'decor'
        total = self.report['blocks_placed'] or 1
        return {
            'kind': kind, 'x': x, 'y': y, 'z': z,
            'blocks': blocks, 'decor': decor,
            'progress': round(self.placed / float(total), 3),
            'map_done': self.cursor >= len(steps),
            'awaiting': False, 'world_reset': False, 'level': None,
        }

    def stats(self):
        return {
            'mode': 'build',
            'map_index': self.map_index,
            'style_name': self.style['name'],
            'hybrid': self.hybrid_kind,
            'novelty': self.level.novelty,
            'descriptor': self.level.descriptor,
            'blocks': self.report['blocks_placed'],
            'placed': self.placed,
            'progress': round(self.placed / float(self.report['blocks_placed'] or 1), 3),
            'step': self.cursor,
            'total_steps': self.report['steps'],
            'decorations': len(self.level.decorations),
            'finished': self.finished,
            'live': None,
        }


# ── маршруты ─────────────────────────────────────────────────

engines = {}
duel = None
boot_error = None
ready = False
ready_lock = threading.Lock()


def boot_engine():
    global engines, duel, ready, boot_error
    try:
        built = {}
        for key, cfg in BUILDERS.items():
            if key == 'abel' and not DUEL_ON:
                continue
            built[key] = World(name=cfg['name'], key=key,
                               style_bias=cfg['bias'], platform=cfg['platform'])
        d = Duel() if (DUEL_ON and 'abel' in built) else None
        with ready_lock:
            engines = built
            duel = d
            ready = True
        print('движок готов: %s' % ', '.join(engines))
    except Exception as exc:
        boot_error = '%s: %s' % (type(exc).__name__, exc)
        print('движок не поднялся: %s' % boot_error)
        import traceback
        traceback.print_exc()


def _who(key):
    return engines.get(key or 'caine') or engines.get('caine')


def _step(who):
    eng = _who(who)
    frame = eng.step()
    frame['who'] = eng.key
    frame['platform'] = eng.platform
    frame['live'] = None
    return frame


def _level(who):
    eng = _who(who)
    info = eng.level_info()
    info['who'] = eng.key
    info['builder'] = eng.name
    info['platform'] = eng.platform
    return info


def _builders():
    if not ready:
        return {'ok': False, 'booting': True, 'error': boot_error,
                'builders': [], 'duel': DUEL_ON}
    return {
        'ok': True,
        'builders': [
            {'key': k, 'name': w.name, 'platform': w.platform, 'wins': w.wins}
            for k, w in engines.items()
        ],
        'duel': DUEL_ON and 'abel' in engines,
    }


def _duel_state():
    if duel is None or len(engines) < 2:
        return {'ok': False, 'reason': 'дуэль выключена'}
    a, b = engines['caine'], engines['abel']
    is_ready = a.finished and b.finished
    if is_ready and duel.champion(a, b) is None:
        duel.resolve_once(a, b, (a.map_index, b.map_index), a.rng)
    return dict({'ok': True, 'ready': is_ready}, **duel.snapshot(a, b))


def _duel_reset():
    if duel is None or len(engines) < 2:
        return {'ok': False, 'reason': 'дуэль выключена'}
    a, b = engines['caine'], engines['abel']
    duel.reset(a, b)
    a.new_map()
    b.new_map()
    return dict({'ok': True}, **duel.snapshot(a, b))


def _next(who):
    frame = _who(who).start_new()
    return {'ok': True, 'frame': frame, 'level': frame['level']}


def _stats(who):
    eng = _who(who)
    data = eng.stats()
    data['tempo_ms'] = TEMPO_MS
    data['who'] = eng.key
    data['builder'] = eng.name
    data['wins'] = eng.wins
    return data


def _walk(who, every=3):
    eng = _who(who)
    lv = getattr(eng, 'level', None)
    if lv is None:
        return {'ok': False, 'reason': 'карта ещё не готова'}
    every = max(1, int(every or 3))
    reach, _mt, cov, frames = naive_walk(
        lv, lv.distances(), goal_cell(lv), n=8, steps=180,
        rng=eng.rng, trace=True, every=every)
    if not frames:
        return {'ok': False, 'reason': 'гуляки не пошли'}
    goal = goal_cell(lv)
    return {
        'ok': True, 'frames': frames, 'walkers': len(frames[0]),
        'reach': round(reach, 3), 'coverage': round(cov, 3),
        'goal': [int(goal[1]) + OFFSET, int(goal[0]) + OFFSET] if goal else None,
    }


def _config():
    return {
        'tempo_ms': TEMPO_MS, 'style_choice': STYLE_CHOICE,
        'styles': dict((k, v['name']) for k, v in STYLES.items()),
        'size_cells': MAP_W * TILE, 'offset': OFFSET,
    }


ROUTES = {
    '/boot': lambda p: _builders(),
    '/step': lambda p: _step(p.get('who')),
    '/level': lambda p: _level(p.get('who')),
    '/builders': lambda p: _builders(),
    '/duel': lambda p: _duel_state(),
    '/duel/reset': lambda p: _duel_reset(),
    '/next': lambda p: _next(p.get('who')),
    '/reset': lambda p: (_who(p.get('who')).new_map(), {'ok': True})[1],
    '/stats': lambda p: _stats(p.get('who')),
    '/walk': lambda p: _walk(p.get('who'), p.get('every', 3)),
    '/config': lambda p: _config(),
    '/health': lambda p: {'ok': True, 'ready': ready, 'error': boot_error},
}


# ── HTTP ─────────────────────────────────────────────────────

class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'

    def log_message(self, fmt, *args):
        sys.stderr.write('[http] ' + (fmt % args) + '\n')

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', '*')
        self.send_header('Cache-Control', 'no-store')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _send(self, code, body, ctype='application/json; charset=utf-8'):
        if not isinstance(body, bytes):
            body = body.encode('utf-8')
        self.send_response(code)
        self._cors()
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, data, code=200):
        self._send(code, json.dumps(data, ensure_ascii=False))

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path or '/'
        params = dict((k, v[0]) for k, v in parse_qs(parsed.query).items())
        if path == '/' or path == '/index.html':
            html_path = os.path.join(HERE, 'index.html')
            if not os.path.isfile(html_path):
                self._send(404, 'нет index.html рядом с main.py', 'text/plain; charset=utf-8')
                return
            with open(html_path, 'rb') as f:
                self._send(200, f.read(), 'text/html; charset=utf-8')
            return
        handler = ROUTES.get(path)
        if handler is None:
            self._json({'ok': False, 'reason': 'нет маршрута %s' % path}, 404)
            return
        if path not in ('/builders', '/boot', '/health', '/config') and not ready:
            self._json({'ok': False, 'booting': True, 'error': boot_error or 'просыпаюсь'}, 503)
            return
        try:
            self._json(handler(params))
        except Exception as exc:
            import traceback
            traceback.print_exc()
            self._json({'ok': False, 'error': '%s: %s' % (type(exc).__name__, exc)}, 500)

    def do_POST(self):
        self.do_GET()


def launch_ui(url):
    try:
        import androidhelper
        droid = androidhelper.Android()
        droid.webViewShow(url)
        print('WebView: %s' % url)
        return
    except Exception:
        pass
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception:
        pass


def main():
    print('CaineAI · QPython')
    print('слушаю http://%s:%s/' % (HOST, PORT))
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    worker = threading.Thread(target=server.serve_forever)
    worker.daemon = True
    worker.start()
    threading.Thread(target=boot_engine, daemon=True).start()
    launch_ui('http://127.0.0.1:%s/' % PORT)
    print('открой http://127.0.0.1:%s/  (на телефоне WebView откроется сам)' % PORT)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print('остановка')
        server.shutdown()


if __name__ == '__main__':
    main()

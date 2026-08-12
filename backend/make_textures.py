"""Текстуры блоков в стиле майнкрафта, палитра «cool colors».

Запуск:  python make_textures.py
"""

import os
import random

from PIL import Image

OUT = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'public', 'tex')
N = 16          # логический размер, как в майнкрафте
SCALE = 4       # 16 × 4 = 64 пикселя на грань

# Палитра «cool colors», поднятая по яркости и насыщенности.
P = {
    'black':   (34, 32, 44),
    'coal':    (58, 55, 74),
    'slate':   (92, 88, 116),
    'grey':    (124, 120, 148),
    'ash':     (158, 154, 180),
    'silver':  (188, 186, 208),
    'pale':    (212, 210, 228),
    'bone':    (230, 228, 240),
    'chalk':   (243, 242, 250),
    'white':   (255, 255, 255),
    'bark':    (92, 52, 34),
    'wood':    (132, 78, 44),
    'oak':     (176, 110, 60),
    'birch':   (208, 142, 78),
    'sand':    (238, 178, 104),
    'tan':     (250, 202, 134),
    'cream':   (255, 228, 180),
    'orange':  (255, 138, 46),
    'amber':   (255, 186, 74),
    'gold':    (255, 219, 84),
    'lemon':   (255, 248, 140),
    'lime':    (190, 246, 110),
    'grass':   (128, 226, 92),
    'leaf':    (74, 200, 96),
    'moss':    (52, 166, 106),
    'pine':    (40, 140, 112),
    'teal':    (56, 226, 210),
    'cyan':    (96, 226, 255),
    'sky':     (86, 164, 255),
    'blue':    (94, 126, 255),
    'violet':  (150, 60, 232),
    'purple':  (188, 108, 255),
    'lilac':   (222, 158, 255),
    'magenta': (255, 104, 182),
    'pink':    (255, 168, 196),
    'crimson': (255, 84, 100),
    'red':     (255, 62, 104),
}


def canvas(base):
    img = Image.new('RGB', (N, N), P[base])
    return img, img.load()


def speckle(px, rng, colors, density=0.3):
    """Крапины — основной приём майнкрафтовой фактуры."""
    for y in range(N):
        for x in range(N):
            if rng.random() < density:
                px[x, y] = P[rng.choice(colors)]


def bricks(px, rng, mortar, face, alt, h=4, w=8):
    for y in range(N):
        row = y // h
        off = (w // 2) if row % 2 else 0
        for x in range(N):
            edge = (y % h == 0) or ((x + off) % w == 0)
            if edge:
                px[x, y] = P[mortar]
            else:
                px[x, y] = P[face if rng.random() < 0.75 else alt]


def planks(px, rng, main, dark, light, h=4):
    for y in range(N):
        for x in range(N):
            if y % h == 0:
                px[x, y] = P[dark]
            elif rng.random() < 0.16:
                px[x, y] = P[light if rng.random() < 0.5 else dark]
            else:
                px[x, y] = P[main]
    for y in range(0, N, h):          # торцы досок вразбежку
        cut = rng.randrange(N)
        for k in range(h):
            if y + k < N:
                px[cut, y + k] = P[dark]


def stripes(px, main, other, w=4, diag=False):
    for y in range(N):
        for x in range(N):
            k = ((x + y) // w) if diag else (x // w)
            px[x, y] = P[main if k % 2 == 0 else other]


def frame(px, color, width=1):
    for i in range(width):
        for k in range(N):
            px[k, i] = P[color]
            px[k, N - 1 - i] = P[color]
            px[i, k] = P[color]
            px[N - 1 - i, k] = P[color]


def ore(px, rng, colors, blobs=5):
    """Вкрапления самоцветов — для акцентных блоков."""
    for _ in range(blobs):
        cx, cy = rng.randrange(2, N - 2), rng.randrange(2, N - 2)
        c = P[rng.choice(colors)]
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                if abs(dx) + abs(dy) <= 1 or rng.random() < 0.5:
                    px[(cx + dx) % N, (cy + dy) % N] = c


# ─────────────────────────────────────────────────────────────
# Сами текстуры
# ─────────────────────────────────────────────────────────────

def cave_wall(px, rng):
    speckle(px, rng, ['slate', 'grey', 'coal', 'ash'], 1.0)
    ore(px, rng, ['purple', 'lilac'], 3)


def cave_floor(px, rng):
    speckle(px, rng, ['black', 'coal', 'slate'], 1.0)


def cave_accent(px, rng):
    speckle(px, rng, ['violet', 'purple'], 1.0)
    ore(px, rng, ['lilac', 'magenta'], 6)


def castle_wall(px, rng):
    bricks(px, rng, 'slate', 'ash', 'silver')


def castle_floor(px, rng):
    speckle(px, rng, ['grey', 'ash', 'slate', 'silver'], 1.0)


def castle_accent(px, rng):
    speckle(px, rng, ['gold', 'amber'], 1.0)
    ore(px, rng, ['lemon'], 4)
    frame(px, 'orange')


def mansion_wall(px, rng):
    planks(px, rng, 'oak', 'wood', 'birch')


def mansion_floor(px, rng):
    planks(px, rng, 'tan', 'sand', 'cream', h=8)


def mansion_accent(px, rng):
    speckle(px, rng, ['magenta', 'pink'], 1.0)
    frame(px, 'crimson')


def island_wall(px, rng):
    speckle(px, rng, ['leaf', 'grass', 'moss'], 1.0)
    for x in range(N):                       # травяная кромка сверху
        for y in range(rng.randint(2, 4)):
            px[x, y] = P['lime' if rng.random() < 0.6 else 'grass']


def island_floor(px, rng):
    speckle(px, rng, ['cream', 'tan', 'sand'], 1.0)


def island_accent(px, rng):
    speckle(px, rng, ['cyan', 'sky', 'teal'], 1.0)


def circus_wall(px, rng):
    stripes(px, 'crimson', 'cream')
    for y in range(N):                       # лёгкая потёртость ткани
        for x in range(N):
            if rng.random() < 0.09:
                px[x, y] = P['red' if rng.random() < 0.5 else 'white']


def circus_floor(px, rng):
    speckle(px, rng, ['cream', 'white', 'bone'], 1.0)


def circus_accent(px, rng):
    stripes(px, 'gold', 'lemon', w=2, diag=True)


def candy_wall(px, rng):
    speckle(px, rng, ['pink', 'magenta'], 1.0)
    for x in range(N):                       # потёки глазури сверху
        d = rng.randint(2, 5)
        for y in range(d):
            px[x, y] = P['white' if rng.random() < 0.7 else 'chalk']


def candy_floor(px, rng):
    speckle(px, rng, ['white', 'chalk', 'pink'], 1.0)


def candy_accent(px, rng):
    stripes(px, 'cyan', 'white', w=2, diag=True)


def city_wall(px, rng):
    bricks(px, rng, 'grey', 'silver', 'pale', h=8, w=8)
    for _ in range(3):                       # окна
        wx, wy = rng.randrange(1, N - 4), rng.randrange(1, N - 4)
        for dx in range(3):
            for dy in range(3):
                px[wx + dx, wy + dy] = P['sky' if rng.random() < 0.7 else 'cyan']


def city_floor(px, rng):
    speckle(px, rng, ['coal', 'slate', 'grey'], 1.0)


def city_accent(px, rng):
    speckle(px, rng, ['amber', 'gold'], 1.0)
    frame(px, 'orange')


TEXTURES = {
    ('cave', 'wall'): cave_wall,       ('cave', 'floor'): cave_floor,
    ('cave', 'accent'): cave_accent,
    ('castle', 'wall'): castle_wall,   ('castle', 'floor'): castle_floor,
    ('castle', 'accent'): castle_accent,
    ('mansion', 'wall'): mansion_wall, ('mansion', 'floor'): mansion_floor,
    ('mansion', 'accent'): mansion_accent,
    ('island', 'wall'): island_wall,   ('island', 'floor'): island_floor,
    ('island', 'accent'): island_accent,
    ('circus', 'wall'): circus_wall,   ('circus', 'floor'): circus_floor,
    ('circus', 'accent'): circus_accent,
    ('candy', 'wall'): candy_wall,     ('candy', 'floor'): candy_floor,
    ('candy', 'accent'): candy_accent,
    ('city', 'wall'): city_wall,       ('city', 'floor'): city_floor,
    ('city', 'accent'): city_accent,
}


def main():
    os.makedirs(OUT, exist_ok=True)
    for (style, role), fn in sorted(TEXTURES.items()):
        rng = random.Random(hash((style, role)) & 0xffff)
        img, px = canvas('ash')
        fn(px, rng)
        big = img.resize((N * SCALE, N * SCALE), Image.NEAREST)
        big.save(os.path.join(OUT, f'{style}_{role}.png'))
    print(f'нарисовано текстур: {len(TEXTURES)} '
          f'({N}×{N} → {N * SCALE}×{N * SCALE}, палитра cool colors)')


if __name__ == '__main__':
    main()

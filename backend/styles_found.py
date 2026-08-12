"""Стили как находки, а не как константы."""

import json
import math
import os
import random

import numpy as np

FEATURES = ('openness', 'loops', 'size', 'depth', 'branching',
            'room_ratio', 'dead_end_ratio', 'verticality',
            'lightness', 'saturation')

FOUND_PATH = os.path.join(os.path.dirname(__file__), 'styles_found.json')

# Как называть крайности по каждому признаку: (низкое, высокое)
ADJECTIVES = {
    'openness':       ('тесный', 'просторный'),
    'loops':          ('древовидный', 'кольцевой'),
    'size':           ('компактный', 'огромный'),
    'depth':          ('короткий', 'глубокий'),
    'branching':      ('линейный', 'ветвистый'),
    'room_ratio':     ('коридорный', 'зальный'),
    'dead_end_ratio': ('сквозной', 'тупиковый'),
    'verticality':    ('приземистый', 'высокий'),
    'lightness':      ('тёмный', 'светлый'),
    'saturation':     ('блёклый', 'яркий'),
}

# (порог, существительное, род): имя должно читаться по-русски, поэтому
# прилагательные согласуются, а не просто склеиваются
NOUNS = [(0.0, 'закуток', 'м'), (0.25, 'галерея', 'ж'), (0.5, 'комплекс', 'м'),
         (0.75, 'лабиринт', 'м'), (0.9, 'цитадель', 'ж')]


def _agree(adj, gender):
    if gender == 'ж' and adj[-2:] in ('ый', 'ий', 'ой'):
        return adj[:-2] + 'ая'
    return adj


def _palette_stats(palette):
    cols = []
    for k in ('wall', 'floor', 'accent'):
        h = palette[k].lstrip('#')
        cols.append([int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)])
    arr = np.array(cols)
    lightness = float(arr.mean())
    saturation = float(np.mean(arr.max(1) - arr.min(1)))
    return lightness, saturation


def features_of(level, entry):
    """Признаки карты: чем она является, а не от кого произошла."""
    d = level.descriptor
    light, sat = _palette_stats(level.style['palette'])
    return [
        d['openness'],
        entry['terms'].get('loops', 0.0),
        d['size'],
        d['depth'],
        d['branching'],
        d['room_ratio'],
        d['dead_ends'] / max(d['size'], 1),
        level.style['verticality'],
        light,
        sat,
    ]


# ─────────────────────────────────────────────────────────────
# Кластеризация
# ─────────────────────────────────────────────────────────────

def _kmeans(X, k, rng, iters=60):
    n = len(X)
    idx = rng.sample(range(n), k)
    C = X[idx].copy()
    labels = np.zeros(n, dtype=int)
    for _ in range(iters):
        d = ((X[:, None, :] - C[None, :, :]) ** 2).sum(-1)
        new = d.argmin(1)
        if (new == labels).all():
            break
        labels = new
        for j in range(k):
            m = labels == j
            if m.any():
                C[j] = X[m].mean(0)
            else:
                C[j] = X[rng.randrange(n)]
    return labels, C


def _silhouette(X, labels):
    """Насколько кластеры плотные и раздельные. Без sklearn — формула простая."""
    uniq = np.unique(labels)
    if len(uniq) < 2:
        return -1.0
    D = np.sqrt(((X[:, None, :] - X[None, :, :]) ** 2).sum(-1))
    out = []
    for i in range(len(X)):
        same = labels == labels[i]
        same[i] = False
        if not same.any():
            continue
        a = D[i][same].mean()
        b = min(D[i][labels == j].mean() for j in uniq if j != labels[i])
        out.append((b - a) / max(a, b))
    return float(np.mean(out)) if out else -1.0


def discover(archive, k_range=(4, 9), seed=0, verbose=False):
    """Найти стили в архиве. Число кластеров подбирается по силуэту."""
    from genome import Genome

    rows, entries, levels = [], [], []
    for e in archive.elites():
        lv = Genome.from_dict(e['genome']).decode()
        if lv is None:
            continue
        rows.append(features_of(lv, e))
        entries.append(e)
        levels.append(lv)
    if len(rows) < max(k_range):
        return None

    X = np.array(rows, dtype=float)
    mu, sigma = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sigma

    rng = random.Random(seed)
    best = None
    for k in range(k_range[0], k_range[1] + 1):
        labels, C = _kmeans(Z, k, rng)
        s = _silhouette(Z, labels)
        if verbose:
            print(f'  k={k}: силуэт {s:.3f}')
        if best is None or s > best[0]:
            best = (s, k, labels, C)

    score, k, labels, C = best
    styles = []
    for j in range(k):
        m = labels == j
        if not m.any():
            continue
        styles.append({
            'id': int(j),
            'count': int(m.sum()),
            'centroid_z': C[j].tolist(),
            'centroid': (C[j] * sigma + mu).tolist(),
            'mean_score': float(np.mean([entries[i]['score']
                                         for i in range(len(entries)) if m[i]])),
            'name': name_for(C[j]),
        })
    styles.sort(key=lambda s: -s['count'])
    return {'silhouette': round(score, 4), 'k': k, 'features': list(FEATURES),
            'mu': mu.tolist(), 'sigma': sigma.tolist(),
            'styles': styles, 'labels': labels.tolist(),
            'entries': entries, 'levels': levels}


def name_for(centroid_z):
    """Имя по двум самым выраженным отличиям плюс существительное по размаху."""
    order = sorted(range(len(FEATURES)), key=lambda i: -abs(centroid_z[i]))
    words = []
    for i in order[:2]:
        lo, hi = ADJECTIVES[FEATURES[i]]
        words.append(hi if centroid_z[i] > 0 else lo)

    size_z = centroid_z[FEATURES.index('size')]
    t = 1 / (1 + math.exp(-size_z))
    noun, gender = NOUNS[0][1], NOUNS[0][2]
    for thr, word, g in NOUNS:
        if t >= thr:
            noun, gender = word, g
    a, b = (_agree(w, gender) for w in words)
    return f'{a.capitalize()} {b} {noun}'


def assign(found, level, entry):
    """К какому найденному стилю относится карта."""
    if not found:
        return None
    mu = np.array(found['mu'])
    sigma = np.array(found['sigma'])
    z = (np.array(features_of(level, entry)) - mu) / sigma
    best, bd = None, None
    for s in found['styles']:
        d = float(((z - np.array(s['centroid_z'])) ** 2).sum())
        if bd is None or d < bd:
            best, bd = s, d
    return best


def save(found, path=FOUND_PATH):
    data = {k: found[k] for k in ('silhouette', 'k', 'features', 'mu', 'sigma')}
    data['styles'] = [{kk: s[kk] for kk in
                       ('id', 'count', 'centroid_z', 'centroid', 'mean_score', 'name')}
                      for s in found['styles']]
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False)
    return path


def load(path=FOUND_PATH):
    if not os.path.exists(path):
        return None
    with open(path, encoding='utf-8') as f:
        return json.load(f)

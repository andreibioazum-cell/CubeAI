"""Приёмка вкусовой части критика.

Запуск:  python calibrate_taste.py
"""

import copy
import statistics as st
import sys

from levelgen import STYLES, blend_styles, generate, generate_novel
from critic import evaluate
from clip_taste import available, build_anchors, status, taste

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def make_style(base='cave', **over):
    s = copy.deepcopy(STYLES[base])
    w = over.pop('weights', None)
    if w is not None:
        s['weights'] = {k: 0.0 for k in s['weights']}
        s['weights'].update(w)
    s.update(over)
    return s


DEGENERATE = {
    'кишка': make_style(weights={'corridor': 1.0}, branching=0.0,
                        symmetry=0.0, size=20),
    'пустой зал': make_style(weights={'yard': 1.0}, branching=0.9,
                             symmetry=0.0, size=24),
    'куча в углу': make_style(weights={'corridor': 1.0, 'turn': 2.0},
                              branching=1.0, symmetry=0.0, size=8),
    'монотонные комнаты': make_style(weights={'corridor': 1.0, 'room_small': 6.0},
                                     branching=0.3, symmetry=0.0, size=20),
}


def pearson(a, b):
    n = len(a)
    ma, mb = st.mean(a), st.mean(b)
    num = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    den = (sum((x - ma) ** 2 for x in a) * sum((y - mb) ** 2 for y in b)) ** 0.5
    return num / den if den else 0.0


def generalization(n=10):
    """Ловится ли уродство, которого нет в прототипах."""
    import numpy as np
    from clip_taste import embed, _degenerate_styles
    from render_iso import render

    print('\n=== обобщение на незнакомое уродство ===')
    deg = _degenerate_styles()
    emb_bad = {name: embed([render(generate(s)) for _ in range(n)])
               for name, s in deg.items()}
    emb_norm = embed([render(generate_novel(STYLES[k]))
                      for k in STYLES for _ in range(3)])

    ratios = []
    for held in deg:
        others = [x for x in deg if x != held]
        mat = np.stack([emb_bad[x].mean(0) / np.linalg.norm(emb_bad[x].mean(0))
                        for x in others])
        ns = (emb_norm @ mat.T).max(1)
        mu, sigma = ns.mean(), ns.std() + 1e-6

        def sc(e):
            return float(np.mean(1 / (1 + np.exp(-((mu - (e @ mat.T).max(1)) / sigma)))))

        h, nm = sc(emb_bad[held]), sc(emb_norm)
        ratios.append(h / nm if nm else 1.0)
        print(f'  без прототипа {held:12} его вкус {h:.3f}  норма {nm:.3f}  '
              f'просадка {(1 - h / nm) * 100:3.0f}%')
    return sum(ratios) / len(ratios)


def main():
    print(status())
    if not available():
        print('модель недоступна — приёмка невозможна')
        return 1
    build_anchors()

    styles = list(STYLES.values()) + [
        blend_styles('cave', 'mansion'), blend_styles('circus', 'island'),
    ]

    print('\n=== обычные карты ===')
    good_t, good_s = [], []
    for i in range(40):
        lv = generate_novel(styles[i % len(styles)])
        r = evaluate(lv)
        if r['rejected']:
            continue
        t = taste(lv)
        good_t.append(t)
        good_s.append(r['score'])
    print(f'вкус: {min(good_t):.3f} .. {max(good_t):.3f}, '
          f'среднее {st.mean(good_t):.3f}, разброс {st.pstdev(good_t):.3f}')

    print('\n=== вырожденные постройки ===')
    bad_t = []
    for name, style in DEGENERATE.items():
        ts = [taste(generate(style)) for _ in range(8)]
        bad_t += ts
        print(f'  {name:22} вкус {st.mean(ts):.3f}')

    thr = (st.mean(good_t) + st.mean(bad_t)) / 2
    acc = (sum(1 for t in good_t if t > thr) +
           sum(1 for t in bad_t if t <= thr)) / (len(good_t) + len(bad_t))
    gap = st.mean(good_t) - st.mean(bad_t)

    corr = pearson(good_t, good_s)

    print(f'\nобычные {st.mean(good_t):.3f} против вырожденных {st.mean(bad_t):.3f}')
    print(f'разделение по порогу: {acc * 100:.0f}%   зазор: {gap:+.3f}')
    print(f'корреляция со структурным счётом: {corr:+.3f}')

    holdout_ratio = generalization()

    ok = True
    if acc < 0.85:
        print('ПРОБЛЕМА: вкус плохо отделяет вырождение')
        ok = False
    if abs(corr) > 0.8:
        print('ПРОБЛЕМА: вкус дублирует структурный счёт, слагаемое лишнее')
        ok = False
    if st.pstdev(good_t) < 0.02:
        print('ПРОБЛЕМА: вкус одинаков у всех карт, различать нечем')
        ok = False
    if holdout_ratio > 0.75:
        print('ПРОБЛЕМА: вкус узнаёт только заложенные виды уродства')
        ok = False
    print(f'\nнезнакомое уродство проседает в среднем до '
          f'{holdout_ratio * 100:.0f}% от нормы')

    print('ИТОГ:', 'вкус работает и добавляет свой сигнал' if ok
          else 'вкус подключать нельзя')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())

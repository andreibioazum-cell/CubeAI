"""Приёмка критика.

Запуск:  python calibrate_critic.py
"""

import copy
import statistics as st
import sys
from collections import Counter, defaultdict

from levelgen import STYLES, blend_styles, generate, generate_novel
from critic import evaluate, describe

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass


def make_style(base='cave', **over):
    """Стиль-мутант для конструирования вырожденных карт."""
    s = copy.deepcopy(STYLES[base])
    weights = over.pop('weights', None)
    if weights is not None:
        s['weights'] = {k: 0.0 for k in s['weights']}
        s['weights'].update(weights)
    s.update(over)
    return s


DEGENERATE = {
    'кишка (одни коридоры)':
        make_style(weights={'corridor': 1.0}, branching=0.0, symmetry=0.0, size=20),
    'пустой зал (одни дворы)':
        make_style(weights={'yard': 1.0}, branching=0.9, symmetry=0.0, size=24),
    'куча в углу':
        make_style(weights={'corridor': 1.0, 'turn': 2.0}, branching=1.0,
                   symmetry=0.0, size=8),
    'монотонные комнаты':
        make_style(weights={'corridor': 1.0, 'room_small': 6.0},
                   branching=0.3, symmetry=0.0, size=20),
    'микрокарта':
        make_style(weights={'corridor': 1.0, 'dead_end': 3.0}, branching=0.0,
                   symmetry=0.0, size=3),
}


def sample_normal(n=200):
    styles = list(STYLES.values()) + [
        blend_styles('cave', 'mansion'), blend_styles('castle', 'candy'),
        blend_styles('circus', 'island'), blend_styles('cave', 'circus'),
    ]
    out = []
    for i in range(n):
        lv = generate_novel(styles[i % len(styles)])
        out.append((evaluate(lv), lv))
    return out


def main():
    print('=== 1. Обычные карты ===')
    rated = sample_normal(200)
    ok = [(r, lv) for r, lv in rated if not r['rejected']]
    scores = [r['score'] for r, _ in ok]
    print(f'оценено {len(rated)}, отклонено воротами {len(rated) - len(ok)}')
    print(f'счёт: {min(scores):.3f} .. {max(scores):.3f}, '
          f'среднее {st.mean(scores):.3f}, разброс {st.pstdev(scores):.3f}\n')

    per_style = defaultdict(list)
    for r, lv in ok:
        per_style[lv.style['name']].append(r['score'])
    for name, v in sorted(per_style.items(), key=lambda kv: -st.mean(kv[1])):
        print(f'  {name:34} {st.mean(v):.3f}  (n={len(v)})')

    ok.sort(key=lambda t: t[0]['score'], reverse=True)
    for title, items in (('ЛУЧШИЕ', ok[:2]), ('ХУДШИЕ', ok[-2:])):
        print(f'\n=== {title} ===')
        for r, lv in items:
            print(f'\n{lv.style["name"]} — {describe(r)}')
            print(lv.to_ascii())

    print('\n\n=== 2. Заведомо вырожденные карты ===')
    print('(каждая должна быть ниже 5-го процентиля обычных)\n')
    # Сравнивать с самой худшей обычной картой нельзя: одна неудачная
    # обычная карта задирала бы планку и делала проверку бессмысленной.
    ordered = sorted(scores)
    worst_normal = ordered[max(0, int(len(ordered) * 0.05) - 1)]
    bad_ok = True
    for name, style in DEGENERATE.items():
        rs = []
        for _ in range(6):
            lv = generate(style, seed=None)
            rs.append(evaluate(lv))
        alive = [r for r in rs if not r['rejected']]
        mean_score = st.mean([r['score'] for r in alive]) if alive else 0.0
        pens = Counter()
        for r in alive:
            pens.update(r['penalties'].keys())
        verdict = 'OK' if mean_score < worst_normal else 'ПРОБЛЕМА'
        if verdict != 'OK':
            bad_ok = False
        print(f'  {name:26} счёт {mean_score:.3f}  '
              f'отклонено {len(rs) - len(alive)}/6  '
              f'штрафы {dict(pens) or "—"}  {verdict}')

    print(f'\n5-й процентиль обычных: {worst_normal:.3f}')
    print('ИТОГ:', 'критик отличает вырождение'
          if bad_ok else 'ЕСТЬ ДЫРА — вырожденные карты проходят')
    return 0 if bad_ok else 1


if __name__ == '__main__':
    raise SystemExit(main())

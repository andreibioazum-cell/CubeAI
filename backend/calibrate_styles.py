"""Приёмка найденных стилей.

Запуск:  python calibrate_styles.py
"""

import statistics as st
import sys
from collections import defaultdict

import numpy as np

from archive import Archive
from genome import Genome
import styles_found as sf

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass


def spread_within(groups, Z):
    """Средний разброс внутри групп: чем меньше, тем описание точнее."""
    out = []
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        sub = Z[idxs]
        out.append(float(np.mean(np.linalg.norm(sub - sub.mean(0), axis=1))))
    return st.mean(out) if out else float('nan')


def main():
    arc = Archive()
    if not arc.load() or len(arc.cells) < 20:
        print('архив пуст или мал — сначала python evolve_modules.py 6')
        return 1

    print('=== 1. Поиск стилей ===')
    found = sf.discover(arc, verbose=True)
    if not found:
        print('слишком мало элиты для кластеризации')
        return 1
    print(f'\nвыбрано k={found["k"]}, силуэт {found["silhouette"]}\n')
    print(f'{"найденный стиль":40} {"карт":>5} {"счёт":>7}')
    for s in found['styles']:
        print(f'{s["name"]:40} {s["count"]:5} {s["mean_score"]:7.3f}')

    entries, levels, labels = found['entries'], found['levels'], found['labels']
    X = np.array([sf.features_of(lv, e) for lv, e in zip(levels, entries)])
    Z = (X - np.array(found['mu'])) / np.array(found['sigma'])

    print('\n=== 2. Характер против происхождения ===')
    by_cluster = defaultdict(list)
    by_lineage = defaultdict(list)
    for i, (e, lv) in enumerate(zip(entries, levels)):
        by_cluster[labels[i]].append(i)
        by_lineage[lv.style['name']].append(i)

    # Сравнивать надо при равном числе групп: чем больше групп, тем они
    # плотнее сами по себе, и 8 кластеров против 15 родословных — сравнение
    # не в пользу кластеров просто по арифметике.
    sl = spread_within(by_lineage, Z)
    k_lin = sum(1 for v in by_lineage.values() if len(v) >= 2)
    matched = sf.discover(arc, k_range=(k_lin, k_lin), seed=0)
    by_matched = defaultdict(list)
    for i, lab in enumerate(matched['labels']):
        by_matched[lab].append(i)
    sc_matched = spread_within(by_matched, Z)
    sc = spread_within(by_cluster, Z)

    print(f'групп по родословной: {len(by_lineage)} '
          f'(содержательных {k_lin}), разброс внутри {sl:.3f}')
    print(f'кластеров при том же числе групп: {k_lin}, '
          f'разброс внутри {sc_matched:.3f}')
    print(f'кластеров по силуэту: {len(by_cluster)}, разброс внутри {sc:.3f}')
    if sl and sc_matched < sl:
        print(f'характер описывает карту на '
              f'{(1 - sc_matched / sl) * 100:.0f}% точнее происхождения')
    else:
        print('родословная описывает не хуже характера')
    sc = sc_matched

    print('\n=== 3. Устойчивость к случайному зерну ===')
    base = np.array(labels)
    agrees = []
    for seed in (1, 2, 3):
        other = sf.discover(arc, seed=seed)
        ol = np.array(other['labels'])
        # доля пар, которые обе разметки относят одинаково (вместе/врозь)
        same_a = base[:, None] == base[None, :]
        same_b = ol[:, None] == ol[None, :]
        n = len(base)
        agree = (same_a == same_b).sum() - n
        agrees.append(agree / (n * n - n))
    print(f'совпадение разбиений при разных зёрнах: '
          f'{st.mean(agrees) * 100:.0f}%')

    print('\n=== 4. Пример из самого крупного стиля ===')
    big = found['styles'][0]
    idxs = by_cluster[big['id']]
    i = max(idxs, key=lambda j: entries[j]['score'])
    print(f'{big["name"]} — счёт {entries[i]["score"]:.3f}, '
          f'родословная «{levels[i].style["name"]}»')
    print(levels[i].to_ascii()[:900])

    ok = True
    if found['silhouette'] <= 0:
        print('\nПРОБЛЕМА: кластеры не выделяются')
        ok = False
    if not (sc < sl):
        print('\nПРОБЛЕМА: характер описывает карту не лучше родословной')
        ok = False
    if st.mean(agrees) < 0.7:
        print('\nПРОБЛЕМА: разбиение неустойчиво')
        ok = False

    sf.save(found)
    print('\nИТОГ:', 'стили найдены и осмысленны' if ok else 'есть проблема')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())

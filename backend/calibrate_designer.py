"""Приёмка сети-проектировщика.

Запуск:  python calibrate_designer.py [сколько_карт]
"""

import random
import statistics as st
import sys
import time

import numpy as np

from archive import Archive
from critic import evaluate
from genome import Genome
from hands import build_steps
from levelgen import STYLES, generate_novel
import designer
import modgen

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

TARGETS = [
    ('тесное древовидное малое',   {'openness': 0.32, 'loops': 0.05, 'size': 12}),
    ('просторное кольцевое малое', {'openness': 0.46, 'loops': 0.80, 'size': 14}),
    ('среднее умеренное',          {'openness': 0.39, 'loops': 0.40, 'size': 28}),
    ('просторное кольцевое большое', {'openness': 0.47, 'loops': 0.85, 'size': 48}),
]


def descriptor_of(level, result):
    return {'openness': level.descriptor['openness'],
            'loops': result['terms'].get('loops', 0.0),
            'size': level.descriptor['size']}


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    modgen.load()
    model, vocab = designer.load()
    if model is None:
        print('модель не обучена — сначала python train_designer.py')
        return 1
    rng = random.Random(5)

    print('=== 1. Валидность и качество ===')
    scores, descs, t_design = [], [], []
    broken = rejected = bad_build = 0
    t0 = time.time()
    for i in range(n):
        name, target = TARGETS[i % len(TARGETS)]
        t1 = time.time()
        gm = designer.design(model, vocab, target, rng=rng)
        t_design.append(time.time() - t1)
        lv = gm.decode()
        if lv is None:
            broken += 1
            continue
        r = evaluate(lv, rng=rng)
        if r['rejected']:
            rejected += 1
            continue
        if build_steps(lv).report()['coverage'] < 1.0:
            bad_build += 1
        scores.append(r['score'])
        descs.append((name, target, descriptor_of(lv, r)))
    total = time.time() - t0

    valid = len(scores)
    print(f'спроектировано {n}: валидных {valid}, развалилось {broken}, '
          f'отклонено воротами {rejected}, недостроено руками {bad_build}')
    if not valid:
        print('ИТОГ: сеть не выдаёт валидных карт')
        return 1
    print(f'счёт сети: {min(scores):.3f}..{max(scores):.3f}, '
          f'среднее {st.mean(scores):.3f}')

    print('\n=== 2. С чем сравниваем ===')
    gram = []
    styles = list(STYLES.values())
    for i in range(40):
        lv = generate_novel(styles[i % len(styles)])
        r = evaluate(lv, rng=rng)
        if not r['rejected']:
            gram.append(r['score'])
    arc = Archive()
    arc.load()
    elite = [e['score'] for e in arc.elites()]
    print(f'грамматика (нижняя планка): {st.mean(gram):.3f}')
    print(f'сеть:                       {st.mean(scores):.3f}')
    print(f'элита архива (перебор):     {st.mean(elite):.3f}')

    print('\n=== 3. Скорость ===')
    print(f'проектирование одной карты: {st.mean(t_design) * 1000:.0f} мс')
    print(f'полный цикл с оценкой:      {total / n * 1000:.0f} мс')
    print(f'эволюция тратит на карту такого качества сотни оценок '
          f'(~{1 / 23 * 1000:.0f} мс каждая)')

    print('\n=== 4. Слушается ли заказа ===')
    ok_cond = True
    for name, target, _ in [(t[0], t[1], None) for t in TARGETS]:
        got = [d for nm, tg, d in descs if nm == name]
        if not got:
            continue
        for key in ('openness', 'loops', 'size'):
            mean = st.mean([g[key] for g in got])
            print(f'  {name:30} {key:9} заказ {target[key]:6.2f} → '
                  f'получено {mean:6.2f}')
    # корреляция заказа и результата по размеру и петлистости
    for key in ('size', 'loops', 'openness'):
        want = np.array([tg[key] for _, tg, _ in descs], dtype=float)
        got = np.array([d[key] for _, _, d in descs], dtype=float)
        if want.std() < 1e-9 or got.std() < 1e-9:
            continue
        r = float(np.corrcoef(want, got)[0, 1])
        print(f'  корреляция заказа и результата по {key}: {r:+.2f}')
        if key in ('size',) and r < 0.3:
            ok_cond = False

    print('\n=== 5. Разнообразие ===')
    uniq = len({tuple(round(d[k], 2) for k in ('openness', 'loops', 'size'))
                for _, _, d in descs})
    print(f'уникальных дескрипторов: {uniq} из {valid}')

    ok = True
    if valid / n < 0.6:
        print('\nПРОБЛЕМА: слишком много выборок не доживает до валидной карты')
        ok = False
    if bad_build:
        print('\nПРОБЛЕМА: карты сети не достраиваются руками')
        ok = False
    if st.mean(scores) < st.mean(gram):
        print('\nПРОБЛЕМА: сеть проектирует хуже грамматики')
        ok = False
    if not ok_cond:
        print('\nПРОБЛЕМА: заказ не влияет на результат')
        ok = False
    if uniq < valid * 0.5:
        print('\nПРОБЛЕМА: сеть схлопнулась в один образец')
        ok = False

    print('\nИТОГ:', 'сеть проектирует и слушается заказа' if ok
          else 'есть проблема')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())

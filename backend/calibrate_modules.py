"""Приёмка эволюции словаря.

Запуск:  python calibrate_modules.py [оценок_на_прогон]
"""

import os
import random
import statistics as st
import sys
from collections import Counter

from modules import MODULES, BASE_MODULE_NAMES
import modgen
from archive import Archive
from evolve import run, seed
from evolve_modules import run_rounds, usage
from genome import Genome
from hands import build_steps

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass


def clean_slate():
    for n in modgen.invented_names():
        MODULES.pop(n, None)
    from modules import VARIANTS
    for n in list(VARIANTS):
        if n not in MODULES:
            VARIANTS.pop(n, None)


def gates_hold(archive):
    bad_reach = bad_build = 0
    for e in archive.elites():
        lv = Genome.from_dict(e['genome']).decode()
        if lv is None:
            bad_build += 1
            continue
        if lv.descriptor['reachability'] < 0.999:
            bad_reach += 1
        if build_steps(lv).report()['coverage'] < 1.0:
            bad_build += 1
    return bad_reach, bad_build


def base_dictionary_holds():
    """Рукописный словарь проходит те же ворота, что и изобретения Кейна."""
    import numpy as np
    from modules import MODULES

    bad = []
    for name in sorted(MODULES):
        why = modgen.validate(np.array(MODULES[name]['grid']))
        if why:
            bad.append((name, why))
            continue
        ok, why = modgen.buildable_by_hands(name)
        if not ok:
            bad.append((name, why))
    print(f'модулей в словаре: {len(MODULES)}, с проблемами: {len(bad)}')
    for name, why in bad:
        print(f'  ПРОБЛЕМА {name}: {why}')
    return not bad


def main():
    evals = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
    rounds = 4
    per_round = evals // rounds

    print('=== 0. Рукописный словарь проходит те же ворота ===')
    base_ok = base_dictionary_holds()

    print()
    print('=== A. Только рукописный словарь ===')
    clean_slate()
    rng = random.Random(11)
    arc_a = Archive(path=os.path.join(os.path.dirname(__file__), 'archive_a.json'))
    seed(arc_a, rng)
    run(evals, archive=arc_a, rng=rng, log_every=evals, save_every=evals * 10)
    a = arc_a.stats()
    print(f'словарь {len(MODULES)}, ниш {a["cells"]}, '
          f'средний {a["mean_score"]:.4f}, лучший {a["best_score"]:.4f}')

    print('\n=== B. Словарь пополняется изобретениями ===')
    clean_slate()
    rng = random.Random(11)
    arc_b = Archive(path=os.path.join(os.path.dirname(__file__), 'archive_b.json'))
    seed(arc_b, rng)
    run_rounds(rounds, archive=arc_b, rng=rng, evals=per_round, verbose=False)
    b = arc_b.stats()
    invented = modgen.invented_names()
    print(f'словарь {len(MODULES)} ({len(invented)} изобретений), '
          f'ниш {b["cells"]}, средний {b["mean_score"]:.4f}, '
          f'лучший {b["best_score"]:.4f}')

    print('\n=== Сравнение ===')
    print(f'{"":22}{"A: рукописный":>16}{"B: с изобретениями":>22}')
    for key, label in (('cells', 'занятых ниш'), ('mean_score', 'средний счёт'),
                       ('best_score', 'лучшая карта')):
        print(f'{label:22}{a[key]:>16}{b[key]:>22}')

    print('\n=== Прижились ли изобретения ===')
    count, value = usage(arc_b)
    n_elites = len(arc_b.elites())
    base_use = [count.get(n, 0) for n in BASE_MODULE_NAMES if n != 'gate']
    inv_use = [count.get(n, 0) for n in invented]
    print(f'элитников: {n_elites}')
    print(f'встречаемость рукописного модуля: '
          f'{st.mean(base_use) / n_elites * 100:.0f}% карт')
    if inv_use:
        print(f'встречаемость изобретённого:      '
              f'{st.mean(inv_use) / n_elites * 100:.0f}% карт')

    top = sorted(invented, key=lambda n: -count.get(n, 0))[:3]
    for n in top:
        if count.get(n, 0) == 0:
            continue
        print(f'\n{MODULES[n]["role"]}, в {count[n]} картах из {n_elites}, '
              f'средний счёт этих карт {value[n]:.3f}')
        print(modgen.to_ascii(n))

    print('\n=== Жёсткие ворота при расширенном словаре ===')
    br, bb = gates_hold(arc_b)
    print(f'непроходимых: {br}, недостроенных руками: {bb}')

    ok = base_ok
    if br or bb:
        print('ПРОБЛЕМА: изобретённые модули ломают ворота')
        ok = False
    if b['mean_score'] < a['mean_score'] * 0.9:
        print('ПРОБЛЕМА: расширение словаря заметно ухудшило качество')
        ok = False
    if not inv_use or max(inv_use) == 0:
        print('ПРОБЛЕМА: ни одно изобретение не используется')
        ok = False

    print('\nИТОГ:', 'словарь эволюционирует и не вредит' if ok else 'есть проблема')
    for p in (arc_a.path, arc_b.path):
        if os.path.exists(p):
            os.remove(p)
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())

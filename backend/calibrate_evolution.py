"""Приёмка эволюции: действительно ли Кейн становится лучше.

Запуск:  python calibrate_evolution.py [число_оценок]
"""

import random
import statistics as st
import sys

from levelgen import STYLES, blend_styles, generate_novel
from genome import Genome
from critic import evaluate
from archive import Archive, AXES, TOTAL_CELLS
from hands import build_steps
from evolve import run, seed, describe_level

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass


def baseline(rng, n=60):
    """Что умеет одна грамматика, без эволюции."""
    styles = list(STYLES.values()) + [
        blend_styles('cave', 'mansion'), blend_styles('castle', 'candy'),
        blend_styles('circus', 'island'), blend_styles('cave', 'circus'),
    ]
    scores, descs = [], []
    for i in range(n):
        lv = generate_novel(styles[i % len(styles)])
        r = evaluate(lv, rng=rng)
        if r['rejected']:
            continue
        scores.append(r['score'])
        descs.append(describe_level(lv, r))
    return scores, descs


def spread(descs):
    """Средний разброс по осям архива — грубая мера разнообразия."""
    if len(descs) < 2:
        return 0.0
    out = []
    for name, lo, hi, _ in AXES:
        vals = [(d[name] - lo) / (hi - lo) for d in descs]
        out.append(st.pstdev(vals))
    return sum(out) / len(out)


def main():
    evals = int(sys.argv[1]) if len(sys.argv) > 1 else 6000
    rng = random.Random(7)

    print('=== 1. Базовый уровень: одна грамматика ===')
    base_scores, base_descs = baseline(rng)
    print(f'{len(base_scores)} карт, средний счёт {st.mean(base_scores):.4f}, '
          f'лучшая {max(base_scores):.4f}, разброс по осям {spread(base_descs):.3f}')

    arc = Archive(path=None or Archive().path)
    arc.cells = {}
    seed(arc, rng)
    seed_cells = len(arc.cells)
    seed_mean = arc.mean_score()
    print(f'грамматика засеяла ниш: {seed_cells} из {TOTAL_CELLS}, '
          f'средний {seed_mean:.4f}')

    print(f'\n=== 2. Эволюция, {evals} оценок ===')
    arc, history = run(evals, archive=arc, rng=rng, log_every=max(250, evals // 8))

    s = arc.stats()
    print(f'\nниш: {seed_cells} → {s["cells"]}  '
          f'(рост в {s["cells"] / max(seed_cells, 1):.1f} раза)')
    print(f'средний счёт элиты: {seed_mean:.4f} → {s["mean_score"]:.4f}')
    print(f'лучший: {max(base_scores):.4f} (грамматика) → {s["best_score"]:.4f}')

    print('\n=== 3. Жёсткие ворота на всей элите ===')
    bad_reach = bad_build = 0
    sizes = []
    for e in arc.elites():
        gm = Genome.from_dict(e['genome'])
        lv = gm.decode()
        if lv is None:
            bad_build += 1
            continue
        if lv.descriptor['reachability'] < 0.999:
            bad_reach += 1
        rep = build_steps(lv).report()
        if rep['coverage'] < 1.0:
            bad_build += 1
        sizes.append(rep['blocks_placed'])
    print(f'элитников: {len(arc.elites())}, '
          f'непроходимых: {bad_reach}, недостроенных руками: {bad_build}')
    print(f'блоков в карте: {min(sizes)}–{max(sizes)} (среднее {round(st.mean(sizes))})')

    print('\n=== 4. Разнообразие ===')
    elite_descs = [e['desc'] for e in arc.elites()]
    print(f'разброс по осям: грамматика {spread(base_descs):.3f} → '
          f'элита {spread(elite_descs):.3f}')

    ok = True
    if s['mean_score'] <= seed_mean:
        print('ПРОБЛЕМА: средний счёт элиты не вырос')
        ok = False
    if s['cells'] <= seed_cells:
        print('ПРОБЛЕМА: архив не расширился')
        ok = False
    if bad_reach or bad_build:
        print('ПРОБЛЕМА: оптимизация ломает жёсткие ворота')
        ok = False
    if spread(elite_descs) < spread(base_descs) * 0.9:
        print('ПРОБЛЕМА: эволюция сузила разнообразие')
        ok = False

    print('\nИТОГ:', 'Кейн учится и не жульничает' if ok else 'есть проблема')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())

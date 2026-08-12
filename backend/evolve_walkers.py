"""Эволюция мозгов гуляк.

Запуск:  python evolve_walkers.py [поколений]
"""

import random
import statistics as st
import sys
import time

import numpy as np

from archive import Archive
from critic import goal_cell
from genome import Genome
import modgen
import walkers

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

MU, LAMBDA = 10, 40
SIGMA0 = 0.5
TRAIN_N, TRAIN_STEPS = 8, 380      # облегчённый режим на время отбора
MAPS_PER_GEN = 8


def load_maps(limit=140):
    modgen.load()
    a = Archive()
    if not a.load():
        return []
    out = []
    for e in a.elites()[:limit]:
        lv = Genome.from_dict(e['genome']).decode()
        if lv is None:
            continue
        dist = lv.distances()
        goal = goal_cell(lv)
        if goal is None or len(dist) < 40:
            continue
        out.append((lv, dist, goal))
    return out


def fitness(theta, maps, n=TRAIN_N, steps=TRAIN_STEPS):
    """Чем кончилась прогулка: дошёл, много ли обошёл, быстро ли."""
    total = 0.0
    for lv, dist, goal in maps:
        reach, mtime, cov = walkers.simulate(lv, dist, goal, theta,
                                             n=n, steps=steps)
        total += 0.55 * cov + 0.35 * reach + 0.10 * (1.0 - mtime)
    return total / max(len(maps), 1)


def run(generations=40, seed=0, verbose=True):
    rng = np.random.default_rng(seed)
    pool = load_maps()
    if len(pool) < 20:
        raise RuntimeError('в архиве слишком мало карт для обучения')

    # Держим часть карт в стороне: на них мозг не учится ни разу.
    holdout = pool[:16]
    train = pool[16:]

    parents = [walkers.seed_brain(rng) for _ in range(MU)]

    sigma = SIGMA0
    history = []
    t0 = time.time()
    best_theta, best_val = None, -1e9

    for g in range(1, generations + 1):
        maps = [train[i] for i in rng.choice(len(train), MAPS_PER_GEN,
                                             replace=False)]
        kids = []
        for _ in range(LAMBDA):
            p = parents[rng.integers(len(parents))]
            kids.append(p + rng.normal(0, sigma, walkers.N_PARAMS))
        # Родители пересчитываются на новой выборке карт вместе с детьми:
        # иначе выживает не лучший мозг, а тот, кому достались лёгкие карты.
        cand = [(fitness(k, maps), k) for k in kids]
        cand += [(fitness(p, maps), p) for p in parents]
        scored = sorted(cand, key=lambda kv: -kv[0])
        parents = [k for _, k in scored[:MU]]

        top = scored[0][0]
        if top > best_val:
            best_val, best_theta = top, scored[0][1]
        sigma = max(0.05, sigma * 0.97)

        if verbose and (g % max(1, generations // 10) == 0 or g == 1):
            hv = fitness(parents[0], holdout[:6])
            history.append({'gen': g, 'train': round(top, 4),
                            'holdout': round(hv, 4)})
            print(f'  поколение {g:3}  обучение {top:.4f}  '
                  f'проверка {hv:.4f}  шаг {sigma:.3f}  '
                  f'{time.time() - t0:.0f} с')

    return best_theta, holdout, train, history


def report(theta, maps, label, n=walkers.DEFAULT_N, steps=walkers.DEFAULT_STEPS):
    rs, cs, ts = [], [], []
    for lv, dist, goal in maps:
        r, mt, c = walkers.simulate(lv, dist, goal, theta, n=n, steps=steps,
                                    rng=random.Random(0))
        rs.append(r); cs.append(c); ts.append(mt)
    print(f'{label:24} нашли {st.mean(rs) * 100:5.1f}%   '
          f'обошли {st.mean(cs) * 100:5.1f}%   время {st.mean(ts):.3f}')
    return st.mean(rs), st.mean(cs), st.mean(ts)


def main():
    gens = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    print(f'=== Отбор мозгов ({walkers.N_PARAMS} чисел, {gens} поколений) ===')
    theta, holdout, train, hist = run(gens)

    print('\n=== Проверка на картах, которых мозг не видел ===')
    n_r, n_c, _ = report(walkers.NAIVE, holdout, 'бродяга без памяти')
    e_r, e_c, _ = report(theta, holdout, 'эволюционировавший')

    print('\n=== На обучающих картах (для сравнения) ===')
    t_r, t_c, _ = report(theta, train[:16], 'эволюционировавший')

    ok = True
    if e_c <= n_c:
        print('\nПРОБЛЕМА: мозг обходит карту не лучше бродяги без памяти')
        ok = False
    if e_c < t_c * 0.75:
        print('\nПРОБЛЕМА: мозг переобучился под обучающие карты')
        ok = False

    if ok:
        walkers.save(theta, meta={'holdout_coverage': e_c,
                                  'holdout_reach': e_r})
        print(f'\nсохранено: {walkers.BRAIN_PATH}')

    print('\nИТОГ:', 'гуляки научились ходить' if ok else 'есть проблема')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())

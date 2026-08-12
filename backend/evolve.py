"""Эволюция карт: Кейн становится лучше от поколения к поколению.

Запуск:
    python evolve.py 4000          # 4000 оценок
    python evolve.py 4000 --fresh  # начать архив с нуля
"""

import random
import sys
import time

from levelgen import STYLES, blend_styles, generate_novel
from genome import Genome, mutate, crossover
from critic import evaluate
from archive import Archive

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

CROSSOVER_RATE = 0.25
SEED_PER_STYLE = 3


def describe_level(level, result):
    """Дескриптор для осей архива. loops берётся из критика, потому что"""
    return {
        'openness': level.descriptor['openness'],
        'loops': result['terms'].get('loops', 0.0),
        'size': level.descriptor['size'],
    }


def seed(archive, rng, verbose=True, bias=None):
    """Начальная популяция — карты, порождённые грамматикой."""
    if bias:
        # Своя начальная популяция — единственный способ развести двух
        # строителей по-настоящему: с общего архива они остаются клонами,
        # сколько их потом ни мутируй.
        keys = [k for k in bias if k in STYLES]
        styles = [STYLES[k] for k in keys]
        styles += [blend_styles(a, b) for a in keys for b in keys if a < b]
    else:
        styles = list(STYLES.values()) + [
            blend_styles('cave', 'mansion'), blend_styles('castle', 'candy'),
            blend_styles('circus', 'island'), blend_styles('cave', 'circus'),
            blend_styles('city', 'castle'), blend_styles('city', 'candy'),
        ]
    n = 0
    for st in styles:
        for _ in range(SEED_PER_STYLE):
            lv = generate_novel(st)
            r = evaluate(lv, rng=rng)
            if r['rejected']:
                continue
            gm = Genome.from_level(lv)
            if archive.add(gm, r['score'], describe_level(lv, r), r['terms']):
                n += 1
    if verbose:
        print(f'засеяно ниш: {n} из {len(styles) * SEED_PER_STYLE} карт')
    return n


def run(evals=4000, archive=None, rng=None, log_every=250, save_every=1000,
        verbose=True, corpus=None):
    rng = rng or random.Random()
    archive = archive or Archive()
    if not archive.cells:
        seed(archive, rng, verbose)

    history = []
    t0 = time.time()
    rejected = 0
    broken = 0

    for i in range(1, evals + 1):
        elites = archive.elites()
        parent = Genome.from_dict(rng.choice(elites)['genome'])

        if len(elites) > 1 and rng.random() < CROSSOVER_RATE:
            other = Genome.from_dict(rng.choice(elites)['genome'])
            child = crossover(parent, other, rng)
            child = mutate(child, rng, k=1)
        else:
            child = mutate(parent, rng)

        lv = child.decode()
        if lv is None:
            broken += 1
            continue
        r = evaluate(lv, rng=rng)
        if r['rejected']:
            rejected += 1
            continue
        desc = describe_level(lv, r)
        archive.add(child, r['score'], desc, r['terms'])
        if corpus is not None:
            # в корпус идёт всё приличное, а не только элита: эволюция
            # по дороге производит тысячи годных примеров
            corpus.add(child, r['score'], desc)

        if i % log_every == 0:
            s = archive.stats()
            history.append({'eval': i, **s})
            if verbose:
                print(f'{i:6}  ниш {s["cells"]:4}/{s["total_cells"]} '
                      f'({s["fill"] * 100:4.1f}%)  средний {s["mean_score"]:.4f}  '
                      f'лучший {s["best_score"]:.4f}  '
                      f'{i / (time.time() - t0):.0f} оц/с')
        if i % save_every == 0:
            archive.save()

    archive.save()
    if verbose:
        dt = time.time() - t0
        print(f'\n{evals} оценок за {dt:.0f} с ({evals / dt:.0f} оц/с), '
              f'развалилось {broken}, отклонено воротами {rejected}')
        print('архив:', archive.stats())
    return archive, history


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    fresh = '--fresh' in sys.argv
    arc = Archive()
    if not fresh and arc.load():
        print(f'архив загружен: {arc.stats()}')
    run(n, archive=arc)

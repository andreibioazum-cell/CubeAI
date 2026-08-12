"""Эволюция словаря: Кейн изобретает собственные элементы.

Запуск:
    python evolve_modules.py 6            # 6 раундов
    python evolve_modules.py 6 --fresh    # с чистым архивом и словарём
"""

import random
import sys
from collections import Counter, defaultdict

from modules import MODULES, BASE_MODULE_NAMES, unregister_module
import modgen
from archive import Archive
from evolve import run, seed

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

NEW_PER_ROUND = 4
EVALS_PER_ROUND = 1500

# Сколько изобретений живёт одновременно. Замер на равном бюджете: словарь
# из 29 модулей давал средний счёт 0.718 против 0.755 у рукописных одиннадцати
# — каждый лишний элемент расширяет пространство поиска, и на его обход нужны
# оценки. Поэтому пул держится узким, а конкуренция за место — жёсткой.
POOL_CAP = 6


def usage(archive):
    """Сколько раз каждый модуль встречается в элите и каков средний счёт"""
    count = Counter()
    scores = defaultdict(list)
    for e in archive.elites():
        names = {t[1] for t in e['genome']['tiles']}
        for n in names:
            count[n] += 1
            scores[n].append(e['score'])
    return count, {n: sum(v) / len(v) for n, v in scores.items()}


# Чем заменять вымерший модуль: близкий по роли элемент из базового словаря
SUBSTITUTE = {
    'junction': 'cross', 'arena': 'cross', 'room': 'room_small',
    'dead_end': 'dead_end', 'corridor': 'corridor', 'tower': 'tower',
    'yard': 'yard', 'gate': 'gate',
}


def rehome_elites(archive, name, rng):
    """Пересадить карты с вымершего модуля на базовый."""
    from critic import evaluate
    from genome import Genome
    from evolve import describe_level

    sub = SUBSTITUTE.get(MODULES.get(name, {}).get('role', ''), 'corridor')
    touched = [cell for cell, e in archive.cells.items()
               if any(t[1] == name for t in e['genome']['tiles'])]
    saved = lost = 0
    for cell in touched:
        entry = archive.cells.pop(cell)
        d = entry['genome']
        d['tiles'] = [[p, (sub if n == name else n), r, f, s]
                      for p, n, r, f, s in d['tiles']]
        gm = Genome.from_dict(d)
        lv = gm.decode()
        if lv is None:
            lost += 1
            continue
        res = evaluate(lv, rng=rng)
        if res['rejected']:
            lost += 1
            continue
        archive.add(gm, res['score'], describe_level(lv, res), res['terms'])
        saved += 1
    return saved, lost


def prune(archive, count, value=None, rng=None, verbose=True,
          keep_unused=False):
    """Вымирание: сначала невостребованные, потом лишние сверх лимита."""
    import random as _r
    rng = rng or _r.Random()
    value = value or {}
    invented = modgen.invented_names()
    killed = []

    if not keep_unused:
        for n in invented:
            if count.get(n, 0) == 0:
                unregister_module(n)
                killed.append(n)

    alive = [n for n in modgen.invented_names()]
    if len(alive) > POOL_CAP:
        # вытесняем наименее востребованные, а при равной востребованности —
        # те, что живут в картах послабее
        alive.sort(key=lambda n: (count.get(n, 0), value.get(n, 0.0)))
        for n in alive[:len(alive) - POOL_CAP]:
            saved, lost = rehome_elites(archive, n, rng)
            unregister_module(n)
            killed.append(n)
            if verbose and (saved or lost):
                print(f'  {n[:10]}: пересажено карт {saved}, потеряно {lost}')

    if verbose and killed:
        print(f'  вымерло изобретений: {len(killed)}')
    return killed


def run_rounds(rounds=6, archive=None, rng=None, evals=EVALS_PER_ROUND,
               verbose=True):
    rng = rng or random.Random()
    archive = archive or Archive()
    if not archive.cells:
        seed(archive, rng, verbose)

    history = []
    for r in range(1, rounds + 1):
        born = [modgen.invent(rng) for _ in range(NEW_PER_ROUND)]
        born = [b for b in born if b]
        if verbose:
            print(f'\n--- раунд {r}: придумано {len(born)}, '
                  f'словарь {len(MODULES)} ---')

        run(evals, archive=archive, rng=rng, log_every=evals,
            save_every=evals, verbose=verbose)

        count, value = usage(archive)
        adopted = [n for n in modgen.invented_names() if count.get(n, 0) > 0]
        if verbose:
            print(f'  прижилось изобретений: {len(adopted)} '
                  f'из {len(modgen.invented_names())}')
        prune(archive, count, value, rng, verbose)
        modgen.save()

        s = archive.stats()
        history.append({'round': r, 'modules': len(MODULES),
                        'invented': len(modgen.invented_names()),
                        'adopted': len(adopted), **s})

    archive.save()
    return archive, history


if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    fresh = '--fresh' in sys.argv
    arc = Archive()
    if fresh:
        import os
        for p in (arc.path, modgen.INVENTED_PATH):
            if os.path.exists(p):
                os.remove(p)
    else:
        modgen.load()
        arc.load()
    print(f'словарь на старте: {len(MODULES)} модулей '
          f'({len(modgen.invented_names())} изобретённых)')
    arc, hist = run_rounds(n, archive=arc)
    print('\nитог:', arc.stats())
    print(f'словарь: {len(MODULES)} модулей, '
          f'изобретений выжило {len(modgen.invented_names())}')

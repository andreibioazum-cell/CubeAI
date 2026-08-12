"""Набрать корпус карт для обучения проектировщика.

Запуск:  python collect_corpus.py 20000
"""
import random
import sys

from archive import Archive
from corpus import Corpus, stats
from evolve import run
import modgen

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

if __name__ == '__main__':
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    fresh = '--fresh' in sys.argv
    modgen.load()
    arc = Archive()
    arc.load()
    print(f'старт: архив {len(arc.cells)} ниш, словарь с {len(modgen.invented_names())} изобретениями')
    with Corpus().open(append=not fresh) as c:
        run(n, archive=arc, rng=random.Random(), log_every=n // 8,
            save_every=n // 4, corpus=c)
        print(f'записано в корпус: {c.n}')
    print('корпус:', stats())

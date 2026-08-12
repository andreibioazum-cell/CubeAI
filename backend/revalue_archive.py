"""Пересчитать архив новым критиком.

Запуск:  python revalue_archive.py
"""

import os
import shutil
import statistics as st
import sys

from archive import Archive
from critic import evaluate
from evolve import describe_level
from genome import Genome
import modgen

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

HERE = os.path.dirname(__file__)


def main():
    modgen.load()
    a = Archive()
    if not a.load():
        print('архив не найден')
        return 1

    backup = os.path.join(HERE, 'archive.before-brains.json')
    if not os.path.exists(backup):
        shutil.copy2(os.path.join(HERE, 'archive.json'), backup)
        print(f'копия «до» сохранена: {os.path.basename(backup)}')

    before = [e['score'] for e in a.elites()]
    fresh = Archive()
    kept = dropped = 0
    for e in a.elites():
        gm = Genome.from_dict(e['genome'])
        lv = gm.decode()
        if lv is None:
            dropped += 1
            continue
        r = evaluate(lv)
        if r['rejected']:
            dropped += 1
            continue
        fresh.add(gm, r['score'], describe_level(lv, r), r['terms'])
        kept += 1

    after = [e['score'] for e in fresh.elites()]
    if not after:
        print('пересчёт не дал ни одной карты — архив не тронут')
        return 1
    fresh.save()

    print(f'пересчитано: оставлено {kept}, отброшено {dropped}')
    print(f'ниш: {len(before)} → {len(after)}')
    print(f'средний счёт: {st.mean(before):.4f} → {st.mean(after):.4f}')
    print(f'лучший: {max(before):.4f} → {max(after):.4f}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

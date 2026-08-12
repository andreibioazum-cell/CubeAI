"""Поднять живость цвета у карт, накопленных до починки мутации палитры.

Запуск:  python resaturate_archive.py
"""
import sys

from archive import Archive
from genome import palette_saturation, saturate, SATURATION_FLOOR
import modgen

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

if __name__ == '__main__':
    modgen.load()
    a = Archive()
    if not a.load():
        print('архив не найден')
        raise SystemExit(1)
    before, fixed = [], 0
    for e in a.elites():
        pal = e['genome']['style']['palette']
        before.append(palette_saturation(pal))
        if palette_saturation(pal) < SATURATION_FLOOR:
            e['genome']['style']['palette'] = saturate(pal, SATURATION_FLOOR)
            fixed += 1
    after = [palette_saturation(e['genome']['style']['palette']) for e in a.elites()]
    a.save()
    n = len(before)
    print(f'элитников {n}, поправлено {fixed}')
    print(f'насыщенность: было {sum(before)/n:.3f}, стало {sum(after)/n:.3f}')
    print(f'ниже порога: было {sum(1 for x in before if x < SATURATION_FLOOR)/n*100:.0f}%, '
          f'стало {sum(1 for x in after if x < SATURATION_FLOOR)/n*100:.0f}%')

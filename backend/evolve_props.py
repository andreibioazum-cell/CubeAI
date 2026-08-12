"""Эволюция реквизита: Кейн придумывает предметы и отбирает лучшие.

Запуск:  python evolve_props.py 4000
"""

import random
import statistics as st
import sys
import time

import props

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

H_BINS = (0.35, 0.6, 0.85)
W_BINS = (0.35, 0.5, 0.65)
POOL_CAP = 24                # сколько предметов уезжает в показ


def niche(prop):
    d = props.descriptor(prop)
    h = sum(1 for b in H_BINS if d['height'] > b)
    w = sum(1 for b in W_BINS if d['width'] > b)
    return (h, w, min(d['parts'], props.MAX_PARTS))


class PropArchive:
    def __init__(self):
        self.cells = {}

    def add(self, prop, q=None):
        q = props.quality(prop) if q is None else q
        key = niche(prop)
        cur = self.cells.get(key)
        if cur is None or q > cur['quality']:
            self.cells[key] = {'prop': prop, 'quality': q}
            return True
        return False

    def all(self):
        return list(self.cells.values())

    def best(self, n=POOL_CAP, floor=0.75):
        """Пул для показа: не топ по качеству, а **непохожие** предметы."""
        rows = sorted(self.all(), key=lambda e: -e['quality'])
        if not rows:
            return []
        top = max(rows[0]['quality'], 1e-6)
        pool = [e for e in rows if e['quality'] >= top * floor] or rows[:n]

        chosen = [pool[0]['prop']]
        rest = [e['prop'] for e in pool[1:]]
        while rest and len(chosen) < n:
            far = max(rest, key=lambda c: min(props.distance(c, k)
                                              for k in chosen))
            chosen.append(far)
            rest.remove(far)
        return chosen

    def stats(self):
        rows = self.all()
        if not rows:
            return {'cells': 0, 'mean': 0.0, 'best': 0.0}
        qs = [e['quality'] for e in rows]
        return {'cells': len(rows), 'mean': round(st.mean(qs), 4),
                'best': round(max(qs), 4)}


def seed(archive, rng, n=200):
    for _ in range(n):
        p = props.propose(rng)
        if props.validate(p) is None:
            archive.add(p)
    return archive


def run(evals=4000, archive=None, rng=None, verbose=True, log_every=1000):
    rng = rng or random.Random()
    archive = archive or PropArchive()
    if not archive.cells:
        seed(archive, rng)

    t0 = time.time()
    rejected = 0
    history = []
    for i in range(1, evals + 1):
        pool = archive.all()
        parent = rng.choice(pool)['prop']
        if len(pool) > 1 and rng.random() < 0.25:
            child = props.crossover(parent, rng.choice(pool)['prop'], rng)
            child = props.mutate(child, rng)
        else:
            child = props.mutate(parent, rng, k=rng.randint(1, 2))

        if props.validate(child) is not None:
            rejected += 1
            continue
        archive.add(child)

        if i % log_every == 0:
            s = archive.stats()
            history.append({'eval': i, **s})
            if verbose:
                print(f'{i:6}  ниш {s["cells"]:3}  среднее {s["mean"]:.4f}  '
                      f'лучший {s["best"]:.4f}  '
                      f'{i / (time.time() - t0):.0f} оц/с')

    if verbose:
        print(f'\n{evals} оценок за {time.time() - t0:.0f} с, '
              f'отклонено воротами {rejected}')
    return archive, history


def diversity(items):
    """Средняя непохожесть силуэтов — разнообразие меряется, а не заявляется."""
    if len(items) < 2:
        return 0.0
    ds = [props.distance(items[i], items[j])
          for i in range(len(items)) for j in range(i + 1, len(items))]
    return round(st.mean(ds), 4)


def main():
    evals = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    rng = random.Random(5)

    print('=== 1. Случайное сочинение против отбора ===')
    base = []
    while len(base) < 200:
        p = props.propose(rng)
        if props.validate(p) is None:
            base.append(p)
    base_q = [props.quality(p) for p in base]
    print(f'случайные предметы: качество {st.mean(base_q):.4f}')

    arc, hist = run(evals, rng=rng)
    s = arc.stats()
    print(f'после отбора:       качество {s["mean"]:.4f} '
          f'(лучший {s["best"]:.4f}, ниш {s["cells"]})')

    print('\n=== 2. Разнообразие ===')
    top = arc.best(POOL_CAP)
    d_base = diversity(base[:POOL_CAP])
    d_top = diversity(top)
    print(f'непохожесть силуэтов у случайных: {d_base:.4f}')
    print(f'непохожесть силуэтов у отобранных: {d_top:.4f}')

    print('\n=== 3. Ворота держат ===')
    bad = [p for p in top if props.validate(p) is not None]
    print(f'в пуле {len(top)} предметов, невалидных: {len(bad)}')

    print('\n=== 4. Что получилось ===')
    for p in top[:8]:
        d = props.descriptor(p)
        shapes = '+'.join(q['shape'] for q in p['parts'])
        print(f'  качество {props.quality(p):.3f}  высота {d["height"]:.2f}  '
              f'ширина {d["width"]:.2f}  {shapes}')

    ok = True
    if s['mean'] <= st.mean(base_q):
        print('\nПРОБЛЕМА: отбор не улучшает качество')
        ok = False
    if bad:
        print('\nПРОБЛЕМА: в пуле есть предметы, не прошедшие ворота')
        ok = False
    if d_top < 0.3:
        print('\nПРОБЛЕМА: предметы схлопнулись в одну форму')
        ok = False

    if ok:
        for i, p in enumerate(top):
            props.register(f'inv_prop_{i:02d}', p)
        props.save()
        print(f'\nсохранено предметов: {len(top)}')

    print('\nИТОГ:', 'реквизит придуман и отобран' if ok else 'есть проблема')
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())

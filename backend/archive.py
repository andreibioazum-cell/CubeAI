"""Архив MAP-Elites — память Кейна."""

import json
import time
import os

# (имя, минимум, максимум, число корзин)
AXES = (
    ('openness', 0.28, 0.50, 6),
    ('loops',    0.00, 1.00, 6),
    ('size',     4,    60,   8),
)

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), 'archive.json')


def cell_of(desc):
    """Ниша, в которую попадает карта."""
    out = []
    for name, lo, hi, n in AXES:
        v = desc.get(name, lo)
        t = (v - lo) / (hi - lo) if hi > lo else 0.0
        out.append(int(min(n - 1, max(0, t * n))))
    return tuple(out)


TOTAL_CELLS = 1
for _, _, _, _n in AXES:
    TOTAL_CELLS *= _n


class Archive:
    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        self.cells = {}          # cell -> запись
        self.inserts = 0
        self.attempts = 0

    # ── работа с ячейками ────────────────────────────────────
    def add(self, genome, score, desc, terms=None):
        """Положить карту в её нишу, если она там лучшая."""
        self.attempts += 1
        cell = cell_of(desc)
        cur = self.cells.get(cell)
        if cur is not None and cur['score'] >= score:
            return False
        self.cells[cell] = {
            'genome': genome.to_dict(),
            'score': float(score),
            'desc': {k: desc.get(k) for k, _, _, _ in AXES},
            'terms': terms or {},
        }
        self.inserts += 1
        return True

    def elites(self):
        return list(self.cells.values())

    def best(self):
        return max(self.cells.values(), key=lambda e: e['score']) if self.cells else None

    def fill(self):
        return len(self.cells) / TOTAL_CELLS

    def mean_score(self):
        if not self.cells:
            return 0.0
        return sum(e['score'] for e in self.cells.values()) / len(self.cells)

    def stats(self):
        return {
            'cells': len(self.cells),
            'total_cells': TOTAL_CELLS,
            'fill': round(self.fill(), 4),
            'mean_score': round(self.mean_score(), 4),
            'best_score': round(self.best()['score'], 4) if self.cells else 0.0,
            'inserts': self.inserts,
            'attempts': self.attempts,
        }

    # ── диск ─────────────────────────────────────────────────
    def save(self, path=None):
        path = path or self.path
        data = {
            'axes': [list(a) for a in AXES],
            'inserts': self.inserts,
            'attempts': self.attempts,
            'cells': [{'cell': list(k), **v} for k, v in self.cells.items()],
        }
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        # Пишем через временный файл, чтобы прерванная запись не убила архив.
        for attempt in range(6):
            try:
                os.replace(tmp, path)
                return path
            except PermissionError:
                time.sleep(0.3 * (attempt + 1))
        raise PermissionError(f'не удалось записать {path}: файл занят')

    def load(self, path=None):
        path = path or self.path
        if not os.path.exists(path):
            return False
        # Изобретённые модули нужны раньше геномов: архив, ссылающийся на
        # модуль, которого нет в словаре, не декодируется.
        try:
            import modgen
            modgen.load()
        except Exception:
            pass
        with open(path, encoding='utf-8') as f:
            data = json.load(f)
        if [list(a) for a in AXES] != data.get('axes'):
            # оси поменялись — старые ячейки бессмысленны
            return False
        from modules import MODULES
        cells, dropped = {}, 0
        for c in data['cells']:
            # Модуль мог вымереть между запусками: карта, ссылающаяся на
            # несуществующий элемент, не декодируется — выкидываем её,
            # а не роняем весь архив.
            if any(t[1] not in MODULES for t in c['genome']['tiles']):
                dropped += 1
                continue
            cells[tuple(c['cell'])] = {k: c[k] for k in
                                       ('genome', 'score', 'desc', 'terms')}
        self.cells = cells
        self.dropped_on_load = dropped
        self.inserts = data.get('inserts', 0)
        self.attempts = data.get('attempts', 0)
        return True

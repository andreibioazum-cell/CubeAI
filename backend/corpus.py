"""Корпус карт для обучения сети-проектировщика."""

import json
import os

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), 'corpus.jsonl')

# Ниже этого счёта карта в корпус не идёт: учиться на посредственных
# примерах — верный способ получить посредственного проектировщика.
MIN_SCORE = 0.55


class Corpus:
    def __init__(self, path=DEFAULT_PATH, min_score=MIN_SCORE):
        self.path = path
        self.min_score = min_score
        self.n = 0
        self._f = None

    def open(self, append=True):
        self._f = open(self.path, 'a' if append else 'w', encoding='utf-8')
        return self

    def add(self, genome, score, desc):
        if score < self.min_score or self._f is None:
            return False
        self._f.write(json.dumps({
            'genome': genome.to_dict(),
            'score': round(float(score), 4),
            'desc': {k: float(v) for k, v in desc.items()},
        }, ensure_ascii=False) + '\n')
        self.n += 1
        return True

    def close(self):
        if self._f:
            self._f.close()
            self._f = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *a):
        self.close()


def read(path=DEFAULT_PATH, limit=None):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue        # оборванная строка от прерванного прогона
            if limit and len(out) >= limit:
                break
    return out


def stats(path=DEFAULT_PATH):
    rows = read(path)
    if not rows:
        return {'rows': 0}
    scores = [r['score'] for r in rows]
    sizes = [len(r['genome']['tiles']) for r in rows]
    return {
        'rows': len(rows),
        'score_min': round(min(scores), 3),
        'score_mean': round(sum(scores) / len(scores), 3),
        'score_max': round(max(scores), 3),
        'tiles_min': min(sizes),
        'tiles_mean': round(sum(sizes) / len(sizes)),
        'tiles_max': max(sizes),
    }

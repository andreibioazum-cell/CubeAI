"""Соперничество Кейна и Авеля."""

import statistics as st
import threading

from critic import evaluate, goal_cell
from genome import Genome
import walkers

# Насколько раунд должен быть убедительным, чтобы засчитать победу.
MARGIN = 0.004

# Матч из пяти раундов. Меньше — победа выглядит случайной, больше —
# зритель успевает заскучать до итога.
MATCH_ROUNDS = 5


def judge(level_a, level_b, rng=None):
    """Рассудить два уровня одними и теми же гуляками."""
    out = []
    for lv in (level_a, level_b):
        if lv is None:
            out.append(None)
            continue
        dist = lv.distances()
        goal = goal_cell(lv)
        reach, mtime, cov = walkers.simulate(lv, dist, goal)
        r = evaluate(lv, rng=rng)
        out.append({
            'score': round(r['score'], 4),
            'reach': round(reach, 3),
            'coverage': round(cov, 3),
            'rejected': r['rejected'],
        })
    return out


def outcome(a, b):
    """Кто взял раунд. Ничья — законный исход, а не отговорка."""
    if a is None or b is None:
        return 'нет карты'
    if a['rejected'] or b['rejected']:
        return 'нет карты'
    if abs(a['score'] - b['score']) < MARGIN:
        return 'ничья'
    return 'a' if a['score'] > b['score'] else 'b'


def steal(loser_archive, winner_archive, rng, n=1):
    """Проигравший забирает лучшие планировки победителя."""
    if winner_archive is None or loser_archive is None:
        return {'tried': 0, 'kept': [], 'why': 'нет архива'}
    # Берём случайную из верхушки, а не всегда первую: иначе каждый раунд
    # переносится одна и та же карта, и со второго раза она уже стоит
    # у проигравшего в своей нише.
    top = sorted(winner_archive.elites(), key=lambda e: -e['score'])
    top = top[:max(n, len(top) // 8)]
    best = rng.sample(top, min(n, len(top))) if top else []
    kept, tried = [], 0
    for entry in best:
        gm = Genome.from_dict(entry['genome'])
        lv = gm.decode()
        if lv is None:
            continue
        r = evaluate(lv, rng=rng)
        if r['rejected']:
            continue
        tried += 1
        from evolve import describe_level
        if loser_archive.add(gm, r['score'], describe_level(lv, r), r['terms']):
            kept.append(round(r['score'], 4))
    # Разница между «не взял» и «взял, но не прижилось» существенная:
    why = None if kept else ('в своей нише не лучше' if tried else 'нечего брать')
    return {'tried': tried, 'kept': kept, 'why': why}


class Duel:
    """Счёт противостояния и история раундов."""

    def __init__(self):
        self.round = 0
        self.history = []
        self.last = None
        # Метка уже засчитанного раунда и замок вокруг подсчёта.
        self.resolved_for = None
        self._lock = threading.Lock()

    def resolve_once(self, world_a, world_b, key, rng=None):
        """Засчитать раунд ровно один раз на данную пару карт."""
        with self._lock:
            if self.resolved_for == key:
                return self.last
            self.resolved_for = key
            return self.resolve(world_a, world_b, rng)

    def resolve(self, world_a, world_b, rng=None):
        res_a, res_b = judge(world_a.level, world_b.level, rng)
        who = outcome(res_a, res_b)
        self.round += 1

        taken = []
        if who in ('a', 'b'):
            win = world_a if who == 'a' else world_b
            lose = world_b if who == 'a' else world_a
            win.wins += 1
            taken = steal(lose.archive, win.archive, rng or __import__('random'))

        self.last = {
            'round': self.round,
            'winner': (world_a.key if who == 'a' else
                       world_b.key if who == 'b' else who),
            'a': res_a, 'b': res_b,
            'stolen': taken,
        }
        self.history.append(self.last)
        del self.history[:-24]
        return self.last

    def reset(self, world_a, world_b):
        """Новый матч: счёт с нуля, история чистая."""
        with self._lock:
            self.round = 0
            self.history = []
            self.last = None
            self.resolved_for = None
            world_a.wins = 0
            world_b.wins = 0

    def champion(self, world_a, world_b):
        """Кто взял матч. None — матч ещё идёт."""
        if self.round < MATCH_ROUNDS:
            return None
        if world_a.wins == world_b.wins:
            return 'ничья'
        return world_a.key if world_a.wins > world_b.wins else world_b.key

    def snapshot(self, world_a, world_b):
        return {
            'round': self.round,
            'match_rounds': MATCH_ROUNDS,
            'over': self.round >= MATCH_ROUNDS,
            'champion': self.champion(world_a, world_b),
            'wins': {world_a.key: world_a.wins, world_b.key: world_b.wins},
            'last': self.last,
            'mean': {
                k: round(st.mean(v), 4) if v else None
                for k, v in (
                    ('a', [h['a']['score'] for h in self.history if h['a']]),
                    ('b', [h['b']['score'] for h in self.history if h['b']]),
                )
            },
        }

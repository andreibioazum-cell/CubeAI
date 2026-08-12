"""Руки Кейна: детерминированная укладка блоков по чертежу."""

from collections import deque

# На сколько клеток Кейн дотягивается. При 2 внутренние углы стен остаются
# недостроенными (покрытие падает до 92%), при 3 достраивается всё.
REACH = 3


class Builder:
    def __init__(self, level, reach=REACH):
        self.level = level
        self.reach = reach
        self.start = level.entry_cell()            # (z, x)
        self.walkable = set(level.distances())     # достижимые проходимые клетки
        self.columns = self._columns()
        self.serves = self._serves()
        self.steps = []
        self.unreachable = []

    # ── подготовка ───────────────────────────────────────────
    def _columns(self):
        """Блоки чертежа, сгруппированные в колонны по (x, z)."""
        cols = {}
        for b in self.level.blueprint:
            cols.setdefault((b['z'], b['x']), []).append(b)
        for key in cols:
            cols[key].sort(key=lambda b: b['y'])
        return cols

    def _serves(self):
        """Откуда Кейн будет ставить каждую колонну."""
        gate_dist = self.level.distances()
        best = {}                       # колонна -> (близость, дальность от входа, клетка)
        r = self.reach
        for cell in self.walkable:
            cz, cx = cell
            for dz in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    key = (cz + dz, cx + dx)
                    if key not in self.columns:
                        continue
                    rank = (max(abs(dz), abs(dx)), gate_dist.get(cell, 10 ** 6))
                    if key not in best or rank < best[key][0]:
                        best[key] = (rank, cell)

        serves = {}
        for key, (_, cell) in best.items():
            serves.setdefault(cell, []).append(key)
        return serves

    # ── поиск пути ───────────────────────────────────────────
    def _bfs(self, origin, targets):
        """Ближайшая из целевых клеток и путь до неё."""
        if origin in targets:
            return origin, []
        prev = {origin: None}
        q = deque([origin])
        while q:
            cur = q.popleft()
            cz, cx = cur
            for dz, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                nxt = (cz + dz, cx + dx)
                if nxt in prev or nxt not in self.walkable:
                    continue
                prev[nxt] = cur
                if nxt in targets:
                    path = []
                    node = nxt
                    while node != origin:
                        path.append(node)
                        node = prev[node]
                    path.reverse()
                    return nxt, path
                q.append(nxt)
        return None, None

    # ── построение маршрута ──────────────────────────────────
    def plan(self):
        """Полный список шагов: перемещения и укладки."""
        self.steps = []
        pending = set(self.columns)
        pos = self.start
        self._emit_move(pos)

        while pending:
            # клетки, из которых есть что строить прямо сейчас
            targets = {cell for cell, cols in self.serves.items()
                       if any(k in pending for k in cols)}
            if not targets:
                break
            cell, path = self._bfs(pos, targets)
            if cell is None:
                break
            for node in path:
                self._emit_move(node)
            pos = cell

            # стоя здесь, кладём всё, до чего дотягиваемся: сначала ближнее,
            # внутри колонны — снизу вверх
            here = [k for k in self.serves[cell] if k in pending]
            here.sort(key=lambda k: (abs(k[0] - cell[0]) + abs(k[1] - cell[1]), k))
            for key in here:
                for block in self.columns[key]:
                    self._emit_place(pos, block)
                pending.discard(key)

        self.unreachable = sorted(pending)
        self._plan_decor(pos)
        return self.steps

    def _plan_decor(self, pos):
        """Декор расставляется последним: сначала стены, потом обстановка."""
        r = self.reach
        for d in self.level.decorations:
            goal = (int(d['z']), int(d['x']))
            cands = {c for c in self.walkable
                     if max(abs(c[0] - goal[0]), abs(c[1] - goal[1])) <= r}
            if not cands:
                continue
            cell, path = self._bfs(pos, cands)
            if cell is None:
                continue
            for node in path:
                self._emit_move(node)
            pos = cell
            self.steps.append({'kind': 'decor',
                               'x': float(cell[1]), 'y': 0.0, 'z': float(cell[0]),
                               'decor': dict(d)})
        return pos

    def _emit_move(self, cell):
        cz, cx = cell
        self.steps.append({'kind': 'move', 'x': float(cx), 'y': 0.0, 'z': float(cz)})

    def _emit_place(self, cell, block):
        cz, cx = cell
        self.steps.append({
            'kind': 'place',
            'x': float(cx), 'y': 0.0, 'z': float(cz),
            'block': {'x': float(block['x']), 'y': float(block['y']),
                      'z': float(block['z']), 'color': block['color']},
        })

    # ── отчёт ────────────────────────────────────────────────
    def report(self):
        placed = sum(1 for s in self.steps if s['kind'] == 'place')
        moves = sum(1 for s in self.steps if s['kind'] == 'move')
        total = len(self.level.blueprint)
        missed = sum(len(self.columns[k]) for k in self.unreachable)
        return {
            'blocks_total': total,
            'blocks_placed': placed,
            'blocks_missed': missed,
            'coverage': round(placed / total, 4) if total else 1.0,
            'moves': moves,
            'steps': len(self.steps),
            'columns': len(self.columns),
            'unreachable_columns': len(self.unreachable),
        }


def build_steps(level, reach=REACH):
    b = Builder(level, reach)
    b.plan()
    return b

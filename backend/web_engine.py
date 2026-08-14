"""Тот же движок, но без сервера — для запуска прямо во вкладке.

Pyodide держит здесь весь Python: карты, критик, гуляки, дуэль. Браузер
дёргает одну функцию `call`, и она отвечает ровно теми же телами, что и
маршруты FastAPI в main.py, — фронтенду разницы не видно.

Обмен идёт строками JSON, а не объектами. Так между JS и Python не
возникает прокси, которые надо конвертировать вручную, и одинаковый ответ
получается и на сервере, и в браузере.
"""
import json

from levelgen import STYLES, MAP_W
from modules import TILE
from world import make_builders, OFFSET, STYLE_CHOICE, TEMPO_MS, DUEL

engines = {}
duel = None
_booted = False


def boot(base_dir='/work'):
    global engines, duel, _booted
    if _booted:
        return {'ok': True, 'builders': list(engines)}
    engines, duel = make_builders(base_dir)
    _booted = True
    return {'ok': True, 'builders': list(engines)}


def _who(key):
    return engines.get(key or 'caine') or engines.get('caine')


def _step(who):
    eng = _who(who)
    frame = eng.step()
    frame['who'] = eng.key
    frame['platform'] = eng.platform
    frame['live'] = eng.live.snapshot() if eng.live else None
    return frame


def _level(who):
    eng = _who(who)
    info = eng.level_info()
    info['who'] = eng.key
    info['builder'] = eng.name
    info['platform'] = eng.platform
    return info


def _builders():
    return {'builders': [
        {'key': k, 'name': w.name, 'platform': w.platform, 'wins': w.wins}
        for k, w in engines.items()
    ], 'duel': DUEL}


def _duel_state():
    if duel is None or len(engines) < 2:
        return {'ok': False, 'reason': 'дуэль выключена'}
    a, b = engines['caine'], engines['abel']
    ready = a.finished and b.finished
    if ready and duel.champion(a, b) is None:
        duel.resolve_once(a, b, (a.map_index, b.map_index), a.rng)
    return {'ok': True, 'ready': ready, **duel.snapshot(a, b)}


def _duel_reset():
    if duel is None or len(engines) < 2:
        return {'ok': False, 'reason': 'дуэль выключена'}
    a, b = engines['caine'], engines['abel']
    duel.reset(a, b)
    a.new_map()
    b.new_map()
    return {'ok': True, **duel.snapshot(a, b)}


def _next(who):
    frame = _who(who).start_new()
    return {'ok': True, 'frame': frame, 'level': frame['level']}


def _stats(who):
    eng = _who(who)
    data = eng.stats()
    data['tempo_ms'] = TEMPO_MS
    data['who'] = eng.key
    data['builder'] = eng.name
    data['wins'] = eng.wins
    return data


def _walk(who, every=3):
    eng = _who(who)
    lv = getattr(eng, 'level', None)
    if lv is None:
        return {'ok': False, 'reason': 'карта ещё не готова'}
    from critic import goal_cell
    import walkers as _w

    reach, mtime, cov, path = _w.simulate(lv, lv.distances(), goal_cell(lv),
                                          trace=True)
    if not path:
        return {'ok': False, 'reason': 'мозг не обучен'}
    goal = goal_cell(lv)
    every = max(1, int(every))
    frames = [[[int(c) + OFFSET for c in (p[i][1], p[i][0])]
               for i in range(len(p))]
              for p in [path[t] for t in range(0, len(path), every)]]
    return {
        'ok': True, 'frames': frames, 'walkers': len(path[0]),
        'reach': round(reach, 3), 'coverage': round(cov, 3),
        'goal': [int(goal[1]) + OFFSET, int(goal[0]) + OFFSET] if goal else None,
    }


def _props():
    import props as _p
    return {'props': [{'name': n, 'parts': _p.INVENTED[n]['parts']}
                      for n in _p.names()]}


def _config():
    return {
        'tempo_ms': TEMPO_MS, 'style_choice': STYLE_CHOICE,
        'styles': {k: v['name'] for k, v in STYLES.items()},
        'size_cells': MAP_W * TILE, 'offset': OFFSET,
    }


ROUTES = {
    '/boot':       lambda p: boot(p.get('dir', '/work')),
    '/step':       lambda p: _step(p.get('who')),
    '/level':      lambda p: _level(p.get('who')),
    '/builders':   lambda p: _builders(),
    '/duel':       lambda p: _duel_state(),
    '/duel/reset': lambda p: _duel_reset(),
    '/next':       lambda p: _next(p.get('who')),
    '/reset':      lambda p: (_who(p.get('who')).new_map(), {'ok': True})[1],
    '/stats':      lambda p: _stats(p.get('who')),
    '/walk':       lambda p: _walk(p.get('who'), p.get('every', 3)),
    '/props':      lambda p: _props(),
    '/config':     lambda p: _config(),
}


def call(route, params_json='{}'):
    """Единственная дверь из браузера. Принимает и отдаёт строки JSON."""
    handler = ROUTES.get(route)
    if handler is None:
        return json.dumps({'ok': False, 'reason': f'нет маршрута {route}'})
    try:
        params = json.loads(params_json) if params_json else {}
        return json.dumps(handler(params), ensure_ascii=False)
    except Exception as exc:
        import traceback
        traceback.print_exc()
        return json.dumps({'ok': False, 'error': f'{type(exc).__name__}: {exc}'},
                          ensure_ascii=False)

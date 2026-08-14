import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from levelgen import STYLES, MAP_W
from modules import TILE
from world import (make_builders, OFFSET, STYLE_CHOICE, TEMPO_MS, DUEL)

# Консоль Windows по умолчанию не в UTF-8: без этого любой print
# с кириллицей роняет обработчик UnicodeEncodeError'ом.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

engine = None
engines = {}
duel = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine, engines, duel
    engines, duel = make_builders(os.path.dirname(__file__))
    engine = engines['caine']
    if duel is not None:
        print(f"Режим ДУЭЛИ: {' против '.join(w.name for w in engines.values())}")
    else:
        print(f"Режим ПОСТРОЙКИ: темп {TEMPO_MS} мс, стиль '{STYLE_CHOICE}'")
    yield
    for w in engines.values() or [engine]:
        live = getattr(w, 'live', None)
        if live:
            live.stop()
            print(f'[{getattr(w, "name", "Кейн")}] живое изобретение остановлено')


app = FastAPI(lifespan=lifespan)

# Собранный фронтенд раздаёт тот же процесс: на хостинге адрес один.
_DIST = os.path.join(os.path.dirname(__file__), '..', 'frontend', 'dist')

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _who(key):
    """Кого спрашивают. Неизвестное имя — это Кейн, а не ошибка 500."""
    return engines.get(key or 'caine') or engine


@app.get("/step")
def step(who: str = 'caine'):
    eng = _who(who)
    frame = eng.step()
    frame['who'] = getattr(eng, 'key', 'caine')
    frame['platform'] = getattr(eng, 'platform', 0)
    live = getattr(eng, 'live', None)
    # Живая сводка кладётся здесь, а не в каждый сборщик кадра: кадров
    # три вида (шаг, ожидание, смена мира), и забыть один из них легко.
    frame['live'] = live.snapshot() if live else None
    return frame


@app.get("/level")
def level(who: str = 'caine'):
    eng = _who(who)
    info = eng.level_info()
    info['who'] = getattr(eng, 'key', 'caine')
    info['builder'] = getattr(eng, 'name', 'Кейн')
    info['platform'] = getattr(eng, 'platform', 0)
    return info


@app.get("/builders")
def builders():
    """Кто участвует и на какой платформе стоит."""
    return {'builders': [
        {'key': k, 'name': w.name, 'platform': w.platform, 'wins': w.wins}
        for k, w in engines.items()
    ], 'duel': DUEL}


@app.get("/duel")
def duel_state():
    """Счёт противостояния. Раунд считается, когда оба достроили."""
    if duel is None or len(engines) < 2:
        return {'ok': False, 'reason': 'дуэль выключена'}
    a, b = engines['caine'], engines['abel']
    ready = a.finished and b.finished
    # Раунды сверх матча не считаются: иначе экран победы сменялся бы
    # шестым раундом, которого никто не просил.
    if ready and duel.champion(a, b) is None:
        duel.resolve_once(a, b, (a.map_index, b.map_index), a.rng)
    return {'ok': True, 'ready': ready, **duel.snapshot(a, b)}


@app.get("/duel/reset")
def duel_reset():
    """Новый матч: счёт с нуля и свежие карты обоим."""
    if duel is None or len(engines) < 2:
        return {'ok': False, 'reason': 'дуэль выключена'}
    a, b = engines['caine'], engines['abel']
    duel.reset(a, b)
    a.new_map()
    b.new_map()
    return {'ok': True, **duel.snapshot(a, b)}


@app.get("/next")
def next_map(who: str = 'caine'):
    """Бросить текущую карту и спроектировать новую."""
    frame = _who(who).start_new()
    return {'ok': True, 'frame': frame, 'level': frame['level']}


@app.get("/reset")
def reset(who: str = 'caine'):
    _who(who).new_map()
    return {'ok': True}


@app.get("/stats")
def stats(who: str = 'caine'):
    eng = _who(who)
    data = eng.stats()
    data['tempo_ms'] = TEMPO_MS
    data['who'] = getattr(eng, 'key', 'caine')
    data['builder'] = getattr(eng, 'name', 'Кейн')
    data['wins'] = getattr(eng, 'wins', 0)
    return data


@app.get("/walk")
def walk(who: str = 'caine', every: int = 3):
    """Прогулка гуляк по достроенной карте."""
    eng = _who(who)
    lv = getattr(eng, 'level', None)
    if lv is None:
        return {'ok': False, 'reason': 'карта ещё не готова'}
    from critic import goal_cell
    import walkers as _w

    dist = lv.distances()
    goal = goal_cell(lv)
    reach, mtime, cov, path = _w.simulate(lv, dist, goal, trace=True)
    if not path:
        return {'ok': False, 'reason': 'мозг не обучен'}

    # Прореживаем: 420 кадров на ходока фронтенду не нужны, он и так
    # сглаживает движение между точками.
    frames = [[[int(c) + OFFSET for c in (p[i][1], p[i][0])]
               for i in range(len(p))]
              for p in [path[t] for t in range(0, len(path), max(1, every))]]
    return {
        'ok': True,
        'frames': frames,
        'walkers': len(path[0]),
        'reach': round(reach, 3),
        'coverage': round(cov, 3),
        'goal': [int(goal[1]) + OFFSET, int(goal[0]) + OFFSET] if goal else None,
    }


@app.get("/props")
def invented_props():
    """Каталог придуманного реквизита — для показа и для проверки глазами."""
    import props as _p
    return {'props': [{'name': n, 'parts': _p.INVENTED[n]['parts']}
                      for n in _p.names()]}


@app.get("/config")
def config():
    return {
        'tempo_ms': TEMPO_MS,
        'style_choice': STYLE_CHOICE,
        'styles': {k: v['name'] for k, v in STYLES.items()},
        'size_cells': MAP_W * TILE,
        'offset': OFFSET,
    }


def _mount_frontend():
    """Подключить статику, если фронтенд собран."""
    if not os.path.isdir(_DIST):
        return False
    from fastapi.staticfiles import StaticFiles
    app.mount('/assets', StaticFiles(directory=os.path.join(_DIST, 'assets')),
              name='assets')
    for extra in ('tex', 'fonts', 'py'):
        d = os.path.join(_DIST, extra)
        if os.path.isdir(d):
            app.mount(f'/{extra}', StaticFiles(directory=d), name=extra)
    return True


# Подключается последним: маршруты API уже объявлены, поэтому перехвата
# не будет, а всё остальное уедет на index.html.
if _mount_frontend():
    from fastapi.responses import FileResponse

    @app.get("/{path:path}")
    def spa(path: str):
        target = os.path.join(_DIST, path)
        if path and os.path.isfile(target):
            return FileResponse(target)
        return FileResponse(os.path.join(_DIST, 'index.html'))

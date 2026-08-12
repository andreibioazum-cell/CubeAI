import os
import random
import sys
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from levelgen import (STYLES, blend_styles, generate_novel, style_mix,
                      MAP_W, MAP_H)
from modules import MODULES, TILE
from hands import build_steps
from archive import Archive
from genome import Genome
import styles_found

# Консоль Windows по умолчанию не в UTF-8: без этого любой print
# с кириллицей роняет обработчик UnicodeEncodeError'ом.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

# ── Режимы ───────────────────────────────────────────────────
# build  — новый движок: Кейн проектирует карту и строит её (по умолчанию)
MODE      = os.getenv("CAINE_MODE", "build").lower()
IS_LEGACY = MODE == "legacy"

# Стиль: конкретный ключ из STYLES, 'hybrid' или 'random'
STYLE_CHOICE = os.getenv("CAINE_STYLE", "random").lower()
TEMPO_MS     = int(os.getenv("CAINE_TEMPO", "150"))

# Блоков за один кадр. 'auto' подбирает так, чтобы карта строилась примерно
# за TARGET_FRAMES кадров: цирк на 6000 блоков иначе занимал бы 20 минут.
BATCH_CHOICE  = os.getenv("CAINE_BATCH", "auto").lower()
TARGET_FRAMES = int(os.getenv("CAINE_FRAMES", "1600"))

# Ждать ли нажатия «построить новую» после достройки
AUTO_ADVANCE = os.getenv("CAINE_AUTO", "0") == "1"

# Откуда брать карты:
SOURCE = os.getenv("CAINE_SOURCE", "auto").lower()

# Сколько вариантов сеть предлагает, прежде чем выбрать лучший по критику.
DESIGNER_TRIES = int(os.getenv("CAINE_DESIGNER_TRIES", "4"))

# Ниже этого счёта проект показывать нельзя: сеть иногда сваливается
# в крошечную карту, и лучше взять готовую из архива, чем портить показ.
DESIGNER_FLOOR = float(os.getenv("CAINE_DESIGNER_FLOOR", "0.35"))

# Доля лучшей части архива, из которой выбираются карты для показа:
# брать самый верх скучно (одна и та же ниша), брать всё подряд — рано.
ELITE_TOP = float(os.getenv("CAINE_ELITE_TOP", "0.5"))

# Насколько сильно предпочитать зрелищные карты при показе.
SHOWINESS = float(os.getenv("CAINE_SHOWINESS", "1.0"))

# Живое изобретение: Кейн продолжает придумывать, пока строит.
LIVE = os.getenv("CAINE_EVOLVE", "0").lower() in ("1", "true", "yes", "on")
LIVE_DUTY = float(os.getenv("CAINE_EVOLVE_DUTY", "0.5"))

# Карта 78×78 клеток — центрируем её на поле, чтобы фронтенду не пришлось
# ничего пересчитывать.
OFFSET = -(MAP_W * TILE) // 2

HYBRID_PAIRS = [
    ('cave', 'mansion'), ('castle', 'candy'), ('circus', 'island'),
    ('cave', 'circus'), ('mansion', 'circus'), ('castle', 'cave'),
    ('candy', 'island'), ('mansion', 'candy'),
    # Город хорошо смешивается: «город × замок» даёт крепостные кварталы,
    # «город × сладости» — пряничный квартал.
    ('city', 'castle'), ('city', 'candy'), ('city', 'island'),
    ('city', 'cave'),
]


def _pick_style(rng, bias=None):
    """Что строим следующим: чистый стиль, смешанный гибрид или сшитый."""
    if STYLE_CHOICE in STYLES:
        return STYLES[STYLE_CHOICE], None, 'pure'
    pool = [STYLES[k] for k in bias if k in STYLES] if bias else list(STYLES.values())
    if not pool:
        pool = list(STYLES.values())
    r = rng.random()
    if STYLE_CHOICE != 'hybrid' and r < 0.6:
        return rng.choice(pool), None, 'pure'

    a, b = rng.choice(HYBRID_PAIRS)
    t = rng.choice([0.35, 0.5, 0.65])
    base = blend_styles(a, b, t)
    if rng.random() < 0.5:
        return base, None, 'blend'
    # сшивка: низ карты одного стиля, верх другого
    axis = rng.choice(['z', 'x'])
    return base, (STYLES[a], STYLES[b], axis), 'zoned'


class World:
    """Строитель со своей картой, своим архивом и своей платформой."""

    def __init__(self, name='Кейн', key='caine', archive_path=None,
                 style_bias=None, platform=0):
        self.name = name
        self.key = key
        self.archive_path = archive_path
        self.style_bias = style_bias
        self.platform = platform
        self.wins = 0
        self.rng = random.Random()
        self.map_index = 0
        self.total_blocks = 0
        # Запросы FastAPI обрабатываются в пуле потоков, поэтому /step может
        # прийти посреди смены карты. Замок реентерабельный: шаг под замком
        # сам вызывает смену карты, когда предыдущая достроена.
        self._lock = threading.RLock()

        self.archive = None
        # Стили, которые Кейн нашёл сам: карта называется по характеру,
        # а не по родословной — «Особняк × Цирк» ничего не говорит зрителю
        # о том, чем постройка стала после десятков мутаций.
        self.designer = None
        if SOURCE == 'designer':
            import designer as _d
            self.designer_mod = _d
            model, vocab = _d.load()
            if model is None:
                print("[Кейн] сеть не обучена — работаю по грамматике")
            else:
                self.designer = (model, vocab)
                print("[Кейн] проектирую сетью, без перебора")

        self.live = None
        import props as _props
        n_props = len(_props.load())
        if n_props:
            print(f"[Кейн] изобретённого реквизита: {n_props}")
        self.found_styles = styles_found.load()
        if self.found_styles:
            print(f"[Кейн] найденных стилей: {len(self.found_styles['styles'])}")
        # Архив нужен не только как источник карт: в живом режиме фоновому
        # изобретателю есть что мутировать только при готовом архиве.
        self.archive_for_maps = SOURCE in ('auto', 'archive', 'designer')
        if self.archive_for_maps or LIVE:
            arc = Archive(self.archive_path) if self.archive_path else Archive()
            if arc.load() and arc.cells:
                self.archive = arc
                print(f"[{self.name}] архив: {arc.stats()}")
            elif SOURCE == 'archive':
                print(f"[{self.name}] архив не найден — работаю по грамматике")
        self.new_map()

        if LIVE and self.archive is not None:
            from live import LiveWorker
            self.live = LiveWorker(self.archive, self._lock,
                                   duty=LIVE_DUTY).start()
            print(f"[Кейн] живое изобретение включено "
                  f"(доля процессора {LIVE_DUTY:.0%})")

    @staticmethod
    def _decode(gdict):
        """Разложить геном в карту под замком словаря модулей: фоновый"""
        if LIVE:
            from live import REGISTRY
            with REGISTRY:
                return Genome.from_dict(gdict).decode()
        return Genome.from_dict(gdict).decode()

    @staticmethod
    def _showiness(entry):
        """Насколько карта хороша именно в кадре."""
        from genome import palette_saturation
        st = entry['genome']['style']
        size = min(1.0, entry['desc'].get('size', 10) / 45.0)
        vert = float(st.get('verticality', 0.5))
        sat = min(1.0, palette_saturation(st['palette']) / 0.35)
        names = [t[1] for t in entry['genome']['tiles']]
        rich = sum(1 for n in names
                   if MODULES.get(n, {}).get('role') not in ('corridor', 'gate'))
        rich = rich / max(len(names), 1)
        return 0.35 * size + 0.25 * vert + 0.2 * sat + 0.2 * rich

    def _pick_elite(self):
        """Взять карту, которую Кейн нашёл сам."""
        elites = sorted(self.archive.elites(), key=lambda e: -e['score'])
        top = elites[:max(1, int(len(elites) * ELITE_TOP))]
        if SHOWINESS > 0:
            w = [max(0.01, self._showiness(e)) ** (2 * SHOWINESS) for e in top]
            # Предпочтения строителя работают и при выборе из архива, иначе
            # Кейн с Авелем тянули бы из одного мешка и строили похожее даже
            # с разными вкусами.
            if self.style_bias:
                want = {STYLES[k]['name'] for k in self.style_bias if k in STYLES}
                for i, e in enumerate(top):
                    родословная = e['genome']['style'].get('name', '')
                    if any(nm in родословная for nm in want):
                        w[i] *= 3.0
            entry = self.rng.choices(top, weights=w)[0]
        else:
            entry = self.rng.choice(top)
        level = self._decode(entry['genome'])
        if level is None:
            return None, None, None, None
        found = styles_found.assign(self.found_styles, level, entry)
        return (level, entry['score'], entry['desc'],
                found['name'] if found else None)

    def _design_one(self):
        """Спроектировать карту сетью и взять лучшую из нескольких попыток."""
        from critic import evaluate
        model, vocab = self.designer
        target = {
            'openness': self.rng.uniform(0.32, 0.48),
            'loops': self.rng.uniform(0.0, 0.9),
            'size': self.rng.randint(12, 50),
        }
        best, best_r = None, None
        for _ in range(DESIGNER_TRIES):
            gm = self.designer_mod.design(model, vocab, target, rng=self.rng)
            lv = self._decode(gm.to_dict())
            if lv is None:
                continue
            r = evaluate(lv, rng=self.rng)
            if r['rejected']:
                continue
            if best_r is None or r['score'] > best_r['score']:
                best, best_r = lv, r
        if best is None or best_r['score'] < DESIGNER_FLOOR:
            return None, None, None, None
        desc = {'openness': best.descriptor['openness'],
                'loops': best_r['terms'].get('loops', 0.0),
                'size': best.descriptor['size']}
        found = styles_found.assign(self.found_styles, best,
                                    {'terms': best_r['terms']})
        return (best, best_r['score'], desc,
                found['name'] if found else None)

    def new_map(self):
        """Спроектировать следующую карту."""
        level = style = None
        source = hybrid = None
        score = desc = found_name = None

        if self.designer is not None:
            level, score, desc, found_name = self._design_one()
            source, hybrid = 'designer', 'designed'

        if level is None and self.archive is not None and self.archive_for_maps:
            level, score, desc, found_name = self._pick_elite()
            source, hybrid = 'archive', 'evolved'

        if level is None:
            st, zoned, kind = _pick_style(self.rng, self.style_bias)
            style = st
            source, hybrid = 'grammar', kind
            level = generate_novel(st, zoned=zoned)
            score = desc = found_name = None

        builder = build_steps(level)
        report = builder.report()

        with self._lock:
            self.level = level
            self.style = style or level.style
            self.source = source
            self.hybrid_kind = hybrid
            self.elite_score = score
            self.elite_desc = desc
            self.found_name = found_name
            self.builder = builder
            self.report = report
            self.cursor = 0
            self.placed = 0
            self.finished = False
            self.map_index += 1

        if BATCH_CHOICE == 'auto':
            self.batch = max(1, round(self.report['steps'] / TARGET_FRAMES))
        else:
            self.batch = max(1, int(BATCH_CHOICE))

        origin = (('сеть' if self.source == 'designer' else 'эволюция')
                  + ', счёт %.3f' % self.elite_score
                  if self.elite_score is not None else f'грамматика, {self.hybrid_kind}')
        print(f"[Кейн] карта #{self.map_index}: {self.style['name']} ({origin}), "
              f"настроение {self.level.mood}, "
              f"модулей {self.level.descriptor['size']}, "
              f"блоков {self.report['blocks_placed']}, "
              f"шагов {self.report['steps']}, пачка {self.batch}")

    def built_so_far(self):
        """Что уже построено. Нужно, чтобы перезагрузка страницы посреди"""
        blocks, decor = [], []
        for s in self.builder.steps[:self.cursor]:
            if s['kind'] == 'place':
                b = s['block']
                blocks.append({'x': b['x'] + OFFSET, 'y': b['y'],
                               'z': b['z'] + OFFSET, 'color': b['color'],
                               'role': b.get('role', 1)})
            elif s['kind'] == 'decor':
                decor.append(self._shift_decor(s['decor']))
        return blocks, decor

    def bounds(self):
        """Габариты постройки — фронтенд по ним наводит камеру, чтобы карта"""
        bp = self.level.blueprint
        if not bp:
            return {'minx': OFFSET, 'maxx': -OFFSET, 'minz': OFFSET, 'maxz': -OFFSET}
        xs = [b['x'] for b in bp]
        zs = [b['z'] for b in bp]
        return {'minx': min(xs) + OFFSET, 'maxx': max(xs) + OFFSET,
                'minz': min(zs) + OFFSET, 'maxz': max(zs) + OFFSET}

    def level_info(self):
        d = self.level.descriptor
        blocks, decor = self.built_so_far()
        return {
            'index': self.map_index,
            'style_name': self.style['name'],
            'hybrid': self.hybrid_kind,
            'palette': self.style['palette'],
            'mood': self.level.mood,
            'sky': self.level.sky,
            'source': self.source,
            'found_style': self.found_name,
            'score': round(self.elite_score, 3) if self.elite_score is not None else None,
            'niche': self.elite_desc,
            'bounds': self.bounds(),
            'awaiting': self.finished,
            'descriptor': d,
            'novelty': self.level.novelty,
            'blocks': self.report['blocks_placed'],
            'total_steps': self.report['steps'],
            'size_cells': MAP_W * TILE,
            'offset': OFFSET,
            # Состав текстур: фронтенд по нему смешивает фактуры стилей.
            'style_mix': style_mix(self.style) if self.style else {},
            'gate': {'x': self.level.entry_cell()[1] + OFFSET,
                     'z': self.level.entry_cell()[0] + OFFSET},
            # только уже расставленный декор: остальное Кейн поставит сам
            'decorations': decor,
            'decorations_total': len(self.level.decorations),
            'built': blocks,
            'progress': round(self.placed / (self.report['blocks_placed'] or 1), 3),
            'legacy': False,
        }

    def _shift_decor(self, d):
        return {**d, 'x': d['x'] + OFFSET, 'z': d['z'] + OFFSET}

    def _idle_frame(self):
        gz, gx = self.level.entry_cell()
        return {
            'kind': 'idle', 'x': float(gx + OFFSET), 'y': 0.0,
            'z': float(gz + OFFSET), 'blocks': [], 'decor': [],
            'progress': 1.0, 'map_done': True, 'awaiting': True,
            'world_reset': False, 'level': None,
        }

    def start_new(self):
        """Спроектировать новую карту и отдать кадр её начала."""
        self.new_map()
        gz, gx = self.level.entry_cell()
        return {
            'kind': 'move', 'x': float(gx + OFFSET), 'y': 0.0,
            'z': float(gz + OFFSET), 'blocks': [], 'decor': [],
            'progress': 0.0, 'map_done': False, 'awaiting': False,
            'world_reset': True, 'level': self.level_info(),
        }

    def step(self):
        with self._lock:
            return self._step_locked()

    def _step_locked(self):
        steps = self.builder.steps
        if self.cursor >= len(steps):
            # Карта достроена. По умолчанию Кейн ждёт команды, а не
            # затирает готовую постройку следующей.
            self.finished = True
            if not AUTO_ADVANCE:
                return self._idle_frame()
            return self.start_new()

        blocks, decor = [], []
        kind = 'move'
        x = y = z = 0.0
        for _ in range(self.batch):
            if self.cursor >= len(steps):
                break
            s = steps[self.cursor]
            self.cursor += 1
            x, y, z = s['x'] + OFFSET, s['y'], s['z'] + OFFSET
            if s['kind'] == 'place':
                b = s['block']
                self.placed += 1
                blocks.append({'x': b['x'] + OFFSET, 'y': b['y'],
                               'z': b['z'] + OFFSET, 'color': b['color'],
                               'role': b.get('role', 1)})
                kind = 'place'
            elif s['kind'] == 'decor':
                decor.append(self._shift_decor(s['decor']))
                if kind != 'place':
                    kind = 'decor'

        total = self.report['blocks_placed'] or 1
        return {
            'kind': kind, 'x': x, 'y': y, 'z': z,
            'blocks': blocks, 'decor': decor,
            'progress': round(self.placed / total, 3),
            'map_done': self.cursor >= len(steps),
            'awaiting': False, 'world_reset': False, 'level': None,
        }

    def stats(self):
        return {
            'mode': 'build',
            'map_index': self.map_index,
            'style_name': self.style['name'],
            'hybrid': self.hybrid_kind,
            'novelty': self.level.novelty,
            'descriptor': self.level.descriptor,
            'blocks': self.report['blocks_placed'],
            'placed': self.placed,
            'progress': round(self.placed / (self.report['blocks_placed'] or 1), 3),
            'step': self.cursor,
            'total_steps': self.report['steps'],
            'decorations': len(self.level.decorations),
            # Доля блоков доходит до единицы раньше, чем строитель
            # заканчивает: остаются проходы и расстановка декора. Признак
            # завершения нужен явный.
            'finished': self.finished,
            'live': self.live.snapshot() if self.live else None,
        }


# Два строителя. Кейн тяготеет к подземельям и зрелищам, Авель — к
# открытым и городским планировкам: без разных предпочтений они строили бы
# одно и то же, и соперничество было бы декоративным.
BUILDERS = {
    'caine': {'name': 'Кейн', 'archive': 'archive.json', 'platform': 0,
              'bias': ['cave', 'castle', 'mansion', 'circus']},
    'abel':  {'name': 'Авель', 'archive': 'archive_abel.json', 'platform': 1,
              'bias': ['city', 'island', 'candy', 'castle']},
}
DUEL = os.getenv("CAINE_DUEL", "1").lower() in ("1", "true", "yes", "on")

engine = None
engines = {}
duel = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global engine
    if IS_LEGACY:
        from legacy_engine import LegacyEngine
        engine = LegacyEngine(offset=OFFSET)
        print(f"Режим LEGACY: старый DQN, {engine.style_name}")
    else:
        global engines, duel
        import os.path as _op
        for key, cfg in BUILDERS.items():
            if key == 'abel' and not DUEL:
                continue
            path = _op.join(_op.dirname(__file__), cfg['archive'])
            engines[key] = World(name=cfg['name'], key=key,
                                 archive_path=path if _op.exists(path) else None,
                                 style_bias=cfg['bias'],
                                 platform=cfg['platform'])
        engine = engines['caine']
        if DUEL and 'abel' in engines:
            from duel import Duel
            duel = Duel()
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
    if IS_LEGACY:
        return {'ok': False, 'reason': 'в режиме legacy карты не проектируются'}
    frame = _who(who).start_new()
    return {'ok': True, 'frame': frame, 'level': frame['level']}


@app.get("/reset")
def reset(who: str = 'caine'):
    if not IS_LEGACY:
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
        'mode': MODE,
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
    for extra in ('tex', 'fonts'):
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

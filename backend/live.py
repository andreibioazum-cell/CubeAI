"""Живое изобретение: Кейн продолжает придумывать, пока строит."""

import random
import sys
import threading
import time

from archive import Archive
from critic import evaluate
from evolve import describe_level
from genome import Genome, mutate, crossover
from modules import unregister_module
import evolve_modules
import evolve_props
import modgen
import props as props_mod

# Общий замок на словарь модулей: его берут и изобретение, и раскладка карты.
REGISTRY = threading.RLock()

CROSSOVER_RATE = 0.25
INVENT_EVERY = 400          # оценок между попытками изобрести модуль
PROP_EVERY = 250            # оценок между попытками изобрести предмет
PROP_BATCH = 120            # сколько попыток отбора реквизита за раз
PRUNE_EVERY = 1200          # оценок между волнами вымирания: за 400 оценок
                            # появляется одно изобретение, и без частой
                            # прополки пул успевает раздуться вдвое сверх лимита
SAVE_EVERY = 1500           # оценок между сохранениями на диск
DUTY = 0.5                  # какую долю времени поток считает, а не спит


class LiveWorker:
    """Фоновый изобретатель. Делит архив с показом под общим замком."""

    def __init__(self, archive, lock, rng=None, duty=DUTY, invent=True):
        self.archive = archive
        self.lock = lock
        self.rng = rng or random.Random()
        self.duty = max(0.05, min(1.0, duty))
        self.invent_enabled = invent

        self.attempts = 0
        self.inserts = 0
        self.invented = 0
        self.invented_props = 0
        self.extinct = 0
        self.prop_archive = evolve_props.PropArchive()
        self.events = []            # что показать в кадре
        self._start_stats = None
        self._thread = None
        self._stop = threading.Event()
        self._snap = None
        self._snap_at = 0.0

    # ── жизненный цикл ────────────────────────────────────────

    def start(self):
        # Одна оценка карты — длинный кусок чистого питона. С интервалом
        # переключения по умолчанию (5 мс) она удерживает GIL и задерживает
        # отдачу кадра. Уступая чаще, теряем немного фоновой пропускной
        # способности и возвращаем показу отзывчивость.
        sys.setswitchinterval(0.0005)
        with self.lock:
            self._start_stats = self.archive.stats()
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name='caine-live')
        self._thread.start()
        return self

    def stop(self, timeout=3.0):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout)

    # ── что показать в кадре ──────────────────────────────────

    def snapshot(self, max_age=0.5):
        """Сводка для кадра. Кэшируется: статистика архива считается по всем"""
        now = time.time()
        if self._snap is not None and now - self._snap_at < max_age:
            snap = dict(self._snap)
            snap['events'] = self.events[-4:]
            return snap
        with self.lock:
            st = self.archive.stats()
        base = self._start_stats or st
        snap = {
            'running': bool(self._thread and self._thread.is_alive()),
            'attempts': self.attempts,
            'inserts': self.inserts,
            'invented': self.invented,
            'extinct': self.extinct,
            'cells': st['cells'],
            'cells_gained': st['cells'] - base['cells'],
            'mean_score': st['mean_score'],
            'mean_gained': round(st['mean_score'] - base['mean_score'], 4),
            'best_score': st['best_score'],
            'pool': len(modgen.invented_names()),
            'props': self.invented_props,
            'prop_pool': len(props_mod.names()),
            'events': self.events[-4:],
        }
        self._snap, self._snap_at = snap, now
        return snap

    def _event(self, kind, text):
        self.events.append({'kind': kind, 'text': text, 't': time.time()})
        del self.events[:-16]

    # ── работа ────────────────────────────────────────────────

    def _one_eval(self):
        # Под замком только выбор записей. Разбор генома — это сотни клеток,
        # и держать на нём замок значит тормозить отдачу кадров: 99-й
        # процентиль задержки подскакивал с 2 до 36 мс именно здесь.
        with self.lock:
            elites = self.archive.elites()
            if not elites:
                return
            a = self.rng.choice(elites)['genome']
            b = self.rng.choice(elites)['genome'] if len(elites) > 1 else None

        parent = Genome.from_dict(a)
        other = Genome.from_dict(b) if b is not None else None

        if other is not None and self.rng.random() < CROSSOVER_RATE:
            child = mutate(crossover(parent, other, self.rng), self.rng, k=1)
        else:
            child = mutate(parent, self.rng)

        with REGISTRY:
            level = child.decode()
        if level is None:
            return
        result = evaluate(level, rng=self.rng)
        if result['rejected']:
            return

        with self.lock:
            added = self.archive.add(child, result['score'],
                                     describe_level(level, result),
                                     result['terms'])
        if added:
            self.inserts += 1

    def _invent_one(self):
        with REGISTRY:
            name = modgen.invent(self.rng)
        if not name:
            return
        self.invented += 1
        self._event('invent', 'Кейн придумал новый элемент')

        # Сразу пробуем пристроить изобретение: без этого оно останется
        # в словаре мёртвым грузом и вымрет на ближайшей волне.
        with self.lock:
            elites = self.archive.elites()
        if not elites:
            return
        for _ in range(6):
            gm = Genome.from_dict(self.rng.choice(elites)['genome'])
            gm = mutate(gm, self.rng, k=2)
            with REGISTRY:
                lv = gm.decode()
            if lv is None:
                continue
            r = evaluate(lv, rng=self.rng)
            if r['rejected']:
                continue
            with self.lock:
                self.archive.add(gm, r['score'], describe_level(lv, r),
                                 r['terms'])

    def _invent_prop(self):
        """Придумать реквизит. Отбор идёт своим архивом ниш формы: у предмета"""
        arc = self.prop_archive
        if not arc.cells:
            evolve_props.seed(arc, self.rng, n=120)
        before = len(arc.cells)
        evolve_props.run(PROP_BATCH, archive=arc, rng=self.rng, verbose=False)
        if len(arc.cells) <= before:
            return
        pool = arc.best(evolve_props.POOL_CAP)
        with REGISTRY:
            props_mod.INVENTED.clear()
            for i, p in enumerate(pool):
                props_mod.register(f'inv_prop_{i:02d}', p)
        self.invented_props += 1
        self._event('prop', 'Кейн придумал новый предмет')

    def _prune(self):
        with self.lock, REGISTRY:
            count, value = evolve_modules.usage(self.archive)
            killed = evolve_modules.prune(self.archive, count, value,
                                          self.rng, verbose=False,
                                          keep_unused=True)
        if killed:
            self.extinct += len(killed)
            self._event('extinct',
                        f'вымерло элементов: {len(killed)}')

    def _save(self):
        with self.lock, REGISTRY:
            try:
                self.archive.save()
                modgen.save()
                props_mod.save()
            except OSError:
                pass        # файл держит другой процесс — попробуем позже

    def _loop(self):
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self._one_eval()
                self.attempts += 1
                if self.invent_enabled and self.attempts % INVENT_EVERY == 0:
                    self._invent_one()
                if self.invent_enabled and self.attempts % PROP_EVERY == 0:
                    self._invent_prop()
                if self.attempts % PRUNE_EVERY == 0:
                    self._prune()
                if self.attempts % SAVE_EVERY == 0:
                    self._save()
            except Exception as e:                  # noqa: BLE001
                # Фоновая работа не должна ронять показ ни при каких условиях.
                self._event('error', f'сбой изобретателя: {type(e).__name__}')
                time.sleep(0.5)
                continue

            # передышка пропорционально потраченному времени
            spent = time.time() - t0
            self._stop.wait(spent * (1.0 / self.duty - 1.0))
        self._save()


__all__ = ['LiveWorker', 'REGISTRY', 'unregister_module', 'Archive']

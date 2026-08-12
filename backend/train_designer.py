"""Обучить сеть-проектировщика на корпусе эволюции.

Запуск:  python train_designer.py [эпох] [квантиль_отбора]
"""
import sys

from corpus import read, stats
import designer
import modgen

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass

if __name__ == '__main__':
    epochs = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    quantile = float(sys.argv[2]) if len(sys.argv) > 2 else 0.75
    modgen.load()
    print('корпус:', stats())
    rows = read()
    if rows and quantile > 0:
        sc = sorted(r['score'] for r in rows)
        thr = sc[int(len(sc) * quantile)]
        rows = [r for r in rows if r['score'] >= thr]
        print(f'отбор: счёт >= {thr:.3f}, осталось {len(rows)} карт')
    if len(rows) < 200:
        print('корпус слишком мал — сначала python collect_corpus.py 20000')
        raise SystemExit(1)
    model, vocab, hist = designer.train(rows, epochs=epochs)
    p = designer.save(model, vocab)
    print(f'\nсохранено: {p}')
    print(f'последняя эпоха: обучение {hist[-1]["train"]:.4f}, '
          f'проверка {hist[-1]["val"]:.4f}')

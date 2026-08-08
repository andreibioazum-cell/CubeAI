import numpy as np
import json
import copy
import os

MAX_COLOR = 5
GRID_SIZE = 7

from enviroment import patterns as BASE_PATTERNS

GENERATED_FILE = "generated_patterns.json"


def evaluate_pattern(pattern):
    grid = np.array(pattern)
    non_zero = np.count_nonzero(grid)
    density = non_zero / (GRID_SIZE * GRID_SIZE)

    # Строгая плотность — как у базовых паттернов (15-60%)
    if density < 0.15 or density > 0.60:
        return 0.0

    # Симметрия — обязательно должна быть
    h_sym = np.sum(grid == np.fliplr(grid)) / (GRID_SIZE * GRID_SIZE)
    v_sym = np.sum(grid == np.flipud(grid)) / (GRID_SIZE * GRID_SIZE)
    sym_score = max(h_sym, v_sym)

    # Паттерн должен быть хотя бы немного симметричным
    if sym_score < 0.55:
        return 0.0

    # Разнообразие цветов — не больше 3 разных цветов (как в базовых)
    unique_colors = len(set(grid.flatten()) - {0})
    if unique_colors > 4:
        return 0.0
    color_score = min(unique_colors / 2.0, 1.0)

    # Связность блоков
    connectivity = 0
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if grid[r][c] != 0:
                for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                    nr, nc = r+dr, c+dc
                    if 0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE and grid[nr][nc] != 0:
                        connectivity += 1
    connectivity_score = min(connectivity / (non_zero * 2 + 1), 1.0)

    # Блоки не должны быть совсем разрозненными
    if connectivity_score < 0.2:
        return 0.0

    # Структурность — проверяем что есть хотя бы одна линия или форма
    row_sums = [np.count_nonzero(grid[r]) for r in range(GRID_SIZE)]
    col_sums = [np.count_nonzero(grid[:, c]) for c in range(GRID_SIZE)]
    has_line = max(row_sums) >= 4 or max(col_sums) >= 4
    structure_score = 1.0 if has_line else 0.5

    score = (
        sym_score * 0.35 +
        color_score * 0.20 +
        connectivity_score * 0.25 +
        structure_score * 0.20
    )
    return score


def mutate(pattern, mutation_rate=0.15):
    grid = copy.deepcopy(pattern)
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if np.random.random() < mutation_rate:
                grid[r][c] = 0 if np.random.random() < 0.4 else np.random.randint(1, MAX_COLOR + 1)
    return grid


def crossover(p1, p2):
    grid = []
    for r in range(GRID_SIZE):
        if np.random.random() < 0.5:
            grid.append(copy.deepcopy(p1[r]))
        else:
            grid.append(copy.deepcopy(p2[r]))
    return grid


def make_symmetric_h(pattern):
    """Горизонтальная симметрия."""
    grid = copy.deepcopy(pattern)
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE // 2):
            grid[r][GRID_SIZE - 1 - c] = grid[r][c]
    return grid


def make_symmetric_v(pattern):
    """Вертикальная симметрия."""
    grid = copy.deepcopy(pattern)
    for r in range(GRID_SIZE // 2):
        grid[GRID_SIZE - 1 - r] = copy.deepcopy(grid[r])
    return grid


def make_symmetric_both(pattern):
    """Двойная симметрия."""
    grid = make_symmetric_h(pattern)
    grid = make_symmetric_v(grid)
    return grid


def limit_colors(pattern, max_colors=3):
    """Ограничивает количество цветов в паттерне."""
    grid = np.array(copy.deepcopy(pattern))
    colors = list(set(grid.flatten()) - {0})
    if len(colors) <= max_colors:
        return grid.tolist()
    # Оставляем только самые частые цвета
    color_counts = [(c, np.sum(grid == c)) for c in colors]
    color_counts.sort(key=lambda x: x[1], reverse=True)
    keep = {c for c, _ in color_counts[:max_colors]}
    for r in range(GRID_SIZE):
        for c in range(GRID_SIZE):
            if grid[r][c] not in keep and grid[r][c] != 0:
                grid[r][c] = 0
    return grid.tolist()


def generate_patterns(n=10, min_score=0.55, max_attempts=500):
    pattern_list = list(BASE_PATTERNS.values())
    result = {}
    generated = 0
    attempts = 0

    while generated < n and attempts < max_attempts:
        attempts += 1
        method = np.random.choice(['mutate_sym_h', 'mutate_sym_v', 'mutate_sym_both',
                                   'crossover_sym', 'crossover_sym_both'])

        if method == 'mutate_sym_h':
            base = copy.deepcopy(pattern_list[np.random.randint(len(pattern_list))])
            candidate = mutate(base, 0.15)
            candidate = make_symmetric_h(candidate)

        elif method == 'mutate_sym_v':
            base = copy.deepcopy(pattern_list[np.random.randint(len(pattern_list))])
            candidate = mutate(base, 0.15)
            candidate = make_symmetric_v(candidate)

        elif method == 'mutate_sym_both':
            base = copy.deepcopy(pattern_list[np.random.randint(len(pattern_list))])
            candidate = mutate(base, 0.15)
            candidate = make_symmetric_both(candidate)

        elif method == 'crossover_sym':
            p1 = pattern_list[np.random.randint(len(pattern_list))]
            p2 = pattern_list[np.random.randint(len(pattern_list))]
            candidate = crossover(p1, p2)
            candidate = mutate(candidate, 0.05)
            candidate = make_symmetric_h(candidate)

        else:  # crossover_sym_both
            p1 = pattern_list[np.random.randint(len(pattern_list))]
            p2 = pattern_list[np.random.randint(len(pattern_list))]
            candidate = crossover(p1, p2)
            candidate = make_symmetric_both(candidate)

        # Ограничиваем цвета
        candidate = limit_colors(candidate, max_colors=3)
        score = evaluate_pattern(candidate)

        if score >= min_score:
            name = f"gen_{generated + 1}_{method[:6]}"
            result[name] = candidate
            generated += 1
            print(f"  [{generated}/{n}] {name} — score: {score:.3f} (попыток: {attempts})")

    if generated < n:
        print(f"  Предупреждение: сгенерировано только {generated}/{n} паттернов за {attempts} попыток")

    return result


def save_patterns(patterns_dict, path=GENERATED_FILE):
    with open(path, "w") as f:
        json.dump(patterns_dict, f, indent=2)
    print(f"\nСохранено {len(patterns_dict)} паттернов в {path}")


def load_patterns(path=GENERATED_FILE):
    if not os.path.exists(path):
        return {}
    with open(path, "r") as f:
        data = json.load(f)
    return data


if __name__ == "__main__":
    print("=== Генетический алгоритм паттернов (строгий режим) ===")
    print(f"Базовых паттернов: {len(BASE_PATTERNS)}")
    print("Критерии: симметрия >= 55%, плотность 15-60%, макс 3 цвета, связность >= 20%\n")

    print("Генерируем новые паттерны...")
    new = generate_patterns(n=10, min_score=0.55)

    save_patterns(new)
    print(f"\nИтого паттернов: {len(new)}")
    print("Теперь запусти train_dqn.py для дообучения!")
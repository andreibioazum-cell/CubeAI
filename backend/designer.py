"""Сеть-проектировщик: Кейн проектирует без перебора."""

import json
import math
import os
import random

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

from modules import MODULES, VARIANTS, DELTA
from levelgen import MAP_W, MAP_H, STYLES
from genome import Genome

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'designer.pt')
N_POS = MAP_W * MAP_H
STOP = N_POS                    # отдельный токен «карта закончена»
N_VAR = 16                      # rot(4) × flip(2) × sym(2)
DESC_KEYS = ('openness', 'loops', 'size')
DESC_LO = np.array([0.28, 0.0, 4.0])
DESC_HI = np.array([0.50, 1.0, 60.0])
MAX_TILES = 80              # в корпусе встречаются карты до 70 тайлов


# ─────────────────────────────────────────────────────────────
# Словарь модулей ↔ индексы
# ─────────────────────────────────────────────────────────────

def module_vocab():
    return sorted(MODULES)


def var_id(rot, flip, sym):
    return int(rot) * 4 + int(bool(flip)) * 2 + int(bool(sym))


def var_parts(v):
    return v // 4, bool((v % 4) // 2), bool(v % 2)


# ─────────────────────────────────────────────────────────────
# Сериализация карты в последовательность
# ─────────────────────────────────────────────────────────────

def pos_id(pos):
    return pos[1] * MAP_W + pos[0]


def pos_of(idx):
    return (idx % MAP_W, idx // MAP_W)


def serialize(gdict, vocab_index):
    """Геном → последовательность (позиция, модуль, вариант) в порядке BFS."""
    tiles = {tuple(p): (n, r, f, s) for p, n, r, f, s in gdict['tiles']}
    gate = tuple(gdict['gate'])
    if gate not in tiles:
        return None

    seen = {gate}
    order = [gate]
    queue = [gate]
    while queue:
        cur = queue.pop(0)
        for side in ('N', 'E', 'S', 'W'):
            dx, dy = DELTA[side]
            nb = (cur[0] + dx, cur[1] + dy)
            if nb in tiles and nb not in seen:
                seen.add(nb)
                order.append(nb)
                queue.append(nb)
    # тайлы, не связанные по сетке, добавляем в конец, чтобы не терять карту
    for p in tiles:
        if p not in seen:
            order.append(p)

    seq = []
    for p in order:
        n, r, f, s = tiles[p]
        if n not in vocab_index:
            return None
        seq.append((pos_id(p), vocab_index[n], var_id(r, f, s)))
    return seq


def norm_desc(desc):
    v = np.array([float(desc[k]) for k in DESC_KEYS])
    return np.clip((v - DESC_LO) / (DESC_HI - DESC_LO), 0.0, 1.0)


# ─────────────────────────────────────────────────────────────
# Модель
# ─────────────────────────────────────────────────────────────

class Designer(nn.Module):
    def __init__(self, n_modules, d=192, layers=4, heads=4, max_len=MAX_TILES + 2):
        super().__init__()
        self.n_modules = n_modules
        self.pos_emb = nn.Embedding(N_POS + 1, d)
        self.mod_emb = nn.Embedding(n_modules + 1, d)   # +1 — «нет» для старта
        self.var_emb = nn.Embedding(N_VAR + 1, d)
        self.step_emb = nn.Embedding(max_len, d)
        self.cond = nn.Sequential(nn.Linear(len(DESC_KEYS), d), nn.GELU(),
                                  nn.Linear(d, d))

        layer = nn.TransformerEncoderLayer(d_model=d, nhead=heads,
                                           dim_feedforward=d * 4,
                                           dropout=0.1, batch_first=True,
                                           norm_first=True, activation='gelu')
        self.body = nn.TransformerEncoder(layer, layers)
        self.norm = nn.LayerNorm(d)
        self.head_pos = nn.Linear(d, N_POS + 1)         # +1 — STOP
        self.head_mod = nn.Linear(d, n_modules)
        self.head_var = nn.Linear(d, N_VAR)

    def forward(self, pos, mod, var, desc):
        b, t = pos.shape
        steps = torch.arange(t, device=pos.device).unsqueeze(0).expand(b, t)
        x = (self.pos_emb(pos) + self.mod_emb(mod) + self.var_emb(var)
             + self.step_emb(steps))
        x = x + self.cond(desc).unsqueeze(1)
        mask = torch.triu(torch.ones(t, t, device=pos.device, dtype=torch.bool),
                          diagonal=1)
        h = self.norm(self.body(x, mask=mask))
        return self.head_pos(h), self.head_mod(h), self.head_var(h)


# ─────────────────────────────────────────────────────────────
# Данные
# ─────────────────────────────────────────────────────────────

def build_dataset(rows, vocab_index, max_len=MAX_TILES):
    """Последовательности с паддингом. Каждая карта — один пример."""
    P, M, V, D, L = [], [], [], [], []
    for r in rows:
        seq = serialize(r['genome'], vocab_index)
        if not seq or len(seq) > max_len:
            continue
        n = len(seq)
        # вход сдвинут на шаг: первый токен — «пусто», предсказываем первый тайл
        pos = [N_POS] + [s[0] for s in seq]
        mod = [len(vocab_index)] + [s[1] for s in seq]
        var = [N_VAR] + [s[2] for s in seq]
        tgt_pos = [s[0] for s in seq] + [STOP]
        tgt_mod = [s[1] for s in seq] + [0]
        tgt_var = [s[2] for s in seq] + [0]

        pad = max_len + 1 - len(pos)
        P.append(pos + [N_POS] * pad)
        M.append(mod + [len(vocab_index)] * pad)
        V.append(var + [N_VAR] * pad)
        D.append(norm_desc(r['desc']))
        L.append([tgt_pos + [-100] * pad, tgt_mod + [-100] * pad,
                  tgt_var + [-100] * pad])
    if not P:
        return None
    return (torch.tensor(P), torch.tensor(M), torch.tensor(V),
            torch.tensor(np.array(D), dtype=torch.float32),
            torch.tensor(L))


# ─────────────────────────────────────────────────────────────
# Обучение
# ─────────────────────────────────────────────────────────────

def train(rows, epochs=30, batch=64, lr=3e-4, device=None, verbose=True,
          val_frac=0.1, seed=0):
    device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
    vocab = module_vocab()
    vidx = {n: i for i, n in enumerate(vocab)}

    data = build_dataset(rows, vidx)
    if data is None:
        raise RuntimeError('корпус пуст или все карты длиннее лимита')
    P, M, V, D, L = data
    n = len(P)
    g = torch.Generator().manual_seed(seed)
    perm = torch.randperm(n, generator=g)
    n_val = max(1, int(n * val_frac))
    vi, ti = perm[:n_val], perm[n_val:]

    model = Designer(len(vocab)).to(device)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    sched = torch.optim.lr_scheduler.OneCycleLR(
        opt, max_lr=lr, total_steps=max(1, epochs * math.ceil(len(ti) / batch)))

    def run_split(idx, training):
        model.train(training)
        total, steps = 0.0, 0
        order = idx[torch.randperm(len(idx), generator=g)] if training else idx
        for i in range(0, len(order), batch):
            sl = order[i:i + batch]
            p, m, v, d, l = (P[sl].to(device), M[sl].to(device), V[sl].to(device),
                             D[sl].to(device), L[sl].to(device))
            with torch.set_grad_enabled(training):
                lp, lm, lv = model(p, m, v, d)
                loss = (F.cross_entropy(lp.reshape(-1, N_POS + 1), l[:, 0].reshape(-1),
                                        ignore_index=-100)
                        + F.cross_entropy(lm.reshape(-1, len(vocab)), l[:, 1].reshape(-1),
                                          ignore_index=-100)
                        + F.cross_entropy(lv.reshape(-1, N_VAR), l[:, 2].reshape(-1),
                                          ignore_index=-100))
            if training:
                opt.zero_grad()
                loss.backward()
                nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step()
                sched.step()
            total += float(loss)
            steps += 1
        return total / max(steps, 1)

    history = []
    for ep in range(1, epochs + 1):
        tr = run_split(ti, True)
        va = run_split(vi, False)
        history.append({'epoch': ep, 'train': round(tr, 4), 'val': round(va, 4)})
        if verbose and (ep % max(1, epochs // 10) == 0 or ep == 1):
            print(f'  эпоха {ep:3}  обучение {tr:.4f}  проверка {va:.4f}')

    return model, vocab, history


def save(model, vocab, path=MODEL_PATH):
    torch.save({'state': model.state_dict(), 'vocab': vocab,
                'n_modules': len(vocab)}, path)
    return path


def load(path=MODEL_PATH, device=None):
    if not os.path.exists(path):
        return None, None
    # Словарь сети включает изобретённые модули: без них имена из чекпоинта
    # не с чем сопоставить.
    try:
        import modgen
        modgen.load()
    except Exception:
        pass
    device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
    ck = torch.load(path, map_location=device, weights_only=False)
    model = Designer(ck['n_modules']).to(device)
    model.load_state_dict(ck['state'])
    model.eval()
    return model, ck['vocab']


# ─────────────────────────────────────────────────────────────
# Проектирование
# ─────────────────────────────────────────────────────────────

def _neighbour_mask(placed):
    """Куда разрешено ставить следующий тайл: только рядом с уже стоящими."""
    allowed = np.zeros(N_POS + 1, dtype=bool)
    allowed[STOP] = True
    for (tx, ty) in placed:
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = tx + dx, ty + dy
            if 0 <= nx < MAP_W and 0 <= ny < MAP_H and (nx, ny) not in placed:
                allowed[ny * MAP_W + nx] = True
    return allowed


@torch.no_grad()
def design(model, vocab, target, style=None, temperature=0.9, rng=None,
           device=None, max_tiles=MAX_TILES):
    """Спроектировать карту под заданный дескриптор — без перебора."""
    device = device or next(model.parameters()).device
    rng = rng or random.Random()
    d = torch.tensor(norm_desc(target), dtype=torch.float32,
                     device=device).unsqueeze(0)

    gate = (MAP_W // 2, MAP_H - 1)
    pos = [N_POS]
    mod = [len(vocab)]
    var = [N_VAR]
    tiles = {gate: {'name': 'gate', 'rot': 0, 'flip': False, 'sym': False}}
    placed = {gate}

    # первый тайл фиксирован: вход всегда на месте
    pos.append(pos_id(gate))
    mod.append(vocab.index('gate'))
    var.append(var_id(0, False, False))

    for _ in range(max_tiles - 1):
        p = torch.tensor([pos], device=device)
        m = torch.tensor([mod], device=device)
        v = torch.tensor([var], device=device)
        lp, lm, lv = model(p, m, v, d)
        lp, lm, lv = lp[0, -1], lm[0, -1], lv[0, -1]

        mask = torch.tensor(_neighbour_mask(placed), device=device)
        lp = lp.masked_fill(~mask, float('-inf'))
        pi = int(torch.multinomial(F.softmax(lp / temperature, -1), 1))
        if pi == STOP:
            break

        mi = int(torch.multinomial(F.softmax(lm / temperature, -1), 1))
        vi = int(torch.multinomial(F.softmax(lv / temperature, -1), 1))
        name = vocab[mi]
        if name == 'gate':                      # вход в карте один
            name = 'corridor'
            mi = vocab.index('corridor')
        if name not in MODULES:
            # модуль вымер после обучения: подменяем базовым, а не падаем
            name = 'corridor'
        rot, flip, sym = var_parts(vi)
        rot = rot % max(1, len(VARIANTS[name]))

        cell = pos_of(pi)
        tiles[cell] = {'name': name, 'rot': int(VARIANTS[name][rot]['rot']),
                       'flip': flip, 'sym': sym}
        placed.add(cell)
        pos.append(pi)
        mod.append(mi)
        var.append(vi)

    import copy
    style = copy.deepcopy(style or rng.choice(list(STYLES.values())))
    return Genome(tiles, gate, style)

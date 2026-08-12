"""Вкусовая часть критика: как постройка выглядит."""

import functools
import os
import sys

import numpy as np

MODEL_ID = 'openai/clip-vit-base-patch32'
ANCHORS_PATH = os.path.join(os.path.dirname(__file__), 'taste_anchors.npz')
REFERENCES_DIR = os.path.join(os.path.dirname(__file__), 'references')

# Сколько карт каждого вида кодировать при построении прототипов
ANCHOR_SAMPLES = 14


@functools.lru_cache(maxsize=1)
def _load():
    """Модель грузится лениво и один раз."""
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor
        model = CLIPModel.from_pretrained(MODEL_ID)
        proc = CLIPProcessor.from_pretrained(MODEL_ID)
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        return {'model': model.to(device).eval(), 'proc': proc,
                'device': device, 'torch': torch}
    except Exception as e:
        return {'error': f'{type(e).__name__}: {e}'}


def available():
    return 'error' not in _load()


def embed(images, batch=16):
    """Нормированные эмбеддинги картинок."""
    ctx = _load()
    if 'error' in ctx:
        return None
    torch = ctx['torch']
    out = []
    for i in range(0, len(images), batch):
        inp = ctx['proc'](images=images[i:i + batch],
                          return_tensors='pt').to(ctx['device'])
        with torch.no_grad():
            f = ctx['model'].get_image_features(**inp)
            # свежие transformers отдают объект, а не тензор
            if not torch.is_tensor(f):
                f = getattr(f, 'image_embeds', None)
                if f is None:
                    f = ctx['model'].visual_projection(
                        ctx['model'].vision_model(**inp).pooler_output)
            f = torch.nn.functional.normalize(f, dim=-1)
        out.append(f.detach().cpu().numpy())
    return np.concatenate(out)


# ─────────────────────────────────────────────────────────────
# Прототипы уродства
# ─────────────────────────────────────────────────────────────

def _degenerate_styles():
    """Те же вырожденные постройки, что и в приёмке критика."""
    import copy
    from levelgen import STYLES

    def make(base='cave', **over):
        s = copy.deepcopy(STYLES[base])
        w = over.pop('weights', None)
        if w is not None:
            s['weights'] = {k: 0.0 for k in s['weights']}
            s['weights'].update(w)
        s.update(over)
        return s

    return {
        'snake': make(weights={'corridor': 1.0}, branching=0.0,
                      symmetry=0.0, size=20),
        'monotony': make(weights={'corridor': 1.0, 'room_small': 6.0},
                         branching=0.3, symmetry=0.0, size=20),
        'huddle': make(weights={'corridor': 1.0, 'turn': 2.0}, branching=1.0,
                       symmetry=0.0, size=8),
        'blob': make(weights={'yard': 1.0}, branching=0.9,
                     symmetry=0.0, size=24),
    }


def build_anchors(force=False, verbose=True):
    """Построить прототипы уродства и шкалу нормы."""
    if os.path.exists(ANCHORS_PATH) and not force:
        return np.load(ANCHORS_PATH, allow_pickle=True)
    if not available():
        return None

    from levelgen import STYLES, generate, generate_novel
    from render_iso import render

    bad_names, bad_vecs = [], []
    for name, style in _degenerate_styles().items():
        imgs = [render(generate(style)) for _ in range(ANCHOR_SAMPLES)]
        c = embed(imgs).mean(0)
        bad_vecs.append(c / np.linalg.norm(c))
        bad_names.append(name)
        if verbose:
            print(f'  прототип уродства: {name}')

    keys = list(STYLES)
    norm_imgs = []
    for k in keys:
        norm_imgs += [render(generate_novel(STYLES[k]))
                      for _ in range(max(2, ANCHOR_SAMPLES // len(keys)))]
    norm = embed(norm_imgs)
    bad = np.stack(bad_vecs)
    norm_bad_sim = (norm @ bad.T).max(1)

    np.savez(ANCHORS_PATH, bad=bad, bad_names=np.array(bad_names),
             mu=float(norm_bad_sim.mean()), sigma=float(norm_bad_sim.std() + 1e-6))
    if verbose:
        print(f'  норма: похожесть на уродство {norm_bad_sim.mean():.4f} '
              f'± {norm_bad_sim.std():.4f}')
        print(f'  сохранено: {ANCHORS_PATH}')
    return np.load(ANCHORS_PATH, allow_pickle=True)


@functools.lru_cache(maxsize=1)
def _anchors():
    if not os.path.exists(ANCHORS_PATH):
        return None
    return dict(np.load(ANCHORS_PATH, allow_pickle=True))


@functools.lru_cache(maxsize=1)
def _positive():
    """Образцы «нравится», выложенные человеком в references/."""
    if not os.path.isdir(REFERENCES_DIR):
        return None
    from PIL import Image
    paths = [os.path.join(REFERENCES_DIR, f)
             for f in sorted(os.listdir(REFERENCES_DIR))
             if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    if not paths:
        return None
    imgs = [Image.open(p).convert('RGB') for p in paths]
    e = embed(imgs)
    if e is None:
        return None
    c = e.mean(0)
    return c / np.linalg.norm(c), len(paths)


def taste(level, image=None):
    """Оценка вида от 0 до 1. None, если модель или прототипы недоступны."""
    a = _anchors()
    if a is None or not available():
        return None

    from render_iso import render
    e = embed([image or render(level)])
    if e is None:
        return None
    e = e[0]

    bad_sim = float((e @ a['bad'].T).max())
    z = (float(a['mu']) - bad_sim) / float(a['sigma'])
    score = 1.0 / (1.0 + np.exp(-z))

    pos = _positive()
    if pos is not None:
        pc, _ = pos
        # похожесть на образцы человека подмешивается мягко: она задаёт
        # предпочтение, но не должна перекрывать защиту от вырождения
        score = 0.65 * score + 0.35 * float(np.clip((e @ pc) * 2.0, 0, 1))
    return float(np.clip(score, 0.0, 1.0))


def status():
    if not available():
        return f'вкус недоступен: {_load().get("error")}'
    a = _anchors()
    if a is None:
        return ('модель есть, прототипы не построены — '
                'запусти: python clip_taste.py build')
    pos = _positive()
    extra = f', образцов человека: {pos[1]}' if pos else ''
    return (f'вкус включён, {MODEL_ID} на {_load()["device"]}, '
            f'прототипов уродства: {len(a["bad"])}{extra}')


if __name__ == '__main__':
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass

    if len(sys.argv) > 1 and sys.argv[1] == 'build':
        print('строю прототипы...')
        build_anchors(force=True)
    print(status())

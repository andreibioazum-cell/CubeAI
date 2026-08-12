"""Изометрическая растеризация карты в картинку."""

from PIL import Image, ImageDraw

TW, TH = 8, 4          # половина ширины и высоты ромба верхней грани
BH = 7                 # высота блока в пикселях


def _shade(hex_color, k):
    c = hex_color.lstrip('#')
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    return (min(255, int(r * k)), min(255, int(g * k)), min(255, int(b * k)))


def render(level, size=(512, 512), sky=None):
    """Карта → картинка. Порядок отрисовки — от дальних блоков к ближним."""
    bp = level.blueprint
    img = Image.new('RGB', size, _shade(sky or level.sky or '#101010', 1.0))
    if not bp:
        return img
    draw = ImageDraw.Draw(img)

    xs = [b['x'] for b in bp]
    zs = [b['z'] for b in bp]
    cx = (min(xs) + max(xs)) / 2
    cz = (min(zs) + max(zs)) / 2
    max_y = max(b['y'] for b in bp)

    # Габариты в изометрии: ширина ~ (span_x + span_z) * tw,
    # высота ~ то же по th плюс подъём по y. Подбираем tw так, чтобы
    # постройка занимала кадр целиком — CLIP на мелком объекте слеп.
    sx = max(xs) - min(xs) + 1
    sz = max(zs) - min(zs) + 1
    diag = sx + sz
    tw = size[0] * 0.92 / diag
    th, bh = tw / 2, tw * 0.9
    fit_h = diag * th + max_y * bh
    if fit_h > size[1] * 0.9:
        k = size[1] * 0.9 / fit_h
        tw, th, bh = tw * k, th * k, bh * k

    ox = size[0] / 2
    oy = (size[1] + max_y * bh - (sx + sz) * 0) / 2

    # Художник: сначала дальние (меньше x+z), внутри столбца — нижние
    order = sorted(bp, key=lambda b: (b['x'] + b['z'], b['y']))

    for b in order:
        px = ox + (b['x'] - cx - (b['z'] - cz)) * tw
        py = oy + (b['x'] - cx + (b['z'] - cz)) * th - b['y'] * bh
        col = b['color']
        top = _shade(col, 1.0)
        left = _shade(col, 0.68)
        right = _shade(col, 0.84)

        draw.polygon([(px, py - th), (px + tw, py),
                      (px, py + th), (px - tw, py)], fill=top)
        draw.polygon([(px - tw, py), (px, py + th),
                      (px, py + th + bh), (px - tw, py + bh)], fill=left)
        draw.polygon([(px + tw, py), (px, py + th),
                      (px, py + th + bh), (px + tw, py + bh)], fill=right)

    return img


if __name__ == '__main__':
    import sys
    from levelgen import STYLES, generate_novel

    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding='utf-8')
        except (AttributeError, ValueError):
            pass

    name = sys.argv[1] if len(sys.argv) > 1 else 'castle'
    out = sys.argv[2] if len(sys.argv) > 2 else 'iso.png'
    lv = generate_novel(STYLES[name])
    render(lv).save(out)
    print(f'{STYLES[name]["name"]}: {len(lv.blueprint)} блоков -> {out}')

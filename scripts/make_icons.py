"""Draw the app icons (sprout growing from a coin) with Pillow."""
from PIL import Image, ImageDraw
import os, sys
out = sys.argv[1]
os.makedirs(out, exist_ok=True)
BG, GOLD, GOLD2, LEAF, LEAF2 = (23, 48, 42), (232, 182, 64), (201, 148, 38), (88, 201, 150), (60, 170, 120)
def draw(size, pad_ratio):
    S = 1024
    im = Image.new('RGBA', (S, S), BG + (255,))
    d = ImageDraw.Draw(im)
    k = 1 - 2 * pad_ratio
    def P(x, y): return (S * pad_ratio + x * k, S * pad_ratio + y * k)
    def box(x0, y0, x1, y1): return [P(x0, y0), P(x1, y1)]
    # coin
    d.ellipse(box(262, 560, 762, 900), fill=GOLD2)
    d.ellipse(box(262, 520, 762, 860), fill=GOLD)
    d.ellipse(box(342, 575, 682, 805), outline=GOLD2, width=int(18 * k))
    # stem
    d.rounded_rectangle(box(492, 300, 532, 640), radius=int(20 * k), fill=LEAF2)
    # leaves
    d.chord(box(210, 200, 520, 470), 0, 360, fill=LEAF)
    d.chord(box(504, 120, 830, 400), 0, 360, fill=LEAF2)
    d.line([P(300, 335), P(505, 400)], fill=BG, width=int(14 * k))
    d.line([P(735, 260), P(525, 330)], fill=BG, width=int(14 * k))
    return im.resize((size, size), Image.LANCZOS)
draw(192, 0.04).save(f'{out}/icon-192.png')
draw(512, 0.04).save(f'{out}/icon-512.png')
draw(512, 0.14).save(f'{out}/icon-maskable-512.png')
draw(180, 0.06).convert('RGB').save(f'{out}/apple-touch-icon.png')
draw(64, 0.02).save(f'{out}/favicon.png')
print('icons ->', out)

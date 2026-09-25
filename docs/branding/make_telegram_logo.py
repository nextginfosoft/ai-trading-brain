"""
TradeSense AI logo as a Telegram profile/group photo.

    python docs/branding/make_telegram_logo.py      # writes tradesense-telegram-640.png next to this file

Square 640x640 PNG with a full-bleed background (Telegram crops photos to a
circle), drawn from the same geometry as web_dashboard/frontend/public/favicon.svg.
Needs Pillow.
"""

import math
import os

from PIL import Image, ImageDraw

OUT_DIR = os.path.dirname(os.path.abspath(__file__))
SIZE = 640
SS = 4                      # supersampling for smooth edges
W = SIZE * SS
BG = (18, 21, 26)           # #12151a
BLUE = (57, 135, 229)       # #3987e5
ARC = (109, 167, 236)       # #6da7ec
ARC_FADED = (64, 94, 131)   # #6da7ec at 50% over the background
GREEN = (31, 184, 90)       # #1fb85a

# Favicon geometry (32-unit grid). Arcs are centred on the signal node (21, 13).
UNIT = SIZE * 0.52 / 24 * SS          # mark (~24 units wide) fills ~52% of the width: safe inside the circle crop
CX, CY = 18.3, 14.4                    # visual centre of the mark in grid units


def pt(x, y):
    return (W / 2 + (x - CX) * UNIT, W / 2 + (y - CY) * UNIT)


def main() -> None:
    img = Image.new("RGB", (W, W), BG)
    d = ImageDraw.Draw(img)

    # Price line with round caps
    line = [pt(6, 23), pt(11.5, 17), pt(15.5, 20), pt(21, 13)]
    lw = int(2.6 * UNIT)
    d.line(line, fill=BLUE, width=lw, joint="curve")
    for x, y in line:
        r = lw / 2
        d.ellipse([x - r, y - r, x + r, y + r], fill=BLUE)

    # Sensing arcs (radius 4.5 and 7.9 around the node, -45..45 degrees) with round caps
    node = pt(21, 13)
    for radius, color in ((7.9, ARC_FADED), (4.5, ARC)):
        rr = radius * UNIT
        aw = int(1.7 * UNIT)
        d.arc([node[0] - rr, node[1] - rr, node[0] + rr, node[1] + rr], -45, 45, fill=color, width=aw)
        for ang in (-45, 45):
            ex = node[0] + (rr - aw / 2) * math.cos(math.radians(ang))
            ey = node[1] + (rr - aw / 2) * math.sin(math.radians(ang))
            d.ellipse([ex - aw / 2, ey - aw / 2, ex + aw / 2, ey + aw / 2], fill=color)

    # Signal node with a background-coloured ring
    r_outer, r_inner = 3.75 * UNIT, 2.25 * UNIT
    d.ellipse([node[0] - r_outer, node[1] - r_outer, node[0] + r_outer, node[1] + r_outer], fill=BG)
    d.ellipse([node[0] - r_inner, node[1] - r_inner, node[0] + r_inner, node[1] + r_inner], fill=GREEN)

    out = os.path.join(OUT_DIR, "tradesense-telegram-640.png")
    img.resize((SIZE, SIZE), Image.LANCZOS).save(out, optimize=True)
    print("saved", out)


if __name__ == "__main__":
    main()

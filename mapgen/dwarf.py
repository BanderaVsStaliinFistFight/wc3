"""The Dark Iron Thane: a custom hero model built the way the classic
Warcraft III units are -- about a thousand polygons of angular planes (soft
where a surface curves gently, creased where it turns sharply) on a full
skeleton, a small hand-painted texture, and team colour showing through the
texture's alpha.

The model is built in its standing pose; the animations rotate the bones
away from it. Model space: +X is forward, +Y is the dwarf's left, +Z is up,
one unit per world unit. The dwarf stands about 108 units tall, topknot
included.
"""

import math

from . import bake, image, mdx
from .lowpoly import Builder, add, cross, dot, ellipse, frame, lerp, mirror, mul, norm, ring, section, sub
from .mdx import quat_euler

MODEL_PATH = 'war3mapImported\\DarkIronThane.mdx'
TEXTURE_PATH = 'war3mapImported\\DarkIronThane.blp'
ICON_PATH = 'war3mapImported\\BTNDarkIronThane.blp'
DISICON_PATH = 'ReplaceableTextures\\CommandButtonsDisabled\\DISBTNDarkIronThane.blp'

TEX = 256

# texture atlas regions in pixels: (x0, y0, x1, y1)
REGIONS = {
    'head': (0, 0, 128, 64),
    'beard': (128, 0, 192, 64),
    'torso': (192, 0, 256, 64),
    'pauldron': (0, 64, 64, 128),
    'shield': (64, 64, 128, 128),
    'arm': (128, 64, 160, 96),
    'hand': (128, 96, 160, 128),
    'gauntlet': (160, 64, 192, 96),
    'thigh': (160, 96, 192, 128),
    'boot': (192, 64, 224, 96),
    'foot': (192, 96, 224, 128),
    'hammer': (224, 64, 256, 96),
    'tasset': (224, 96, 256, 128),
    'belt': (0, 128, 64, 144),
    'fur': (0, 144, 64, 160),
    'hips': (0, 160, 64, 192),
    'cloth': (64, 128, 96, 160),
    'backcloth': (64, 160, 96, 192),
    'buckle': (96, 128, 128, 144),
    'knee': (96, 144, 112, 160),
    'thumb': (112, 144, 128, 160),
    'eye': (96, 160, 112, 176),
    'gem': (112, 160, 128, 176),
    'spike': (96, 176, 128, 192),
    'handle': (128, 128, 144, 192),
    'grip': (144, 128, 160, 160),
    'gold': (144, 160, 160, 192),
    'iron': (160, 128, 224, 160),
    'moustache': (0, 192, 32, 224),
    'topknot': (32, 192, 48, 224),
    'brow': (48, 192, 64, 208),
    'ear': (48, 208, 64, 224),
}

# regions shared by unrelated parts get no baked shading
SHARED = {'gold', 'iron', 'spike', 'eye', 'gem', 'handle', 'grip'}

GEO_MAIN, GEO_GLOW = 0, 1

BONES = [
    # name, parent, pivot -- the layout of the classic hero skeletons
    ('Root', -1, (0.0, 0.0, 38.0)),
    ('Pelvis', 0, (0.0, 0.0, 38.0)),
    ('Chest', 1, (0.0, 0.0, 46.0)),
    ('Head', 2, (3.0, 0.0, 77.0)),
    ('ShoulderL', 2, (0.0, 14.0, 72.0)),
    ('ArmL', 4, (-1.0, 25.0, 70.0)),
    ('ForeL', 5, (-3.0, 34.0, 55.0)),
    ('HandL', 6, (0.8, 39.0, 42.5)),
    ('ShoulderR', 2, (0.0, -14.0, 72.0)),
    ('ArmR', 8, (-1.0, -25.0, 70.0)),
    ('ForeR', 9, (-3.0, -34.0, 55.0)),
    ('HandR', 10, (0.8, -39.0, 42.5)),
    ('Hammer', 11, (2.0, -39.8, 36.5)),
    ('ThighL', 1, (0.0, 10.0, 38.0)),
    ('ShinL', 13, (3.8, 12.8, 22.0)),
    ('FootL', 14, (0.8, 15.0, 7.0)),
    ('ThighR', 1, (0.0, -10.0, 38.0)),
    ('ShinR', 16, (3.8, -12.8, 22.0)),
    ('FootR', 17, (0.8, -15.0, 7.0)),
]
B = {name: i for i, (name, _, _) in enumerate(BONES)}

FIST = (2.0, 39.8, 36.5)                       # left fist; the right one mirrors it
HAMMER_DIR = norm((0.52, -0.12, -0.85))         # from the right fist to the hammer head
HAMMER_HEAD = 24.0
SHIELD_C = (7.0, 49.5, 44.0)
SHIELD_N = norm((0.45, 0.89, 0.0))

ICON_CAMERA = {'eye': (66.0, -30.0, 92.0), 'target': (8.0, -3.0, 82.0), 'fov': 0.62}


def atlas(region, u, v):
    x0, y0, x1, y1 = REGIONS[region]
    u = min(1.0, max(0.0, u))
    v = min(1.0, max(0.0, v))
    return ((x0 + 1.0 + u * (x1 - x0 - 2)) / TEX, (y0 + 1.0 + v * (y1 - y0 - 2)) / TEX)


def _bones(*names):
    ids = sorted({B[n] for n in names})
    return ids[0] if len(ids) == 1 else tuple(ids)


def _side(name, side):
    """'ArmL' -> 'ArmR' for the right side."""
    return name if side > 0 or not name.endswith('L') else name[:-1] + 'R'


# ---------------------------------------------------------------------------
# the head
# ---------------------------------------------------------------------------

HEAD_ANGLES = [0, 12, 30, 60, 95, 135, 180]
HEAD = [
    # height, centre x, radius at each angle (front, nose side, eye, cheek, side, back)
    (73.5, 4.0, [5.5, 5.6, 6.0, 6.5, 6.5, 6.0, 5.5]),
    (77.5, 4.5, [10.2, 10.2, 10.2, 10.2, 9.8, 8.6, 7.8]),
    (81.0, 4.5, [14.2, 11.8, 11.0, 11.2, 10.4, 9.4, 8.8]),    # nose tip, cheeks
    (84.5, 4.5, [12.4, 11.0, 9.6, 11.0, 10.6, 9.8, 9.2]),     # bridge, eye sockets, cheekbones
    (87.5, 4.5, [11.2, 11.4, 11.6, 11.2, 10.6, 10.0, 9.4]),   # heavy brow
    (91.0, 4.0, [10.6, 10.6, 10.6, 10.4, 10.0, 9.6, 9.2]),    # forehead
    (94.5, 3.5, [8.8, 8.8, 8.8, 8.6, 8.4, 8.2, 8.0]),
    (97.0, 3.2, [5.6, 5.6, 5.6, 5.5, 5.4, 5.3, 5.2]),
    (98.3, 3.0, [2.2, 2.2, 2.2, 2.2, 2.2, 2.2, 2.2]),
]
HEAD_C = (4.5, 0.0, 86.0)
HEAD_POINT_ANGLES = [-180, -135, -95, -60, -30, -12, 0, 12, 30, 60, 95, 135]


def head_u(angle):
    """Texture u for an angle round the head: the face gets the most room."""
    return 0.5 + 0.5 * math.copysign((abs(angle) / 180.0) ** 0.7, angle)


def head_angle(u):
    x = (u - 0.5) / 0.5
    return math.copysign(180.0 * abs(x) ** (1 / 0.7), x)


def _head_level_point(level, angle):
    z, cx, radii = HEAD[level]
    a = abs(angle)
    k = 0
    while k < len(HEAD_ANGLES) - 2 and a > HEAD_ANGLES[k + 1]:
        k += 1
    t = (a - HEAD_ANGLES[k]) / (HEAD_ANGLES[k + 1] - HEAD_ANGLES[k])

    def polar(ang, r):
        return (cx + r * math.cos(math.radians(ang)), r * math.sin(math.radians(ang)), z)
    p = lerp(polar(HEAD_ANGLES[k], radii[k]), polar(HEAD_ANGLES[k + 1], radii[k + 1]), t)
    return (p[0], p[1] if angle >= 0 else -p[1], p[2])


def head_surface(angle, z, out=0.0):
    """A point on the faceted head at an angle and height, pushed out along
    the horizontal normal."""
    i = 0
    while i < len(HEAD) - 2 and z > HEAD[i + 1][0]:
        i += 1
    t = (z - HEAD[i][0]) / (HEAD[i + 1][0] - HEAD[i][0])
    p = lerp(_head_level_point(i, angle), _head_level_point(i + 1, angle), t)
    o = norm((p[0] - HEAD_C[0], p[1], 0.0))
    return add(p, mul(o, out))


BEARD = [
    # height, front x, back x, half width
    (81.0, 12.6, 2.0, 10.8),
    (77.0, 16.2, 3.4, 12.0),
    (72.0, 19.6, 7.0, 12.8),
    (66.0, 21.2, 10.5, 12.4),
    (59.5, 21.8, 13.0, 10.6),
    (53.0, 21.4, 14.5, 7.6),
    (48.0, 20.2, 15.5, 4.0),
]
BEARD_TIP = (19.2, 0.0, 43.5)


def _beard_half(xf, xb, w):
    """The left half of a beard section, front to side."""
    return [(xf, 0.0), (xf - 0.8, 0.45 * w), (xf - 3.0, 0.85 * w), ((xf + xb) / 2 - 1.0, w), (xb + 1.0, 0.7 * w)]


def beard_section(z, xf, xb, w):
    half = _beard_half(xf, xb, w)
    pts = [(xb, 0.0)] + [(x, -y) for x, y in reversed(half[1:])] + half[:-1] + [half[-1]]
    return [(x, y, z) for x, y in pts]


def beard_front(y, z):
    """x of the front of the beard at (y, z)."""
    i = 0
    while i < len(BEARD) - 2 and z < BEARD[i + 1][0]:
        i += 1
    t = (BEARD[i][0] - z) / (BEARD[i][0] - BEARD[i + 1][0])
    _, xf, xb, w = (a + (b - a) * t for a, b in zip(BEARD[i], BEARD[i + 1]))
    half = _beard_half(xf, xb, w)[:4]
    y = abs(y)
    for (x0, y0), (x1, y1) in zip(half, half[1:]):
        if y <= y1:
            return x0 + (x1 - x0) * (y - y0) / (y1 - y0)
    return half[-1][0]


def octagon(ha, hb, c=0.6):
    """A chamfered rectangle, counter-clockwise from the back (-a)."""
    return [(-ha, -c * hb), (-c * ha, -hb), (c * ha, -hb), (ha, -c * hb), (ha, c * hb), (c * ha, hb),
            (-c * ha, hb), (-ha, c * hb)]


def path_sections(path, radii, count, hint=(1.0, 0.0, 0.0), phase=0.0, shape=None):
    """Elliptical sections along a path of points; radii are (along the
    hint, across) per point. shape(i, j) can scale single points."""
    out = []
    for i, (c, (ra, rb)) in enumerate(zip(path, radii)):
        d = sub(path[min(i + 1, len(path) - 1)], path[max(i - 1, 0)])
        ax, ay = frame(d, hint)
        sec = ellipse(c, ax, ay, ra, rb, count, phase)
        if shape:
            sec = [add(c, mul(sub(p, c), shape(i, j))) for j, p in enumerate(sec)]
        out.append(sec)
    return out


def zigzag(last):
    """A ragged lower edge for fur: every other point of the last section pulled in."""
    return lambda i, j: (0.86 if j % 2 else 1.06) if i == last else 1.0


# ---------------------------------------------------------------------------
# the mesh
# ---------------------------------------------------------------------------

def build_mesh():
    m = Builder(2, atlas)
    head = B['Head']

    # -- head
    us = [head_u(a) for a in HEAD_POINT_ANGLES]
    m.loft(GEO_MAIN, 'head', [ring((cx, 0.0, z), HEAD_ANGLES, radii) for z, cx, radii in HEAD], head,
           caps=('end',), us=us, smooth=55)
    for side in (1, -1):
        def s(p, side=side):
            return p if side > 0 else mirror(p)
        # glowing eyes, slanted in a scowl
        eye = [head_surface(21, 84.8, 0.45), head_surface(31, 86.3, 0.45), head_surface(42, 86.0, 0.45),
               head_surface(31, 84.5, 0.45)]
        m.mesh(GEO_GLOW, 'eye', [s(p) for p in eye], [(0.0, 0.5), (0.5, 0.0), (1.0, 0.5), (0.5, 1.0)], [head] * 4,
               [[0, 1, 2, 3]], outward=s((0.86, 0.5, 0.0)))
        # brows: thick wedges in an angry V
        brow = [(5, 85.8, 0.9), (15, 87.0, 1.2), (27, 88.1, 1.3), (39, 88.7, 1.0), (50, 88.7, 0.4)]
        sections = []
        for k, (a, z, size) in enumerate(brow):
            c = head_surface(a, z, 0.8)
            prev = head_surface(*brow[max(k - 1, 0)][:2], 0.8)
            nxt = head_surface(*brow[min(k + 1, len(brow) - 1)][:2], 0.8)
            ax, ay = frame(sub(nxt, prev), norm((c[0] - HEAD_C[0], c[1], 0.0)))
            if ay[2] < 0:
                ay = mul(ay, -1.0)
            sections.append([s(p) for p in section(c, ax, ay, [(1.0 * size, 0.1), (-0.5 * size, 1.0 * size),
                                                                (-0.5 * size, -0.9 * size)])])
        m.loft(GEO_MAIN, 'brow', sections, head, caps=('start', 'end'), smooth=40)
        # ears
        base = [head_surface(86, 84.0, -0.4), head_surface(102, 84.6, -0.4), head_surface(100, 89.8, -0.4),
                head_surface(86, 88.8, -0.4)]
        tip = add(head_surface(100, 88.2, 3.6), (-1.2, 0.0, 0.6))
        pts = [s(p) for p in base + [tip]]
        m.mesh(GEO_MAIN, 'ear', pts, [(0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0), (0.5, 0.5)], [head] * 5,
               [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4], [0, 3, 2, 1]], smooth=35)
        # a long drooping moustache lying on the beard
        must = [(1.0, 78.8, 1.2, 1.6), (4.6, 77.4, 1.5, 2.4), (8.4, 73.4, 1.6, 2.6), (10.4, 67.2, 1.5, 2.4),
                (10.0, 61.2, 1.2, 1.8), (8.8, 56.2, 0.15, 0.2)]
        path = [(17.6 if k == 0 else beard_front(y, z) + 0.8 * t, y, z) for k, (y, z, t, _) in enumerate(must)]
        sections = []
        for k, (c, (_, _, t, w)) in enumerate(zip(path, must)):
            ax, ay = frame(sub(path[min(k + 1, len(path) - 1)], path[max(k - 1, 0)]), (1.0, 0.0, 0.0))
            sections.append([s(p) for p in section(c, ax, ay, [(t, 0.0), (0.0, w), (-0.7 * t, 0.0), (0.0, -w)])])
        m.loft(GEO_MAIN, 'moustache', sections, head, caps=('start',), smooth=60)

    # -- the beard: a great wedge from the jaw to the belt
    sections = [beard_section(*b) for b in BEARD] + [[BEARD_TIP] * 10]
    m.loft(GEO_MAIN, 'beard', sections, head, caps=('start',), smooth=55)

    # -- topknot, bound with a gold ring
    knot = [(2.6, 0.0, 98.6), (1.4, 0.0, 103.0), (-1.4, 0.0, 106.6), (-5.6, 0.0, 107.6), (-9.6, 0.0, 105.0),
            (-11.8, 0.0, 100.4)]
    radii = [(3.6, 3.2), (3.0, 2.7), (3.2, 2.9), (2.8, 2.5), (1.8, 1.6), (0.15, 0.15)]
    m.loft(GEO_MAIN, 'topknot', path_sections(knot, radii, 6, hint=(0.0, 1.0, 0.0)), head, smooth=60)
    m.loft(GEO_MAIN, 'gold', path_sections([(2.4, 0.0, 99.8), (2.0, 0.0, 101.8)], [(4.0, 4.0), (3.7, 3.7)], 8,
                                           hint=(0.0, 1.0, 0.0)), head, smooth=60)

    # -- torso: a barrel chest in a dark iron breastplate
    angles = [0, 25, 55, 90, 125, 155, 180]
    torso = [(42.0, 0.5, [13.0, 13.2, 14.6, 16.4, 13.4, 11.2, 10.8]),
             (50.0, 1.5, [15.6, 15.8, 17.0, 19.0, 15.0, 12.4, 12.0]),
             (60.0, 2.0, [16.6, 17.2, 19.8, 22.0, 16.6, 13.4, 13.0]),
             (68.0, 1.5, [14.8, 15.8, 19.8, 22.6, 16.6, 13.6, 13.2]),
             (74.0, 1.0, [10.6, 11.4, 13.6, 15.6, 12.8, 10.6, 10.2]),
             (79.0, 2.0, [6.6, 6.6, 6.8, 7.2, 6.8, 6.4, 6.2])]
    m.loft(GEO_MAIN, 'torso', [ring((cx, 0.0, z), angles, r) for z, cx, r in torso],
           [_bones('Pelvis', 'Chest')] + [B['Chest']] * 5, smooth=50)

    # -- belt with a big buckle and an ember in it
    belt = [(38.0, 0.5, [14.4, 14.6, 16.0, 17.8, 14.8, 12.4, 12.0]),
            (42.2, 0.8, [15.4, 15.6, 17.0, 18.8, 15.6, 13.2, 12.8]),
            (46.4, 1.2, [16.2, 16.4, 17.6, 19.6, 16.0, 13.4, 13.0])]
    pelvis = B['Pelvis']
    m.loft(GEO_MAIN, 'belt', [ring((cx, 0.0, z), angles, r) for z, cx, r in belt], pelvis, smooth=50)
    m.loft(GEO_MAIN, 'buckle', [section((16.0, 0.0, 42.2), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), octagon(5.0, 4.4)),
                                section((18.6, 0.0, 42.2), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), octagon(4.0, 3.4))],
           pelvis, caps=('end',), smooth=40)
    gem = [(18.7, 0.0, 44.4), (18.7, 1.7, 42.2), (18.7, 0.0, 40.0), (18.7, -1.7, 42.2), (20.2, 0.0, 42.2)]
    m.mesh(GEO_GLOW, 'gem', gem, [(0.5, 0.0), (1.0, 0.5), (0.5, 1.0), (0.0, 0.5), (0.5, 0.5)], [pelvis] * 5,
           [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]], smooth=30)

    # -- hips, the team coloured tabard and the leg plates
    def hip_bones(p):
        if p[2] > 33.0 or abs(p[1]) < 4.0:
            return pelvis
        return _bones('Pelvis', 'ThighL' if p[1] > 0 else 'ThighR')
    hips = [(38.5, 0.5, [14.0, 14.2, 15.6, 17.2, 14.4, 12.0, 11.6]),
            (34.0, 0.3, [13.0, 13.2, 14.6, 16.4, 13.8, 11.6, 11.2]),
            (29.5, 0.0, [8.0, 8.6, 10.4, 12.0, 10.0, 8.4, 8.0]),
            (27.0, 0.0, [3.0] * 7)]
    m.loft(GEO_MAIN, 'hips', [ring((cx, 0.0, z), angles, r) for z, cx, r in hips], hip_bones, smooth=50)
    for front, region in ((1, 'cloth'), (-1, 'backcloth')):
        xs = [16.4, 15.6, 14.6, 13.8] if front > 0 else [-12.4, -11.8, -11.0, -10.4]
        rows = []
        for x, z, w in zip(xs, [38.6, 32.0, 25.6, 19.6], [7.2, 6.8, 6.4, 5.6]):
            rows.append([(x, -w, z), (x + front * 1.0, 0.0, z), (x, w, z)])
        m.sheet(GEO_MAIN, region, rows, pelvis, outward=(float(front), 0.0, 0.0), two_sided=True, thickness=0.5,
                smooth=40)
    for side in (1, -1):
        thigh = B[_side('ThighL', side)]
        rows = []
        for z, r in ((39.0, 17.0), (33.5, 18.4), (28.0, 19.6)):
            rows.append([(0.5 + r * math.cos(math.radians(a)), side * r * math.sin(math.radians(a)), z)
                         for a in (35, 60, 85)])
        m.sheet(GEO_MAIN, 'tasset', rows, [_bones('Pelvis', _side('ThighL', side)), thigh, thigh],
                outward=(0.5, side * 0.87, 0.0), two_sided=True, thickness=0.6, smooth=40)

    for side in (1, -1):
        def s(p, side=side):
            return p if side > 0 else mirror(p)

        def bone(name, side=side):
            return B[_side(name, side)]

        def blend(*names, side=side):
            return _bones(*(_side(n, side) for n in names))

        def place(sections, side=side):
            return [[p if side > 0 else mirror(p) for p in sec] for sec in sections]

        # -- legs: leather breeches, knee guards, fur topped boots
        m.loft(GEO_MAIN, 'thigh', place(path_sections(
            [(0.0, 10.0, 39.0), (1.6, 11.6, 31.0), (3.8, 12.8, 23.0)], [(9.4, 8.8), (9.6, 9.0), (8.0, 7.6)], 8)),
            [blend('Pelvis', 'ThighL'), bone('ThighL'), blend('ThighL', 'ShinL')], smooth=55)
        m.loft(GEO_MAIN, 'knee', place([
            section((10.8, 12.9, 22.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), octagon(4.6, 5.2)),
            section((13.6, 12.9, 21.4), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), octagon(2.6, 3.2))]),
            bone('ShinL'), caps=('end',), smooth=40)
        m.loft(GEO_MAIN, 'boot', place(path_sections(
            [(4.0, 13.0, 23.0), (3.4, 13.6, 18.5), (2.0, 14.4, 13.0), (0.8, 15.0, 8.0)],
            [(7.6, 7.2), (9.2, 8.8), (7.8, 7.4), (8.0, 7.6)], 8)), bone('ShinL'), smooth=55)
        m.loft(GEO_MAIN, 'fur', place(path_sections(
            [(3.6, 13.5, 20.6), (3.2, 13.8, 16.2)], [(9.8, 9.4), (10.2, 9.8)], 10, shape=zigzag(1))),
            bone('ShinL'), smooth=60)
        foot = [(-5.4, 15.4, 6.0, 4.8, 4.6), (1.0, 15.8, 7.4, 6.0, 4.6), (9.0, 16.4, 7.6, 3.4, 3.6),
                (16.0, 17.0, 6.8, 2.8, 3.2), (21.5, 17.5, 4.2, 2.2, 3.0)]
        sections = []
        for x, yc, w, top, zc in foot:
            pts = [(0.0, top), (-0.65 * w, 0.8 * top), (-w, 0.1 * top), (-0.8 * w, -zc), (0.8 * w, -zc),
                   (w, 0.1 * top), (0.65 * w, 0.8 * top)]
            sections.append([(x, yc + a, zc + b) for a, b in pts])
        sections.append([(24.2, 17.6, 3.4)] * 7)
        m.loft(GEO_MAIN, 'foot', place(sections), bone('FootL'), caps=('start',), smooth=45)

        # -- shoulders: great angular pauldrons with spikes
        pauldron = [(13.0, -1.0, 74.5, 9.0, 9.0, 3.5, -2.5, 1.8), (19.5, -1.0, 74.5, 13.6, 13.6, 7.8, -5.0, 2.4),
                    (28.5, -1.5, 72.6, 14.8, 14.2, 8.6, -8.4, 2.4), (36.0, -2.0, 68.8, 12.8, 12.2, 6.2, -9.8, 2.4),
                    (41.0, -2.6, 64.6, 7.6, 7.2, 3.2, -7.4, 1.6)]
        sections = []
        for y, cx, cz, fx, bx, zt, zb, t in pauldron:
            outer = [(fx, zb), (fx * 0.85, zt * 0.55), (fx * 0.45, zt * 0.95), (0.0, zt), (-bx * 0.45, zt * 0.95),
                     (-bx * 0.85, zt * 0.55), (-bx, zb)]
            inner = [(-bx + t, zb + t * 0.5), (-(bx - t) * 0.8, (zt - t) * 0.6), (0.0, zt - t),
                     ((fx - t) * 0.8, (zt - t) * 0.6), (fx - t, zb + t * 0.5)]
            sections.append([(cx + a, y, cz + b) for a, b in outer + inner])
        m.loft(GEO_MAIN, 'pauldron', place(sections), bone('ShoulderL'), caps=('start', 'end'), smooth=42,
               us=[0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.68, 0.76, 0.84, 0.92, 0.97])
        spikes = (((-1.5, 28.5, 80.4), (-2.8, 33.4, 90.5), 2.6), ((6.0, 24.0, 79.2), (9.0, 27.6, 85.6), 1.6))
        for base, tip, size in spikes:
            mid = lerp(base, tip, 0.45)
            secs = path_sections([base, mid, tip], [(size, size), (size * 0.55, size * 0.55), (0.05, 0.05)], 4,
                                 phase=math.pi / 4)
            m.loft(GEO_MAIN, 'spike', place(secs), bone('ShoulderL'), smooth=30)

        # -- bare muscled arms, iron gauntlets, big fists
        m.loft(GEO_MAIN, 'arm', place(path_sections(
            [(-1.0, 25.0, 71.0), (-1.6, 29.0, 64.0), (-2.6, 32.4, 57.5), (-3.0, 33.8, 54.0)],
            [(8.0, 7.4), (8.8, 8.2), (7.2, 6.8), (6.6, 6.4)], 8)),
            [bone('ArmL'), bone('ArmL'), bone('ArmL'), blend('ArmL', 'ForeL')], smooth=55)
        m.loft(GEO_MAIN, 'fur', place(path_sections(
            [(-3.0, 34.0, 56.6), (-2.6, 34.6, 51.4)], [(8.2, 7.8), (8.8, 8.4)], 10, shape=zigzag(1))),
            bone('ForeL'), smooth=60)
        m.loft(GEO_MAIN, 'gauntlet', place(path_sections(
            [(-2.8, 34.4, 53.0), (-1.4, 36.2, 48.0), (0.6, 38.6, 42.0)], [(7.0, 6.6), (7.8, 7.4), (9.8, 9.2)], 8)),
            bone('ForeL'), smooth=45)
        fx, fy, fz = FIST
        m.loft(GEO_MAIN, 'hand', place(path_sections(
            [(0.8, 39.0, 42.5), (fx, fy, fz), (2.6, 40.2, 31.0)], [(5.8, 5.0), (7.4, 5.8), (6.0, 4.8)], 8)),
            bone('HandL'), caps=('end',), smooth=55)
        m.loft(GEO_MAIN, 'thumb', place(path_sections(
            [(6.6, 34.4, 39.0), (9.6, 35.6, 36.8), (10.6, 38.2, 35.2)], [(2.3, 2.3), (2.0, 2.0), (1.3, 1.3)], 5,
            hint=(0.0, 0.0, 1.0))), bone('HandL'), caps=('end',), smooth=60)

    # -- the round shield on the left forearm
    fore = B['ForeL']
    up = (0.0, 0.0, 1.0)
    across = cross(SHIELD_N, up)
    rings = [(0.0, -1.2), (15.6, -1.2), (17.4, -0.6), (17.4, 0.8), (15.8, 1.4), (13.2, 2.4), (5.2, 3.6), (3.6, 5.4),
             (0.0, 9.4)]
    sections = []
    for r, h in rings:
        sec = []
        for k in range(10):
            a = 2 * math.pi * k / 10
            rim = add(mul(across, r * math.cos(a)), mul(up, r * math.sin(a)))
            sec.append(add(add(SHIELD_C, mul(SHIELD_N, h)), rim))
        sections.append(sec)
    m.loft(GEO_MAIN, 'shield', sections, fore, vs=[0.0, 0.12, 0.2, 0.28, 0.36, 0.55, 0.8, 0.88, 1.0], smooth=35)

    # -- the warhammer: head down at the dwarf's right side
    hb = B['Hammer']
    grip = mirror(FIST)
    d = HAMMER_DIR
    head_c = add(grip, mul(d, HAMMER_HEAD))
    h = norm(sub(up, mul(d, dot(up, d))))          # along the hammer head, square to the handle
    s = cross(d, h)

    def along(c, axis, offsets_sizes, a_axis, b_axis):
        return [section(add(c, mul(axis, o)), a_axis, b_axis, octagon(sa, sb)) for o, sa, sb in offsets_sizes]
    m.loft(GEO_MAIN, 'handle', path_sections([add(grip, mul(d, -12.0)), head_c], [(1.9, 1.9), (1.9, 1.9)], 6,
                                             hint=h), hb, smooth=60)
    m.loft(GEO_MAIN, 'grip', path_sections([add(grip, mul(d, -11.0)), add(grip, mul(d, -5.5))],
                                           [(2.3, 2.3), (2.3, 2.3)], 6, hint=h), hb, smooth=60)
    m.loft(GEO_MAIN, 'gold', along(grip, d, [(-12.2, 2.8, 2.8), (-14.2, 2.0, 2.0)], h, s), hb,
           caps=('start', 'end'), smooth=40)
    m.loft(GEO_MAIN, 'hammer', along(head_c, h, [(-11.0, 4.6, 4.6), (-9.4, 5.6, 5.6), (9.4, 5.6, 5.6),
                                                 (11.0, 4.6, 4.6)], d, s), hb, caps=('start', 'end'), smooth=40)
    for o in (-7.0, 7.0):
        m.loft(GEO_MAIN, 'gold', along(head_c, h, [(o - 0.9, 6.1, 6.1), (o + 0.9, 6.1, 6.1)], d, s), hb, smooth=40)
    spike = [add(head_c, mul(h, 10.6)), add(head_c, mul(h, 14.5)), add(head_c, mul(h, 18.5))]
    m.loft(GEO_MAIN, 'spike', path_sections(spike, [(3.4, 3.4), (2.0, 2.0), (0.05, 0.05)], 4, hint=d,
                                            phase=math.pi / 4), hb, smooth=30)
    return m


# ---------------------------------------------------------------------------
# painting: flat colour, soft gradients, dark edges and bright highlights --
# the way the original unit skins were painted
# ---------------------------------------------------------------------------

def _clamp(x):
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def mix(a, b, t):
    t = _clamp(t)
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t)


def smooth(e0, e1, x):
    t = _clamp((x - e0) / (e1 - e0))
    return t * t * (3 - 2 * t)


def ramp(stops, x):
    if x <= stops[0][0]:
        return stops[0][1]
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if x <= p1:
            return mix(c0, c1, (x - p0) / (p1 - p0))
    return stops[-1][1]


def gauss(dx, dy, sx, sy):
    return math.exp(-(dx / sx) ** 2 - (dy / sy) ** 2)


SKIN = [(0.0, (30, 30, 58)), (0.3, (74, 78, 118)), (0.6, (122, 128, 166)), (0.85, (170, 176, 206)),
        (1.0, (226, 230, 244))]
HAIR = [(0.0, (10, 10, 18)), (0.35, (36, 37, 54)), (0.65, (80, 84, 108)), (0.85, (134, 140, 166)),
        (1.0, (196, 202, 222))]
LEATHER = [(0.0, (34, 20, 12)), (0.35, (78, 48, 27)), (0.65, (124, 82, 46)), (0.9, (170, 124, 76)),
           (1.0, (206, 168, 114))]
FUR = [(0.0, (52, 46, 44)), (0.4, (122, 114, 106)), (0.75, (198, 194, 186)), (1.0, (246, 244, 238))]
WOOD = [(0.0, (40, 22, 12)), (0.45, (92, 56, 30)), (0.8, (140, 94, 54)), (1.0, (178, 130, 80))]
# metal is painted as bands of light and dark, like a reflection
IRON = [(0.0, (206, 204, 212)), (0.18, (132, 128, 136)), (0.42, (42, 39, 44)), (0.58, (15, 14, 17)),
        (0.76, (84, 80, 86)), (0.9, (152, 148, 154)), (1.0, (72, 68, 74))]
GOLD = [(0.0, (255, 246, 196)), (0.2, (238, 196, 92)), (0.45, (164, 104, 30)), (0.6, (88, 50, 14)),
        (0.78, (196, 140, 50)), (0.9, (240, 206, 110)), (1.0, (150, 96, 30))]
FIRE = [(0.0, (110, 14, 4)), (0.4, (226, 70, 12)), (0.75, (255, 170, 40)), (1.0, (255, 244, 170))]
DARK = (12, 10, 14)


def team(shade):
    """Team colour, darkened by `shade` (0 = full colour, 1 = black)."""
    return (0, 0, 0, int(255 * _clamp(shade)))


def edge(v, width):
    """1 at the edges of a 0..1 range, falling to 0 over `width`."""
    return smooth(width, 0.0, min(v, 1.0 - v))


class Painter:
    """Each method paints one atlas region from its (u, v) in 0..1, and
    returns (r, g, b), or (r, g, b, a) where team colour shows through."""

    # -- head ----------------------------------------------------------------

    def head(self, u, v):
        a = head_angle(u)
        aa = abs(a)
        z = HEAD[0][0] + (HEAD[-1][0] - HEAD[0][0]) * v
        k = 0.56 + 0.12 * math.cos(math.radians(a)) + 0.12 * smooth(88, 99, z) - 0.12 * smooth(84, 76, z)
        k += 0.28 * gauss(z - 94.5, a, 2.2, 40)                     # shine on the bald crown
        k += 0.18 * gauss(a, z - 82.5, 6, 3.0)                      # nose
        k += 0.14 * gauss(aa - 45, z - 83.0, 12, 2.4)               # cheekbones
        k += 0.12 * gauss(aa - 22, z - 87.8, 16, 1.2)               # brow ridge
        k -= 0.4 * gauss(aa - 31, z - 85.3, 11, 1.7)                # sockets
        k -= 0.3 * gauss(aa - 8, z - 79.6, 3, 0.8)                  # nostrils
        for wz in (90.2, 91.8):                                     # furrowed forehead
            k -= 0.22 * gauss(z - wz - 0.012 * aa, 0, 0.35, 1) * smooth(42, 15, aa)
        k -= 0.25 * gauss(aa - 2.5, z - 87.4, 1.6, 1.4)             # frown
        c = ramp(SKIN, k)
        c = mix(c, (c[0] * 1.15 + 14, c[1] * 0.92, c[2] * 0.94), 0.55 * gauss(aa - 30, z - 81.5, 16, 2.5))
        c = mix(c, (255, 130, 40), 0.5 * gauss(aa - 31, z - 85.4, 9, 1.4))       # eye glow on the sockets
        hair = max(smooth(79.8, 78.0, z), smooth(66, 80, aa) * smooth(90, 87, z))
        return mix(c, (22, 22, 34), 0.9 * hair)

    def ear(self, u, v):
        return ramp(SKIN, 0.62 - 0.25 * gauss(u - 0.5, v - 0.5, 0.25, 0.25) - 0.1 * v)

    def eye(self, u, v):
        return ramp(FIRE, 1.0 - 1.6 * math.hypot(u - 0.5, (v - 0.5) * 0.8))

    def gem(self, u, v):
        return ramp(FIRE, 1.0 - 1.4 * math.hypot(u - 0.5, v - 0.5) + 0.1 * math.sin(u * 30))

    # -- hair ----------------------------------------------------------------

    def _hair(self, u, v, strands, k0):
        w = u * strands + 0.3 * math.sin(v * 6.0 + u * 4.0)
        lock = abs(math.sin(math.pi * w))
        k = k0 + 0.28 * (lock - 0.5) + 0.25 * smooth(0.7, 1.0, lock) * (0.5 + 0.5 * math.sin(v * 8 + u * 17))
        if lock < 0.14:
            k -= 0.18
        return ramp(HAIR, k)

    def beard(self, u, v):
        front = gauss(u - 0.5, 0, 0.3, 1)
        return self._hair(u, v, 13, 0.32 + 0.2 * front + 0.1 * smooth(0.3, 0.0, v) - 0.14 * smooth(0.6, 1.0, v))

    def moustache(self, u, v):
        return self._hair(u, v, 3, 0.52 - 0.15 * v)

    def topknot(self, u, v):
        return self._hair(u, v, 4, 0.46)

    def brow(self, u, v):
        return self._hair(u, v, 2, 0.34)

    # -- skin ----------------------------------------------------------------

    def arm(self, u, v):
        front = math.cos(2 * math.pi * (u - 0.5))
        k = 0.54 + 0.14 * front + 0.2 * gauss(u - 0.5, v - 0.4, 0.13, 0.22) + 0.1 * gauss(min(u, 1 - u), v - 0.3,
                                                                                           0.12, 0.2)
        k -= 0.25 * edge(v, 0.14)
        c = ramp(SKIN, k)
        zig = abs(((u * 8.0) % 1.0) - 0.5) * 2.0                   # clan tattoo round the arm
        if abs(v - 0.62 - 0.07 * zig) < 0.035 or abs(v - 0.52) < 0.014 or abs(v - 0.76) < 0.014:
            c = mix(c, (16, 18, 40), 0.85)
        return c

    def hand(self, u, v):
        front = math.cos(2 * math.pi * (u - 0.5))
        k = 0.56 + 0.15 * front - 0.12 * v
        if front > -0.2 and 0.38 < v < 0.95:
            for g in (0.52, 0.66, 0.8):                            # fingers curled round the haft
                k -= 0.3 * gauss(v - g, 0, 0.02, 1) * smooth(-0.2, 0.3, front)
            k += 0.14 * gauss(v - 0.42, 0, 0.05, 1)                # knuckles
        return ramp(SKIN, k)

    def thumb(self, u, v):
        c = ramp(SKIN, 0.6 + 0.12 * math.cos(2 * math.pi * (u - 0.5)))
        return mix(c, (178, 174, 190), 0.7) if v > 0.7 and abs(u - 0.5) < 0.2 else c

    # -- armour and clothing -------------------------------------------------

    def torso(self, u, v):
        front = math.cos(2 * math.pi * (u - 0.5))
        if v > 0.86:
            return ramp(GOLD, 0.2 + 2.5 * (v - 0.86))
        if v < 0.05:
            return ramp(IRON, 0.5)
        if front > 0.3:                                            # breastplate
            k = 0.62 - 0.35 * front + 0.15 * smooth(0.3, 0.8, v)
            if abs(u - 0.5) < 0.01:
                return ramp(GOLD, 0.25)
            if abs(v - 0.56 + 0.4 * abs(u - 0.5)) < 0.012:
                return ramp(GOLD, 0.3)
            return ramp(IRON, k)
        if abs(((v * 7.0) % 1.0) - 0.5) > 0.44:                    # lames on the back
            return DARK
        return ramp(IRON, 0.62 - 0.2 * front + 0.08 * ((v * 7.0) % 1.0))

    def pauldron(self, u, v):
        if u > 0.62:                                               # leather lining
            return ramp(LEATHER, 0.3 + 0.1 * v)
        if u < 0.06 or 0.54 < u < 0.62 or v > 0.88 or v < 0.07:    # gold trim
            return ramp(GOLD, 0.2 + 0.5 * abs(math.sin(u * 14 + v * 3)))
        if abs(u - 0.3) < 0.014:                                   # ridge
            return ramp(GOLD, 0.15)
        for ru in (0.1, 0.5):                                      # a few big rivets
            if math.hypot((u - ru) * 3.0, ((v * 4.0) % 1.0) - 0.5) < 0.16:
                return ramp(GOLD, 0.1)
        light = gauss(u - 0.24, 0, 0.07, 1) * (0.7 + 0.3 * v)
        if light > 0.45:
            return (255, 255, 255, int(255 * 0.5 * (light - 0.45)))
        return team(0.1 + 0.45 * smooth(0.2, 0.5, abs(u - 0.3)) + 0.15 * v)

    def shield(self, u, v):
        if v < 0.17:                                               # planks on the back
            p = (u * 6.0) % 1.0
            return ramp(WOOD, 0.5 - 0.3 * edge(p, 0.1))
        if v < 0.38:                                               # iron rim with gold edge
            if abs(v - 0.34) < 0.025:
                return ramp(GOLD, 0.2)
            return ramp(IRON, 0.2 + 2.0 * (v - 0.17))
        if v > 0.78:                                               # boss and spike
            return ramp(IRON, 0.15 + 0.6 * (v - 0.78) / 0.22)
        # team coloured field with flames licking out from the boss
        t = (v - 0.38) / 0.4                                       # 0 at the rim, 1 at the boss
        a = (u * 10.0) % 1.0 - 0.5
        width = 0.45 * smooth(0.2, 0.95, t)
        if abs(a) < width:
            heat = 1.0 - abs(a) / max(width, 1e-6)
            return DARK if heat < 0.2 else ramp(FIRE, 0.3 + 0.7 * heat * t)
        return team(0.15 + 0.5 * smooth(0.5, 0.0, t))

    def gauntlet(self, u, v):
        front = math.cos(2 * math.pi * (u - 0.5))
        if v < 0.1 or v > 0.86:
            return ramp(GOLD, 0.15 + 2.0 * min(v, 1 - v))
        if 0.44 < v < 0.56:
            return team(0.2 + 0.3 * (1 - front) / 2)
        if abs(v - 0.4) < 0.02 or abs(v - 0.6) < 0.02:
            return ramp(GOLD, 0.3)
        return ramp(IRON, 0.62 - 0.32 * front + 0.1 * v)

    def belt(self, u, v):
        cell = (u * 14.0) % 1.0
        if 0.2 < cell < 0.8 and 0.2 < v < 0.8:
            return ramp(GOLD, 0.15 + 0.5 * abs(v - 0.35))
        return ramp(LEATHER, 0.45 - 0.25 * edge(v, 0.15))

    def buckle(self, u, v):
        return ramp(GOLD, 0.1 + 0.7 * v)

    def cloth(self, u, v):
        x, y = (u - 0.5) * 2, v
        if min(u, 1 - u) < 0.1 or y > 0.92:
            return ramp(GOLD, 0.2 + 2 * min(u, 1 - u, 1 - y))
        anvil = ((abs(x) < 0.55 and abs(y - 0.3) < 0.07) or (abs(x) < 0.18 and 0.3 < y < 0.55)
                 or (abs(x) < 0.42 and abs(y - 0.6) < 0.06)
                 or (0.55 <= x < 0.8 and abs(y - 0.3) < 0.07 * (0.8 - x) / 0.25))
        if anvil:
            return DARK
        return team(0.1 + 0.4 * y)

    def backcloth(self, u, v):
        return ramp(LEATHER, 0.5 - 0.15 * v - 0.3 * edge(u, 0.08))

    def tasset(self, u, v):
        if min(u, 1 - u) < 0.12 or v > 0.88:
            return ramp(GOLD, 0.2 + 2 * min(u, 1 - u, 1 - v))
        if abs(u - 0.5) < 0.1:
            return team(0.25 + 0.3 * v)
        return ramp(IRON, 0.25 + 0.4 * v)

    def hips(self, u, v):
        return ramp(LEATHER, 0.45 + 0.12 * math.cos(2 * math.pi * (u - 0.5)) - 0.2 * v)

    def thigh(self, u, v):
        k = 0.5 + 0.15 * math.cos(2 * math.pi * (u - 0.5)) - 0.1 * v
        k -= 0.2 * max(0.0, math.sin(u * math.pi * 8 + v * 2.0)) ** 8
        return ramp(LEATHER, k)

    def knee(self, u, v):
        return ramp(GOLD, 0.3) if v < 0.12 else ramp(IRON, 0.15 + 0.6 * v)

    def boot(self, u, v):
        front = math.cos(2 * math.pi * (u - 0.5))
        c = ramp(LEATHER, 0.52 + 0.15 * front - 0.12 * v)
        if 0.4 < v < 0.56:                                         # green and gold trim
            y = (v - 0.4) / 0.16
            zig = abs(((u * 10.0) % 1.0) - 0.5) * 2.0
            if y < 0.15 or y > 0.85:
                return ramp(GOLD, 0.4)
            if abs(abs(y - 0.5) - 0.35 * zig) < 0.09:
                return ramp(GOLD, 0.15)
            return mix((72, 130, 46), (26, 50, 18), abs(y - 0.5))
        return c

    def foot(self, u, v):
        if v > 0.62:                                               # iron toe cap
            return ramp(GOLD, 0.3) if v < 0.66 else ramp(IRON, 0.3 + 0.4 * (v - 0.66))
        return ramp(LEATHER, 0.55 - 0.2 * v)

    def fur(self, u, v):
        stripe = math.sin(u * math.pi * 16 + 0.8 * math.sin(v * 7))
        k = 0.66 + 0.2 * stripe - 0.3 * v + 0.08 * math.sin(u * 110 + v * 9)
        return ramp(FUR, k) if stripe > -0.5 else ramp(LEATHER, 0.28)

    # -- the hammer and odd bits of metal ------------------------------------

    def hammer(self, u, v):
        cheek = min(abs(u - 0.25), abs(u - 0.75))
        if cheek < 0.09 and 0.2 < v < 0.8:                         # runes glowing like embers
            x, y = cheek / 0.09, (v - 0.5) / 0.3
            if min(abs(x - abs(y)), abs(abs(y) - 0.5) + (0.0 if x < 0.7 else 1.0)) < 0.13:
                return ramp(FIRE, 0.9 - 0.3 * abs(y))
        return ramp(IRON, 0.62 - 0.4 * math.cos(math.pi * (2 * u - 0.5)) ** 2 + 0.15 * edge(v, 0.12))

    def handle(self, u, v):
        return ramp(WOOD, 0.5 + 0.2 * math.sin(u * 4 * math.pi) * (0.6 + 0.4 * math.sin(v * 25)))

    def grip(self, u, v):
        return ramp(LEATHER, 0.55 if (u + v * 3.0) % 1.0 < 0.8 else 0.2)

    def gold(self, u, v):
        return ramp(GOLD, 0.1 + 0.8 * abs(math.sin(math.pi * (u + 0.25))))

    def iron(self, u, v):
        return ramp(IRON, 0.15 + 0.7 * v)

    def spike(self, u, v):
        return ramp(IRON, 0.1 + 0.8 * abs(math.sin(math.pi * 2 * u)))


LIGHT = norm((0.3, 0.0, 1.0))


def light_map(model):
    """Shading per texel, painted from the model: dark in the crevices and
    underneath, light on top."""
    geosets = model['geosets']
    ao = bake.vertex_occlusion(geosets, cell=1.2, rays=16, reach=12.0)[GEO_MAIN]
    g = geosets[GEO_MAIN]
    values = []
    for k, n in zip(ao, g['normals']):
        top = max(0.0, dot(n, LIGHT))
        values.append((0.5 + 0.5 * k ** 1.5) * (0.82 + 0.3 * top))
    return bake.bake(g, values, TEX, [r for name, r in sorted(REGIONS.items()) if name not in SHARED])


def paint_texture(model=None):
    """The 256 x 256 RGBA skin, with the model's shading painted in."""
    if model is None:
        model = build_model()
    light = light_map(model)
    painter = Painter()
    pixels = [(0, 0, 0, 255)] * (TEX * TEX)
    for name, (x0, y0, x1, y1) in REGIONS.items():
        fn = getattr(painter, name)
        baked = name not in SHARED
        w, h = x1 - x0, y1 - y0
        for py in range(y0, y1):
            v = _clamp((py + 0.5 - y0 - 1.0) / (h - 2))
            row = py * TEX
            for px in range(x0, x1):
                u = _clamp((px + 0.5 - x0 - 1.0) / (w - 2))
                c = fn(u, v)
                k = light[row + px] if baked else None
                if len(c) == 4:
                    r, g, b, a = c
                    if k is not None and k < 1.0:
                        # darken the team colour too: blend more black over it
                        a0 = a / 255.0
                        a1 = 1.0 - (1.0 - a0) * k
                        f = a0 * k / a1 if a1 > 0 else 0.0
                        r, g, b, a = r * f, g * f, b * f, a1 * 255.0
                    pixels[row + px] = (int(min(255, max(0, r))), int(min(255, max(0, g))),
                                        int(min(255, max(0, b))), int(min(255, max(0, a))))
                else:
                    if k is not None:
                        c = (c[0] * k, c[1] * k, c[2] * k)
                    pixels[row + px] = (int(min(255, max(0, c[0]))), int(min(255, max(0, c[1]))),
                                        int(min(255, max(0, c[2]))), 255)
    return pixels


# ---------------------------------------------------------------------------
# animation
# ---------------------------------------------------------------------------

def _rot(pitch=0.0, roll=0.0, yaw=0.0):
    return quat_euler(roll=roll, pitch=pitch, yaw=yaw)


def pose(**bones):
    """pose(ThighL=(pitch, roll, yaw), Root=dict(trans=(x, y, z))...)"""
    out = {}
    for name, value in bones.items():
        if isinstance(value, dict):
            out[name] = value
        else:
            pitch, roll, yaw = (tuple(value) + (0.0, 0.0, 0.0))[:3]
            out[name] = {'rot': _rot(pitch, roll, yaw)}
    return out


def _with(base, **changes):
    out = dict(base)
    out.update(pose(**changes))
    return out


def stride(lead, push):
    """A walking pose: the `lead` leg reaching forward, the other pushing off."""
    l, p = lead[-1], push[-1]
    return pose(**{'Thigh' + l: (-28,), 'Shin' + l: (10,), 'Foot' + l: (12,),
                   'Thigh' + p: (22,), 'Shin' + p: (28,), 'Foot' + p: (-20,),
                   'Arm' + l: (14,), 'Arm' + p: (-14,), 'Chest': (2, 0, -6 if l == 'L' else 6)})


def passing(lift):
    other = 'R' if lift == 'L' else 'L'
    return pose(**{'Thigh' + lift: (-14,), 'Shin' + lift: (46,), 'Foot' + lift: (-10,),
                   'Thigh' + other: (2,), 'Shin' + other: (4,), 'Chest': (3,),
                   'Root': {'trans': (0.0, 0.0, 2.0)}})


READY = pose(Root={'trans': (0.0, 0.0, -4.0)}, Chest=(10,), Head=(-8,),
             ThighL=(-16,), ShinL=(26,), FootL=(-10,), ThighR=(-6,), ShinR=(22,), FootR=(-16,),
             ArmR=(-35,), ForeR=(-50,), Hammer=(-40,), ArmL=(-30, 8), ForeL=(-40,))

RAISED = pose(ArmR=(165,), ForeR=(0,), Hammer=(54,), Chest=(-8,), Head=(-15,), ArmL=(-45, 20), ForeL=(-30,))

DEATH = pose(Root={'rot': _rot(-82), 'trans': (6.0, 0.0, -25.0)}, Chest=(-6,), Head=(-20, 0, 25),
             ArmL=(-10, 50), ArmR=(-20, -50), ForeR=(-20,), Hammer=(60,),
             ThighL=(60, 6), ShinL=(-20,), ThighR=(48, -6), ShinR=(-10,))

# name, length (ms), looping, move speed, rarity, keyframes [(time, pose)]
SEQUENCES = [
    ('Stand - 1', 3000, True, 0, 0, [
        (0, {}),
        (1500, pose(Chest={'rot': _rot(2), 'scale': (1.0, 1.02, 1.02)}, Head=(-3,), ShoulderL=(0, 3),
                    ShoulderR=(0, -3), ArmL=(0, 3), ArmR=(0, -3))),
        (3000, {}),
    ]),
    ('Stand - 2', 3000, True, 0, 0.3, [
        (0, {}),
        (900, pose(Head=(0, 0, 28), Chest=(0, 0, 6))),
        (1500, pose(Head=(-5, 0, 28), Chest=(0, 0, 6), ArmR=(-15,), ForeR=(-25,))),
        (2300, pose(Head=(0, 0, -22), Chest=(0, 0, -4))),
        (3000, {}),
    ]),
    ('Stand Ready', 1000, True, 0, 0, [
        (0, READY),
        (500, _with(READY, Root={'trans': (0.0, 0.0, -5.0)}, Chest=(13,))),
        (1000, READY),
    ]),
    ('Walk', 1000, True, 220, 0, [
        (0, stride('L', 'R')),
        (250, passing('R')),
        (500, stride('R', 'L')),
        (750, passing('L')),
        (1000, stride('L', 'R')),
    ]),
    ('Attack - 1', 1000, True, 0, 0, [
        # an overhead smash
        (0, {}),
        (250, pose(Chest=(-12, 0, -12), ArmR=(150, -10), ForeR=(-40,), Hammer=(20,), ArmL=(-25,),
                   ThighL=(-14,), ShinL=(18,), ThighR=(8,), ShinR=(10,))),
        (400, pose(Root={'trans': (3.0, 0.0, -4.0)}, Chest=(24, 0, 8), ArmR=(-80,), ForeR=(-20,), Hammer=(45,),
                   ArmL=(-15, 12), ThighL=(-22,), ShinL=(30,), FootL=(-8,), ThighR=(10,), ShinR=(18,))),
        (650, pose(Root={'trans': (2.0, 0.0, -3.0)}, Chest=(14,), ArmR=(-60,), ForeR=(-15,), Hammer=(35,),
                   ThighL=(-16,), ShinL=(22,), ThighR=(8,), ShinR=(12,))),
        (1000, {}),
    ]),
    ('Attack - 2', 1000, True, 0, 0, [
        # a sweeping blow from the right
        (0, {}),
        (250, pose(Chest=(0, 0, -45), ArmR=(-20, -65), ForeR=(-30,), Hammer=(-30,), ArmL=(-30,),
                   ThighL=(-12,), ShinL=(14,))),
        (420, pose(Chest=(8, 0, 40), ArmR=(-85, -25), ForeR=(-10,), Hammer=(30,), ArmL=(-10,),
                   ThighL=(-14,), ShinL=(18,), ThighR=(8,))),
        (650, pose(Chest=(5, 0, 25), ArmR=(-55, -15), Hammer=(10,), ThighL=(-8,), ShinL=(10,))),
        (1000, {}),
    ]),
    ('Spell', 1000, True, 0, 0, [
        (0, {}),
        (300, RAISED),
        (700, RAISED),
        (1000, {}),
    ]),
    ('Spell Throw', 800, True, 0, 0, [
        (0, {}),
        (260, pose(Chest=(-12, 0, -20), ArmR=(150,), ForeR=(-40,), Hammer=(20,), ArmL=(-35,))),
        (400, pose(Chest=(18, 0, 15), ArmR=(-100,), ForeR=(0,), Hammer=(60,), ArmL=(15,),
                   ThighL=(-16,), ShinL=(20,))),
        (800, {}),
    ]),
    ('Spell Slam', 1000, True, 0, 0, [
        (0, {}),
        (300, pose(Root={'trans': (0.0, 0.0, 22.0)}, Chest=(-10,), ArmR=(160,), ForeR=(-20,), Hammer=(40,),
                   ArmL=(-40, 20), ThighL=(-40,), ShinL=(60,), ThighR=(-36,), ShinR=(56,))),
        (450, pose(Root={'trans': (4.0, 0.0, -8.0)}, Chest=(30,), ArmR=(-70,), ForeR=(-15,), Hammer=(50,),
                   ArmL=(-30, 10), ThighL=(-30,), ShinL=(50,), FootL=(-20,), ThighR=(-20,), ShinR=(44,),
                   FootR=(-24,))),
        (700, pose(Root={'trans': (2.0, 0.0, -5.0)}, Chest=(20,), ArmR=(-50,), ForeR=(-10,), Hammer=(40,),
                   ThighL=(-20,), ShinL=(34,), FootL=(-14,), ThighR=(-12,), ShinR=(28,), FootR=(-16,))),
        (1000, {}),
    ]),
    ('Death', 2000, False, 0, 0, [
        (0, {}),
        (300, pose(Chest=(-18,), Head=(-25,), ArmL=(0, 30), ArmR=(0, -30), ThighL=(-10,), ShinL=(30,))),
        (550, pose(Root={'rot': _rot(-30), 'trans': (0.0, 0.0, -10.0)}, Chest=(-10,), ArmL=(0, 45), ArmR=(0, -45),
                   ThighL=(30,), ShinL=(20,), ThighR=(25,), ShinR=(20,))),
        (900, DEATH),
        (1050, _with(DEATH, Root={'rot': _rot(-78), 'trans': (6.0, 0.0, -22.0)})),
        (1250, DEATH),
        (2000, DEATH),
    ]),
    ('Decay Flesh', 2000, False, 0, 0, [
        (0, DEATH),
        (2000, _with(DEATH, Root={'rot': _rot(-82), 'trans': (6.0, 0.0, -45.0)})),
    ]),
    ('Decay Bone', 2000, False, 0, 0, [
        (0, _with(DEATH, Root={'rot': _rot(-82), 'trans': (6.0, 0.0, -45.0)})),
        (2000, _with(DEATH, Root={'rot': _rot(-82), 'trans': (6.0, 0.0, -70.0)})),
    ]),
    ('Stand Victory', 2000, True, 0, 0, [
        (0, {}),
        (400, RAISED),
        (800, _with(RAISED, Root={'trans': (0.0, 0.0, 3.0)}, ArmR=(155,))),
        (1200, RAISED),
        (1600, _with(RAISED, Root={'trans': (0.0, 0.0, 3.0)}, ArmR=(155,))),
        (2000, {}),
    ]),
    ('Portrait', 3000, True, 0, 0, [
        (0, {}),
        (1500, pose(Head=(-3, 0, 4), Chest={'scale': (1.0, 1.02, 1.02)})),
        (3000, {}),
    ]),
    ('Portrait Talk', 1500, True, 0, 0, [
        (0, {}),
        (300, pose(Head=(6,))),
        (600, pose(Head=(-4, 0, 5))),
        (900, pose(Head=(5, 0, -4))),
        (1200, pose(Head=(-3,))),
        (1500, {}),
    ]),
]

IDENTITY = (0.0, 0.0, 0.0, 1.0)


def build_animation():
    sequences = []
    tracks = {name: {'rot': [], 'trans': [], 'scale': []} for name, _, _ in BONES}
    start = 0
    for name, length, looping, speed, rarity, keys in SEQUENCES:
        start += 100
        end = start + length
        sequences.append({'name': name, 'start': start, 'end': end, 'looping': looping,
                          'move_speed': float(speed), 'rarity': float(rarity)})
        for bone, _, _ in BONES:
            for t, frame_pose in keys:
                p = frame_pose.get(bone, {})
                tracks[bone]['rot'].append((start + t, p.get('rot', IDENTITY)))
                tracks[bone]['trans'].append((start + t, p.get('trans', (0.0, 0.0, 0.0))))
                tracks[bone]['scale'].append((start + t, p.get('scale', (1.0, 1.0, 1.0))))
        start = end
    return sequences, tracks


def sequence_frame(model, name, fraction=0.0):
    for s in model['sequences']:
        if s['name'] == name:
            return int(s['start'] + (s['end'] - s['start']) * fraction)
    raise KeyError(name)


# ---------------------------------------------------------------------------
# assembly
# ---------------------------------------------------------------------------

def build_model():
    mesh = build_mesh()
    sequences, tracks = build_animation()
    bones = []
    for name, parent, pivot in BONES:
        t = tracks[name]
        bone = {'name': name, 'parent': parent, 'pivot': pivot}
        if any(tuple(v) != IDENTITY for _, v in t['rot']):
            bone['rotation'] = t['rot']
        if any(tuple(v) != (0.0, 0.0, 0.0) for _, v in t['trans']):
            bone['translation'] = t['trans']
        if any(tuple(v) != (1.0, 1.0, 1.0) for _, v in t['scale']):
            bone['scaling'] = t['scale']
        bones.append(bone)
    grip_r, grip_l = mirror(FIST), FIST
    hammer_head = add(grip_r, mul(HAMMER_DIR, HAMMER_HEAD))
    return {
        'name': 'DarkIronThane',
        'sequences': sequences,
        'textures': [{'replaceable': 1}, {'path': TEXTURE_PATH}],
        'materials': [
            # the classic unit setup: team colour, with the painted texture blended on top
            {'layers': [{'texture': 0}, {'texture': 1, 'filter': mdx.FILTER_BLEND}]},
            {'layers': [{'texture': 1, 'shading': mdx.SHADE_UNSHADED | mdx.SHADE_UNFOGGED}]},
        ],
        'geosets': [dict(mesh.geosets[GEO_MAIN], material=0), dict(mesh.geosets[GEO_GLOW], material=1)],
        'bones': bones,
        'attachments': [
            {'name': 'Origin Ref', 'parent': -1, 'pivot': (0.0, 0.0, 0.0)},
            {'name': 'Chest Ref', 'parent': B['Chest'], 'pivot': (16.0, 0.0, 62.0)},
            {'name': 'Head Ref', 'parent': B['Head'], 'pivot': (4.0, 0.0, 98.0)},
            {'name': 'Overhead Ref', 'parent': -1, 'pivot': (0.0, 0.0, 124.0)},
            {'name': 'Hand Right Ref', 'parent': B['HandR'], 'pivot': grip_r},
            {'name': 'Hand Left Ref', 'parent': B['HandL'], 'pivot': grip_l},
            {'name': 'Weapon Ref', 'parent': B['Hammer'], 'pivot': hammer_head},
            {'name': 'Foot Left Ref', 'parent': B['FootL'], 'pivot': (8.0, 16.4, 1.0)},
            {'name': 'Foot Right Ref', 'parent': B['FootR'], 'pivot': (8.0, -16.4, 1.0)},
        ],
        'collision': [
            {'name': 'Collision Sphere01', 'parent': B['Root'], 'pivot': (0.0, 0.0, 52.0),
             'center': (0.0, 0.0, 52.0), 'radius': 48.0},
        ],
        'cameras': [
            {'name': 'Portrait', 'position': (84.0, -28.0, 96.0), 'target': (6.0, 0.0, 84.0),
             'fov': 0.6, 'far': 1000.0, 'near': 8.0},
        ],
    }


def build():
    """Returns ({archive path: bytes}, model, texture, icon)."""
    from . import raster
    model = build_model()
    texture = paint_texture(model)
    icon = raster.hero_icon(model, texture, TEX, frame=sequence_frame(model, 'Portrait'), **ICON_CAMERA)
    disabled = raster.disabled_icon(icon)
    return {
        MODEL_PATH: mdx.write(model),
        TEXTURE_PATH: image.blp1(texture, TEX, TEX),
        ICON_PATH: image.blp1(icon, 64, 64, mipmaps=False),
        DISICON_PATH: image.blp1(disabled, 64, 64, mipmaps=False),
    }, model, texture, icon

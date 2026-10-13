"""The Dark Iron Thane: the hero's model, assembled from the reference models
in this repository the way Hive Workshop modellers make theirs.

The base is "King" by Tranquil (King.zip): its body, arms, pauldrons, cape,
bearded head, skeleton and animations, all textured with the game's own
skins. On top of that:
- dwarf proportions: the legs and cape shortened, the body widened
- the crown taken off and the beard grown down over the chest
- everything tinted through geoset colours: dark iron armour, dark slate
  skin, a near black beard and moustache
- glowing red eyes, a topknot, and a warhammer in place of the sword, painted on
  a small texture of their own
The King's portrait model gets the same head.
"""

import math
import os
import zipfile
from collections import defaultdict

from . import image, mdxedit
from .lowpoly import Builder, add, cross, dot, frame, mul, norm, section, sub

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KING_ZIP = os.path.join(ROOT, 'King.zip')

MODEL_PATH = 'war3mapImported\\DarkIronThane.mdx'
PORTRAIT_PATH = 'war3mapImported\\DarkIronThane_Portrait.mdx'   # the game finds it by this name
TEXTURE_PATH = 'war3mapImported\\DarkIronThane.blp'
ICON_PATH = 'ReplaceableTextures\\CommandButtons\\BTNHeroMountainKing.blp'

# the King's geosets
BODY, ARMS, SWORD_GLOW, HERO_GLOW, SWORD, HEAD, ARMOUR, CAPE, TASSETS = range(9)
KING_TEXTURES = {BODY: 'Textures\\Arthas.blp', SWORD: 'UI\\Glues\\MainMenu\\MainMenu3d\\SwordBladeGoldTrim.blp',
                 HEAD: 'Units\\Human\\HeroPaladinBoss2\\HeropaladinBoss2.blp'}
# the portrait's geosets
P_ARMOUR, P_HEAD = 0, 1

# colours multiplied over the game's skins (red, green, blue)
ARMOUR_TINT = (0.48, 0.42, 0.44)       # dark iron
SKIN_TINT = (0.30, 0.36, 0.56)         # dark slate
HAIR_TINT = (0.22, 0.22, 0.30)         # near black
CAPE_TINT = (0.85, 0.85, 0.85)

# dwarf proportions: legs (below the King's hips) shortened, everything widened
HIP_Z = 68.1
LEG_SCALE = 0.62
DROP = HIP_Z * (1.0 - LEG_SCALE)
WIDEN = (1.08, 1.12)
WALK_SPEED = 170.0

# the beard grows down from the line of the mouth
BEARD_TOP = 111.2
BEARD_BONES = {'Portrait__Beard01', 'Portrait__MoustachL01', 'Portrait__MoustachR01', 'Portrait__MoustacheM01'}

TEX = 128
REGIONS = {
    'hammer': (0, 0, 64, 64),
    'gold': (64, 0, 96, 32),
    'spike': (96, 0, 128, 32),
    'handle': (64, 32, 80, 96),
    'grip': (80, 32, 96, 96),
    'hair': (96, 32, 128, 96),
    'eye': (0, 64, 32, 96),
}


def atlas(region, u, v):
    x0, y0, x1, y1 = REGIONS[region]
    u = min(1.0, max(0.0, u))
    v = min(1.0, max(0.0, v))
    return ((x0 + 1.0 + u * (x1 - x0 - 2)) / TEX, (y0 + 1.0 + v * (y1 - y0 - 2)) / TEX)


def read_reference(member):
    with zipfile.ZipFile(KING_ZIP) as z:
        return z.read(member)


# ---------------------------------------------------------------------------
# geometry helpers
# ---------------------------------------------------------------------------

def extent(points):
    if not points:
        return (0.0,) * 7
    lo = [min(p[k] for p in points) for k in range(3)]
    hi = [max(p[k] for p in points) for k in range(3)]
    radius = math.sqrt(sum((hi[k] - lo[k]) ** 2 for k in range(3))) / 2
    return (radius, *lo, *hi)


def principal_axes(points):
    """The two main directions of a cloud of points (power iteration)."""
    c = [sum(p[k] for p in points) / len(points) for k in range(3)]
    cov = [[sum((p[i] - c[i]) * (p[j] - c[j]) for p in points) for j in range(3)] for i in range(3)]

    def dominant(m, start):
        v = start
        for _ in range(100):
            v = norm(tuple(sum(m[i][j] * v[j] for j in range(3)) for i in range(3)))
        return v
    a = dominant(cov, (1.0, 0.2, 0.1))
    lam = sum(a[i] * sum(cov[i][j] * a[j] for j in range(3)) for i in range(3))
    deflated = [[cov[i][j] - lam * a[i] * a[j] for j in range(3)] for i in range(3)]
    b = dominant(deflated, (0.1, 0.2, 1.0))
    return tuple(c), a, b


def ray_hit(geoset, origin, direction):
    """The nearest point where a ray leaves through the mesh (or None)."""
    best = None
    v = geoset.vertices
    for ia, ib, ic in geoset.faces:
        a, b, c = v[ia], v[ib], v[ic]
        e1, e2 = sub(b, a), sub(c, a)
        p = cross(direction, e2)
        det = dot(e1, p)
        if abs(det) < 1e-9:
            continue
        t0 = sub(origin, a)
        u = dot(t0, p) / det
        q = cross(t0, e1)
        w = dot(direction, q) / det
        t = dot(e2, q) / det
        if u >= 0 and w >= 0 and u + w <= 1 and t > 0 and (best is None or t < best):
            best = t
    return add(origin, mul(direction, best)) if best is not None else None


def to_geoset(built, material):
    """A geoset from lowpoly.Builder data."""
    g = mdxedit.Geoset()
    g.vertices, g.normals, g.uvs = list(built['vertices']), list(built['normals']), list(built['uvs'])
    g.faces = list(built['triangles'])
    index = {}
    for b in built['bones']:
        key = tuple(b)
        if key not in index:
            index[key] = len(g.groups)
            g.groups.append(list(key))
        g.vertex_groups.append(index[key])
    g.material = material
    return g


def compact(g):
    """Drops vertices no face uses."""
    used = sorted({i for f in g.faces for i in f})
    remap = {old: new for new, old in enumerate(used)}
    g.vertices = [g.vertices[i] for i in used]
    g.normals = [g.normals[i] for i in used]
    g.uvs = [g.uvs[i] for i in used]
    g.vertex_groups = [g.vertex_groups[i] for i in used]
    g.extra_uv_sets = [[s[i] for i in used] for s in g.extra_uv_sets]
    g.faces = [tuple(remap[i] for i in f) for f in g.faces]


def split(g, keep):
    """Moves the faces whose corners all pass keep(vertex) into a new geoset
    (same material and bones)."""
    moved = [f for f in g.faces if all(keep(i) for i in f)]
    rest = [f for f in g.faces if not all(keep(i) for i in f)]
    new = mdxedit.Geoset()
    new.vertices, new.normals, new.uvs = list(g.vertices), list(g.normals), list(g.uvs)
    new.vertex_groups, new.groups = list(g.vertex_groups), [list(x) for x in g.groups]
    new.material, new.faces = g.material, moved
    g.faces = rest
    compact(g)
    compact(new)
    return new


def drop_faces(g, gone):
    g.faces = [f for f in g.faces if not all(gone(i) for i in f)]
    compact(g)


class HeadMap:
    """Ties the King's head to the portrait's copy of it (the same mesh,
    scaled and moved, with vertices in another order): the portrait's
    facial bones say which vertices are beard, and where the eyes are."""

    def __init__(self, main, portrait, portrait_model):
        names = {e.node.object_id: e.node.name for _, e in portrait_model.all_nodes()}
        by_uv = defaultdict(list)
        for j, uv in enumerate(portrait.uvs):
            by_uv[(round(uv[0], 4), round(uv[1], 4))].append(j)
        unique = [(i, by_uv[key][0]) for i, uv in enumerate(main.uvs)
                  for key in [(round(uv[0], 4), round(uv[1], 4))] if len(by_uv[key]) == 1]
        n = len(unique)
        self.mk = [sum(main.vertices[i][k] for i, _ in unique) / n for k in range(3)]
        self.mp = [sum(portrait.vertices[j][k] for _, j in unique) / n for k in range(3)]
        num = sum((main.vertices[i][k] - self.mk[k]) * (portrait.vertices[j][k] - self.mp[k])
                  for i, j in unique for k in range(3))
        den = sum((main.vertices[i][k] - self.mk[k]) ** 2 for i, _ in unique for k in range(3))
        self.scale = num / den
        self.bones = []
        for i, uv in enumerate(main.uvs):
            candidates = by_uv[(round(uv[0], 4), round(uv[1], 4))]
            target = self.to_portrait(main.vertices[i])
            j = min(candidates, key=lambda c: sum((portrait.vertices[c][k] - target[k]) ** 2 for k in range(3)))
            self.bones.append({names[b] for b in portrait.bones_of(j)})
        self.portrait_names = names

    def to_portrait(self, p):
        return tuple(self.mp[k] + (p[k] - self.mk[k]) * self.scale for k in range(3))

    def to_main(self, q):
        return tuple(self.mk[k] + (q[k] - self.mp[k]) / self.scale for k in range(3))

    def is_hair(self, i):
        return bool(self.bones[i] & BEARD_BONES)


def grow_beard(p):
    """Beard below the mouth grows down (and a little forward and wider)."""
    x, y, z = p
    d = BEARD_TOP - z
    if d <= 0:
        return p
    return (x + 0.3 * d, y * (1.0 + 0.03 * d), BEARD_TOP - 2.4 * d)


def tint(model, geoset, rgb, alpha=1.0):
    """A static geoset colour. (Static colours are stored red, green, blue;
    only animated ones are stored the other way round.)"""
    for a in model.geoset_animations:
        if a.geoset == geoset:
            a.color, a.alpha, a.flags = tuple(rgb), alpha, a.flags | 2
            return a
    a = mdxedit.GeosetAnimation(geoset, alpha, tuple(rgb), 2)
    model.geoset_animations.append(a)
    return a


# ---------------------------------------------------------------------------
# the added pieces: hammer, topknot, eyes
# ---------------------------------------------------------------------------

def octagon(ha, hb, c=0.6):
    return [(-ha, -c * hb), (-c * ha, -hb), (c * ha, -hb), (ha, -c * hb), (ha, c * hb), (c * ha, hb),
            (-c * ha, hb), (-ha, c * hb)]


def path_sections(path, radii, count, hint=(1.0, 0.0, 0.0), phase=0.0):
    out = []
    for i, (c, (ra, rb)) in enumerate(zip(path, radii)):
        d = sub(path[min(i + 1, len(path) - 1)], path[max(i - 1, 0)])
        ax, ay = frame(d, hint)
        out.append([add(c, add(mul(ax, ra * math.cos(math.pi + phase + 2 * math.pi * k / count)),
                               mul(ay, rb * math.sin(math.pi + phase + 2 * math.pi * k / count))))
                    for k in range(count)])
    return out


def build_hammer(sword_points, bone):
    """A warhammer along the King's sword: the handle where the blade was,
    the head square across it, in the plane the blade cuts in."""
    m = Builder(1, atlas)
    centre, a, h = principal_axes(sword_points)
    if a[0] < 0:
        a = mul(a, -1.0)
    grip = min(sword_points, key=lambda p: dot(p, a))
    grip = add(grip, mul(a, 14.0))                  # past the pommel, in the fist
    s = cross(a, h)
    head = add(grip, mul(a, 40.0))

    def along(c, axis, rows, ax, ay):
        return [section(add(c, mul(axis, o)), ax, ay, octagon(sa, sb)) for o, sa, sb in rows]
    m.loft(0, 'handle', path_sections([add(grip, mul(a, -13.0)), head], [(2.3, 2.3), (2.3, 2.3)], 6, hint=h),
           bone, smooth=60)
    m.loft(0, 'grip', path_sections([add(grip, mul(a, -6.0)), add(grip, mul(a, 6.0))], [(2.8, 2.8), (2.8, 2.8)], 6,
                                    hint=h), bone, smooth=60)
    m.loft(0, 'gold', along(grip, a, [(-13.4, 3.4, 3.4), (-16.0, 2.2, 2.2)], h, s), bone, caps=('start', 'end'),
           smooth=40)
    m.loft(0, 'hammer', along(head, h, [(-13.0, 6.2, 6.2), (-11.0, 7.4, 7.4), (11.0, 7.4, 7.4), (13.0, 6.2, 6.2)],
                              a, s), bone, caps=('start', 'end'), smooth=40)
    for o in (-8.0, 8.0):
        m.loft(0, 'gold', along(head, h, [(o - 1.2, 8.0, 8.0), (o + 1.2, 8.0, 8.0)], a, s), bone, smooth=40)
    m.loft(0, 'spike', path_sections([add(head, mul(h, 12.5)), add(head, mul(h, 23.0))], [(4.2, 4.2), (0.05, 0.05)],
                                     4, hint=a, phase=math.pi / 4), bone, smooth=30)
    return m.geosets[0], head


def build_topknot(to_space, bone):
    """A topknot of black hair, bound with a gold ring, on the bald crown."""
    m = Builder(1, atlas)
    path = [(1.5, 0.0, 125.5), (-0.5, 0.0, 129.6), (-4.6, 0.0, 132.0), (-9.6, 0.0, 130.6), (-12.6, 0.0, 126.4)]
    radii = [(3.4, 3.0), (2.8, 2.5), (2.9, 2.6), (2.0, 1.8), (0.15, 0.15)]
    m.loft(0, 'hair', [[to_space(p) for p in sec] for sec in
                       path_sections(path, radii, 5, hint=(0.0, 1.0, 0.0))], bone, smooth=60)
    ring = [(1.4, 0.0, 127.0), (1.0, 0.0, 128.8)]
    m.loft(0, 'gold', [[to_space(p) for p in sec] for sec in
                       path_sections(ring, [(3.8, 3.8), (3.5, 3.5)], 6, hint=(0.0, 1.0, 0.0))], bone, smooth=60)
    return m.geosets[0]


def build_eyes(middle_y, eye_centres, bones, size=1.0):
    """Glowing slits over the painted eyes, slanted in a scowl."""
    m = Builder(1, atlas)
    for (cx, cy, cz), bone in zip(eye_centres, bones):
        side = 1.0 if cy > middle_y else -1.0
        quad = [(cx - 0.2 * size, cy - side * 1.5 * size, cz - 0.3 * size),
                (cx, cy, cz + 0.6 * size),
                (cx - 0.5 * size, cy + side * 1.6 * size, cz + 0.4 * size),
                (cx, cy, cz - 0.5 * size)]
        m.mesh(0, 'eye', quad, [(0.0, 0.5), (0.5, 0.0), (1.0, 0.5), (0.5, 1.0)], [bone] * 4, [[0, 1, 2], [0, 2, 3]],
               outward=(1.0, 0.0, 0.0), smooth=80)
    return m.geosets[0]


class Space:
    """A mapping from the King's model space into another (identity, or the portrait's)."""

    def __init__(self, fn=None):
        self.fn = fn

    def __call__(self, p):
        return self.fn(p) if self.fn else p


# ---------------------------------------------------------------------------
# the dwarf proportions
# ---------------------------------------------------------------------------

def _upper_body(model):
    """Object ids that move rigidly with the chest (not the legs or cape)."""
    nodes = {e.node.object_id: e.node for _, e in model.all_nodes()}
    chest = model.node('Bone_Chest').node.object_id
    out = set()
    for oid, n in nodes.items():
        k = oid
        while k >= 0:
            if k == chest:
                if not n.name.startswith('Bone_Cape'):
                    out.add(oid)
                break
            k = nodes[k].parent
    return out


def deform(p, rigid):
    x, y, z = p
    if rigid or z > HIP_Z:
        z = z - DROP
    else:
        z = z * LEG_SCALE
    return (x * WIDEN[0], y * WIDEN[1], z)


def scale_of(p, rigid):
    return (WIDEN[0], WIDEN[1], 1.0 if rigid or p[2] > HIP_Z else LEG_SCALE)


def make_dwarf(model):
    rigid = _upper_body(model)
    for g in model.geosets:
        for i, v in enumerate(g.vertices):
            r = all(b in rigid for b in g.bones_of(i))
            sx, sy, sz = scale_of(v, r)
            n = g.normals[i]
            g.normals[i] = norm((n[0] / sx, n[1] / sy, n[2] / sz))
            g.vertices[i] = deform(v, r)
    root = model.node('Root').node.object_id
    for _, e in model.all_nodes():
        oid = e.node.object_id
        pivot = model.pivots[oid]
        r = oid in rigid
        sx, sy, sz = scale_of(pivot, r)
        if oid == root:
            sz = LEG_SCALE
        for t in e.node.tracks:
            if t.tag == b'KGTR':
                for key in t.keys:
                    key[1] = (key[1][0] * sx, key[1][1] * sy, key[1][2] * sz)
                    if key[2] is not None:
                        key[2] = (key[2][0] * sx, key[2][1] * sy, key[2][2] * sz)
                        key[3] = (key[3][0] * sx, key[3][1] * sy, key[3][2] * sz)
        model.pivots[oid] = deform(pivot, r)
        if e.kind == 'CLID':
            shape, pts, radius = e.collision()
            e.set_collision(shape, [deform(p, False) for p in pts], radius * 0.85 if radius else radius)


def finish(model):
    """Extents and sequence bounds after editing."""
    every = []
    for g in model.geosets:
        g.extent = extent(g.vertices)
        g.sequence_extents = [g.extent] * len(model.sequences)
        every += g.vertices
    model.extent = extent(every)
    for s in model.sequences:
        s.extent = model.extent


# ---------------------------------------------------------------------------
# the models
# ---------------------------------------------------------------------------

def _check_king(king):
    for geoset, path in KING_TEXTURES.items():
        layer_texture = mdxedit.layer_textures(king.materials[king.geosets[geoset].material])[-1]
        if king.textures[layer_texture].path != path:
            raise ValueError('King.zip is not the expected model (geoset %d)' % geoset)


def build_models():
    """Returns (model, portrait) as mdxedit.Model objects."""
    king = mdxedit.Model(read_reference('King/King.mdx'))
    portrait = mdxedit.Model(read_reference('King/King_Portrait.mdx'))
    _check_king(king)
    heads = HeadMap(king.geosets[HEAD], portrait.geosets[P_HEAD], portrait)
    head_bone = king.node('Bone_Head').node.object_id
    sword_bone = king.node('Sword').node.object_id

    # our texture and its materials, in both models
    def add_materials(model):
        model.textures.append(mdxedit.Texture(TEXTURE_PATH))
        tex = len(model.textures) - 1
        model.materials.append(mdxedit.material([(0, 0, tex, 1.0)]))
        model.materials.append(mdxedit.material([(3, 0x21, tex, 1.0)]))       # additive, unshaded, unfogged
        return len(model.materials) - 2, len(model.materials) - 1

    # -- the main model
    painted, glow = add_materials(king)
    head = king.geosets[HEAD]
    for i in range(len(head.vertices)):
        if heads.is_hair(i):
            head.vertices[i] = grow_beard(head.vertices[i])
    hair = split(head, heads.is_hair)
    king.geosets.append(hair)
    hair_geoset = len(king.geosets) - 1
    armour = king.geosets[ARMOUR]
    drop_faces(armour, lambda i: armour.bones_of(i) == [head_bone])          # the crown
    sword = king.geosets[SWORD]
    hammer, hammer_head = build_hammer(sword.vertices, sword_bone)
    king.geosets[SWORD] = to_geoset(hammer, painted)
    eyes = [ray_hit(head, heads.to_main(portrait.pivots[portrait.node(n).node.object_id]), (1.0, 0.0, 0.0))
            for n in ('Portrait__EyeL01', 'Portrait__EyeR01')]
    eyes = [add(e, (0.35, 0.0, 0.0)) for e in eyes]
    king.geosets.append(to_geoset(build_eyes(0.0, eyes, [head_bone, head_bone]), glow))
    king.geosets.append(to_geoset(build_topknot(Space(), head_bone), painted))
    for g in (BODY, ARMS, ARMOUR, TASSETS):
        tint(king, g, ARMOUR_TINT)
    tint(king, HEAD, SKIN_TINT)
    tint(king, hair_geoset, HAIR_TINT)
    tint(king, CAPE, CAPE_TINT)
    tint(king, SWORD_GLOW, (1.0, 1.0, 1.0), alpha=0.0)                        # the sword's glow
    for name in ('Weapon Ref', 'BlizRibbon01'):                             # at the hammer's head
        king.pivots[king.node(name).node.object_id] = hammer_head
    make_dwarf(king)
    king.sequence('Walk').move_speed = WALK_SPEED
    king.name = 'DarkIronThane'
    finish(king)

    # -- the portrait: the same head
    painted, glow = add_materials(portrait)
    ph = portrait.geosets[P_HEAD]
    portrait_hair = set()
    for j, v in enumerate(ph.vertices):
        if {heads.portrait_names[b] for b in ph.bones_of(j)} & BEARD_BONES:
            portrait_hair.add(j)
            ph.vertices[j] = heads.to_portrait(grow_beard(heads.to_main(v)))
    p_hair = split(ph, lambda j: j in portrait_hair)
    portrait.geosets.append(p_hair)
    p_hair_geoset = len(portrait.geosets) - 1
    p_head_bone = portrait.node('Portrait__Head01').node.object_id
    parmour = portrait.geosets[P_ARMOUR]
    drop_faces(parmour, lambda i: parmour.bones_of(i) == [p_head_bone])      # the crown
    p_eyes = []
    p_eye_bones = []
    for n in ('Portrait__EyeL01', 'Portrait__EyeR01'):
        e = portrait.node(n).node.object_id
        hit = ray_hit(ph, portrait.pivots[e], (1.0, 0.0, 0.0))
        p_eyes.append(add(hit, (0.35 * heads.scale, 0.0, 0.0)))
        p_eye_bones.append(e)
    portrait.geosets.append(to_geoset(build_eyes(heads.mp[1], p_eyes, p_eye_bones, size=heads.scale), glow))
    portrait.geosets.append(to_geoset(build_topknot(Space(heads.to_portrait), p_head_bone), painted))
    tint(portrait, P_ARMOUR, ARMOUR_TINT)
    head_anim = tint(portrait, P_HEAD, SKIN_TINT)
    hair_anim = tint(portrait, p_hair_geoset, HAIR_TINT)
    hair_anim.tracks = head_anim.tracks
    for g in (p_hair_geoset + 1, p_hair_geoset + 2):
        tint(portrait, g, (1.0, 1.0, 1.0)).tracks = head_anim.tracks
    portrait.name = 'DarkIronThane_Portrait'
    finish(portrait)
    return king, portrait


# ---------------------------------------------------------------------------
# the small texture for the added pieces
# ---------------------------------------------------------------------------

def _clamp(x):
    return 0.0 if x < 0.0 else 1.0 if x > 1.0 else x


def mix(a, b, t):
    t = _clamp(t)
    return tuple(a[k] + (b[k] - a[k]) * t for k in range(3))


def ramp(stops, x):
    if x <= stops[0][0]:
        return stops[0][1]
    for (p0, c0), (p1, c1) in zip(stops, stops[1:]):
        if x <= p1:
            return mix(c0, c1, (x - p0) / (p1 - p0))
    return stops[-1][1]


IRON = [(0.0, (196, 194, 202)), (0.18, (124, 120, 128)), (0.42, (40, 37, 42)), (0.58, (15, 14, 17)),
        (0.76, (80, 76, 82)), (0.9, (146, 142, 148)), (1.0, (70, 66, 72))]
GOLD = [(0.0, (255, 246, 196)), (0.2, (238, 196, 92)), (0.45, (164, 104, 30)), (0.6, (88, 50, 14)),
        (0.78, (196, 140, 50)), (0.9, (240, 206, 110)), (1.0, (150, 96, 30))]
FIRE = [(0.0, (0, 0, 0)), (0.3, (120, 20, 4)), (0.6, (240, 90, 16)), (0.85, (255, 190, 60)), (1.0, (255, 250, 200))]
RED_GLOW = [(0.0, (0, 0, 0)), (0.3, (110, 0, 0)), (0.6, (230, 16, 6)), (0.85, (255, 60, 30)), (1.0, (255, 160, 130))]
WOOD = [(0.0, (40, 22, 12)), (0.45, (92, 56, 30)), (0.8, (140, 94, 54)), (1.0, (178, 130, 80))]
LEATHER = [(0.0, (34, 20, 12)), (0.5, (96, 60, 34)), (1.0, (170, 124, 76))]
HAIR = [(0.0, (8, 8, 14)), (0.4, (30, 31, 44)), (0.75, (74, 78, 100)), (1.0, (150, 156, 182))]


def paint(region, u, v):
    if region == 'hammer':
        cheek = min(abs(u - 0.25), abs(u - 0.75))
        if cheek < 0.09 and 0.2 < v < 0.8:               # runes glowing like embers
            x, y = cheek / 0.09, (v - 0.5) / 0.3
            if min(abs(x - abs(y)), abs(abs(y) - 0.5) + (0.0 if x < 0.7 else 1.0)) < 0.13:
                return ramp(FIRE, 0.95 - 0.3 * abs(y))
        return ramp(IRON, 0.62 - 0.4 * math.cos(math.pi * (2 * u - 0.5)) ** 2)
    if region == 'gold':
        return ramp(GOLD, 0.1 + 0.8 * abs(math.sin(math.pi * (u + 0.25))))
    if region == 'spike':
        return ramp(IRON, 0.1 + 0.8 * abs(math.sin(math.pi * 2 * u)))
    if region == 'handle':
        return ramp(WOOD, 0.5 + 0.2 * math.sin(u * 4 * math.pi) * (0.6 + 0.4 * math.sin(v * 25)))
    if region == 'grip':
        return ramp(LEATHER, 0.55 if (u + v * 3.0) % 1.0 < 0.8 else 0.15)
    if region == 'hair':
        lock = abs(math.sin(math.pi * (u * 4 + 0.3 * math.sin(v * 6))))
        return ramp(HAIR, 0.3 + 0.35 * lock + 0.2 * (lock > 0.85) * math.sin(v * 9 + u * 20))
    if region == 'eye':
        return ramp(RED_GLOW, 1.0 - 1.7 * math.hypot(u - 0.5, (v - 0.5) * 0.8))
    raise KeyError(region)


def paint_texture():
    pixels = [(0, 0, 0)] * (TEX * TEX)
    for name, (x0, y0, x1, y1) in REGIONS.items():
        for py in range(y0, y1):
            v = _clamp((py + 0.5 - y0 - 1.0) / (y1 - y0 - 2))
            for px in range(x0, x1):
                u = _clamp((px + 0.5 - x0 - 1.0) / (x1 - x0 - 2))
                pixels[py * TEX + px] = tuple(int(min(255, max(0, c))) for c in paint(name, u, v))
    return pixels


def build():
    """Returns {archive path: bytes} for the model, its portrait and texture."""
    model, portrait = build_models()
    return {
        MODEL_PATH: model.write(),
        PORTRAIT_PATH: portrait.write(),
        TEXTURE_PATH: image.blp1(paint_texture(), TEX, TEX),
    }

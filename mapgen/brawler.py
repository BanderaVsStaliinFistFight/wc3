"""The Dark Iron Brawler: "RPGDwarf" by Tenebrae (RPGDwarf.zip), recoloured at
build time as a Dark Iron dwarf.

The model, its animations and its hand-painted texture are Tenebrae's. The
build only changes colours and adds two small glows:
- the skin goes dark slate, the ginger beard and hair near black
- the eyes turn red, with an additive glow over each so they burn in the dark
- the steel goes dark iron, the gold brass, the leather oxblood, the cap
  crimson
- the icon gets the same treatment
"""

import colorsys
import os
import zipfile

from . import image, mdxedit
from .dwarf import RED_GLOW, extent, mix, ramp, to_geoset
from .lowpoly import add, cross, mul, norm, sub

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ZIP = os.path.join(ROOT, 'RPGDwarf.zip')
MEMBERS = {
    'model': 'RPGDwarf/RPGDwarf-1/RPGDwarf.mdx',
    'portrait': 'RPGDwarf/RPGDwarf/RPGDwarf_Portrait.mdx',
    'texture': 'RPGDwarf/RPGDwarf/RPGDwarf.blp',
    'icon': 'RPGDwarf/assets/BTNRPGDwarf/BTNRPGDwarf.blp',
}
SOURCE_TEXTURE = 'Textures\\RPGDwarf.blp'

MODEL_PATH = 'war3mapImported\\DarkIronBrawler.mdx'
PORTRAIT_PATH = 'war3mapImported\\DarkIronBrawler_Portrait.mdx'   # the game finds it by this name
TEXTURE_PATH = 'war3mapImported\\DarkIronBrawler.blp'
ICON_PATH = 'ReplaceableTextures\\CommandButtons\\BTNDarkIronBrawler.blp'
DISABLED_ICON_PATH = 'ReplaceableTextures\\CommandButtonsDisabled\\DISBTNDarkIronBrawler.blp'

HEAD, P_HEAD = 2, 1                 # the head geoset in the model and in the portrait
CAP_BOTTOM = 42                     # texture rows above the headband are the cap
EYE = (158.5, 71.5)                 # centre of the painted eye, in texels
EYE_RADII = (8.0, 4.5)
GLOW = (192, 112, 16)               # x, y, size of the glow sprite, in an unused corner of the texture
GLOW_SCALE = 1.6                    # glow quad size relative to the painted eye
ICON_EYES = [(24.0, 20.5), (38.5, 20.5)]
ICON_EYE_RADII = (2.6, 1.5)
ICON_LIGHTEN = 1.25                 # the face a little lighter, so it reads at icon size


def read_reference(member):
    with zipfile.ZipFile(ZIP) as z:
        return z.read(MEMBERS[member])


# ---------------------------------------------------------------------------
# colours
# ---------------------------------------------------------------------------

def _clamp(x, lo=0.0, hi=1.0):
    return lo if x < lo else hi if x > hi else x


def smoothstep(a, b, x):
    t = _clamp((x - a) / (b - a))
    return t * t * (3.0 - 2.0 * t)


def iron(lum):
    k = 255.0 * (lum / 255.0) ** 1.3
    return (k * 0.62, k * 0.62, k * 0.68)


def skin(lum):
    return (lum * 0.42, lum * 0.44, lum * 0.53)


def hair(lum):
    return (6 + lum * 0.3, 6 + lum * 0.3, 8 + lum * 0.36)


def crimson(lum):
    return (lum * 2.4, lum * 0.45, lum * 0.4)


def brass(r, g, b):
    return (r * 0.92, g * 0.74, b * 0.5)


def oxblood(lum):
    return (lum * 1.1, lum * 0.45, lum * 0.4)


def _analyse(r, g, b):
    h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    return h * 360.0, s, v, 0.299 * r + 0.587 * g + 0.114 * b


def head_colour(r, g, b, cap):
    """Face, beard, headband and cap. Skin is pale and unsaturated, the
    beard dark and fully saturated, the band grey."""
    hue, s, v, lum = _analyse(r, g, b)
    metal = 1.0 - smoothstep(0.08, 0.2, s)
    if cap:
        return mix(crimson(lum), iron(lum), metal)
    body = mix(skin(lum), hair(lum), smoothstep(0.42, 0.75, s))
    return mix(body, iron(lum), metal)


def body_colour(r, g, b):
    """Armour: steel plates and mail, gold trim, leather and cloth."""
    hue, s, v, lum = _analyse(r, g, b)
    metal = 1.0 - smoothstep(0.12, 0.28, s)
    gold = smoothstep(0.33, 0.55, v) * smoothstep(0.3, 0.5, s)
    c = mix(oxblood(lum), brass(r, g, b), gold)
    return mix(c, iron(lum), metal)


def eye_colour(r, g, b, x, y, original):
    """The painted eye: white, iris and pupil become a red glow, brightest
    in the middle; lashes and lids stay as they are."""
    e = ((x - EYE[0]) / EYE_RADII[0]) ** 2 + ((y - EYE[1]) / EYE_RADII[1]) ** 2
    if e >= 1.0:
        return original
    hue, s, v, lum = _analyse(r, g, b)
    eye_like = max(1.0 - smoothstep(0.25, 0.45, s), 1.0 if 150.0 < hue < 260.0 else 0.0) * smoothstep(0.25, 0.4, v)
    eye_like = max(eye_like, 1.0 - smoothstep(0.2, 0.4, e))           # the pupil
    glow = ramp(RED_GLOW, 0.55 + 0.45 * (1.0 - e))
    return mix(original, glow, eye_like * (1.0 - smoothstep(0.6, 1.0, e)))


def recolour_texture(pixels, w, h, head_mask, used_mask):
    """Texels no triangle uses (the old orc face, Tenebrae's signature) keep
    their colours."""
    out = []
    for i, (r, g, b, a) in enumerate(pixels):
        x, y = i % w, i // w
        if not used_mask[i]:
            out.append((r, g, b, a))
            continue
        if head_mask[i]:
            c = head_colour(r, g, b, y < CAP_BOTTOM)
            c = eye_colour(r, g, b, x + 0.5, y + 0.5, c)
        else:
            c = body_colour(r, g, b)
        out.append(tuple(int(round(_clamp(k, 0, 255))) for k in c) + (a,))
    gx, gy, size = GLOW
    for y in range(size):
        for x in range(size):
            d = ((x + 0.5 - size / 2) ** 2 + (y + 0.5 - size / 2) ** 2) ** 0.5 / (size / 2 - 1)
            c = ramp(RED_GLOW, 1.0 - d) if d < 1.0 else (0, 0, 0)
            out[(gy + y) * w + gx + x] = tuple(int(round(k)) for k in c) + (255,)
    return out


def recolour_icon(pixels, w, h, border=4):
    """The icon: same face colours; the red background and the frame stay."""
    out = []
    for i, (r, g, b, a) in enumerate(pixels):
        x, y = i % w, i // w
        if min(x, y, w - 1 - x, h - 1 - y) < border:
            out.append((r, g, b, a))
            continue
        hue, s, v, lum = _analyse(r, g, b)
        if (hue < 12.0 or hue > 345.0) and s > 0.5 and (x < 12 or x > 46):     # the red background
            c = (r, g, b)
        else:
            c = tuple(k * ICON_LIGHTEN for k in head_colour(r, g, b, False))
        for ex, ey in ICON_EYES:
            e = ((x + 0.5 - ex) / ICON_EYE_RADII[0]) ** 2 + ((y + 0.5 - ey) / ICON_EYE_RADII[1]) ** 2
            if e < 1.0:
                c = mix(c, ramp(RED_GLOW, 0.7 + 0.3 * (1.0 - e)), 1.0 - smoothstep(0.5, 1.0, e))
        out.append(tuple(int(round(_clamp(k, 0, 255))) for k in c) + (a,))
    return out


def disabled_icon(pixels):
    """Greyed out and darkened, like the game's own DISBTN icons."""
    out = []
    for r, g, b, a in pixels:
        k = int((0.299 * r + 0.587 * g + 0.114 * b) * 0.55)
        out.append((k, k, k, a))
    return out


def uv_mask(geosets, w, h, grow=4):
    """Texels covered by the geosets' UV triangles, grown by a few texels so
    filtering at the seams picks up the right colours."""
    mask = bytearray(w * h)
    for g in geosets:
        for f in g.faces:
            pts = [(g.uvs[i][0] * w, g.uvs[i][1] * h) for i in f]
            (x0, y0), (x1, y1), (x2, y2) = pts
            area = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(area) < 1e-9:
                continue
            for y in range(max(0, int(min(y0, y1, y2)) - 1), min(h, int(max(y0, y1, y2)) + 2)):
                for x in range(max(0, int(min(x0, x1, x2)) - 1), min(w, int(max(x0, x1, x2)) + 2)):
                    px, py = x + 0.5, y + 0.5
                    a = ((x1 - px) * (y2 - py) - (x2 - px) * (y1 - py)) / area
                    b = ((x2 - px) * (y0 - py) - (x0 - px) * (y2 - py)) / area
                    if a >= 0 and b >= 0 and a + b <= 1:
                        mask[y * w + x] = 1
    for _ in range(grow):
        grown = bytearray(mask)
        for y in range(h):
            for x in range(w):
                if not mask[y * w + x] and any(mask[yy * w + xx] for yy in (y - 1, y, y + 1) for xx in (x - 1, x, x + 1)
                                               if 0 <= yy < h and 0 <= xx < w):
                    grown[y * w + x] = 1
        mask = grown
    return mask


# ---------------------------------------------------------------------------
# the eye glows
# ---------------------------------------------------------------------------

def eye_spots(geoset, w, h):
    """Where the painted eye sits on the mesh: one spot per triangle whose UVs
    hold the eye (the face is mirrored, so one per side). Each is (centre,
    the 3D directions of +u and +v texels, outward normal, vertex)."""
    eu, ev = EYE[0] / w, EYE[1] / h
    spots = []
    for f in geoset.faces:
        (u0, v0), (u1, v1), (u2, v2) = (geoset.uvs[i] for i in f)
        det = (u1 - u0) * (v2 - v0) - (u2 - u0) * (v1 - v0)
        if abs(det) < 1e-12:
            continue
        a = ((eu - u0) * (v2 - v0) - (u2 - u0) * (ev - v0)) / det
        b = ((u1 - u0) * (ev - v0) - (eu - u0) * (v1 - v0)) / det
        if a < 0 or b < 0 or a + b > 1:
            continue
        p0, p1, p2 = (geoset.vertices[i] for i in f)
        e1, e2 = sub(p1, p0), sub(p2, p0)
        centre = add(p0, add(mul(e1, a), mul(e2, b)))
        # solve dP/du and dP/dv from the two edges
        du1, dv1, du2, dv2 = u1 - u0, v1 - v0, u2 - u0, v2 - v0
        dpdu = mul(sub(mul(e1, dv2), mul(e2, dv1)), 1.0 / det)
        dpdv = mul(sub(mul(e2, du1), mul(e1, du2)), 1.0 / det)
        normal = norm(cross(e1, e2))
        if normal[0] < 0:               # the model faces +x
            normal = mul(normal, -1.0)
        weights = (1.0 - a - b, a, b)
        vertex = f[max(range(3), key=lambda k: weights[k])]
        if all(sum((c - d) ** 2 for c, d in zip(centre, s[0])) > 0.25 for s in spots):
            spots.append((centre, mul(dpdu, 1.0 / w), mul(dpdv, 1.0 / h), normal, vertex))
    return spots


def glow_geoset(geoset, material, w, h):
    gx, gy, size = GLOW
    corners = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
    built = {'vertices': [], 'normals': [], 'uvs': [], 'bones': [], 'triangles': []}
    for centre, du, dv, normal, vertex in eye_spots(geoset, w, h):
        bones = tuple(geoset.bones_of(vertex))
        base = len(built['vertices'])
        for su, sv in corners:
            p = add(centre, add(mul(du, su * EYE_RADII[0] * GLOW_SCALE), mul(dv, sv * EYE_RADII[1] * GLOW_SCALE)))
            built['vertices'].append(add(p, mul(normal, 0.3)))
            built['normals'].append(normal)
            built['uvs'].append(((gx + (su + 1) / 2 * size) / w, (gy + (sv + 1) / 2 * size) / h))
            built['bones'].append(bones)
        built['triangles'] += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    return to_geoset(built, material)


# ---------------------------------------------------------------------------
# the models
# ---------------------------------------------------------------------------

def retexture(model):
    """Points the model at our texture and adds the glow material."""
    found = False
    for t in model.textures:
        if t.path == SOURCE_TEXTURE:
            t.path = TEXTURE_PATH
            found = True
    if not found:
        raise ValueError('RPGDwarf.zip is not the expected model (no %s)' % SOURCE_TEXTURE)
    tex = [i for i, t in enumerate(model.textures) if t.path == TEXTURE_PATH][0]
    # additive, unshaded, two-sided (the face is mirrored, so the quads face both ways), unfogged
    model.materials.append(mdxedit.material([(3, 0x31, tex, 1.0)]))
    return len(model.materials) - 1


def add_glow(model, head, w, h):
    g = glow_geoset(model.geosets[head], retexture(model), w, h)
    if len(g.faces) != 4:
        raise ValueError('expected one painted eye on each side of the face, found %d' % (len(g.faces) // 2))
    g.extent = extent(g.vertices)
    g.sequence_extents = [g.extent] * len(model.sequences)
    model.geosets.append(g)


def faces_on(g, mask, w, h):
    """A copy of a geoset with only the faces whose middle lies on the mask
    (the portrait's head is in the same geoset as its body)."""
    out = mdxedit.Geoset()
    out.uvs = g.uvs
    for f in g.faces:
        u = sum(g.uvs[i][0] for i in f) / 3
        v = sum(g.uvs[i][1] for i in f) / 3
        if mask[min(h - 1, int(v * h)) * w + min(w - 1, int(u * w))]:
            out.faces.append(f)
    return out


def textured(model):
    """The geosets painted with the dwarf's texture (the portrait also has a
    team glow quad)."""
    return [g for g in model.geosets
            if any(model.textures[t].path == TEXTURE_PATH for t in mdxedit.layer_textures(model.materials[g.material]))]


def build_models(w, h):
    model = mdxedit.Model(read_reference('model'))
    portrait = mdxedit.Model(read_reference('portrait'))
    add_glow(model, HEAD, w, h)
    add_glow(portrait, P_HEAD, w, h)
    model.name = 'DarkIronBrawler'
    portrait.name = 'DarkIronBrawler_Portrait'
    return model, portrait


def build():
    """Returns {archive path: bytes}: the model, portrait, texture and icons."""
    pixels, w, h = image.read_blp(read_reference('texture'))
    model, portrait = build_models(w, h)
    # the head's margin stops where the body's own texels start (the ponytail sits next to the kilt)
    body = uv_mask([g for g in textured(model) if g is not model.geosets[HEAD]], w, h, grow=0)
    face = uv_mask([model.geosets[HEAD]], w, h)
    head = uv_mask([model.geosets[HEAD], faces_on(portrait.geosets[P_HEAD], face, w, h)], w, h)
    head = bytes(a and not b for a, b in zip(head, body))
    used = uv_mask(textured(model) + textured(portrait), w, h)
    texture = recolour_texture(pixels, w, h, head, used)
    icon, iw, ih = image.read_blp(read_reference('icon'))
    icon = recolour_icon(icon, iw, ih)
    return {
        MODEL_PATH: model.write(),
        PORTRAIT_PATH: portrait.write(),
        TEXTURE_PATH: image.blp1(texture, w, h),
        ICON_PATH: image.blp1(icon, iw, ih),
        DISABLED_ICON_PATH: image.blp1(disabled_icon(icon), iw, ih),
    }

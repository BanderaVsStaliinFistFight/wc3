"""A tiny software renderer for the generated hero model: it draws the
command-card icon and preview pictures, so the build needs no 3D tools."""

import math

from .mdx import quat_rotate

TEAM_COLOUR = (150, 20, 20)
LIGHT = (0.55, 0.35, 0.76)


def _lerp(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def _nlerp(a, b, t):
    if sum(x * y for x, y in zip(a, b)) < 0:
        b = tuple(-y for y in b)
    q = _lerp(a, b, t)
    n = math.sqrt(sum(x * x for x in q)) or 1.0
    return tuple(x / n for x in q)


def _sample(keys, frame, interp, default):
    if not keys:
        return default
    prev = None
    for f, v in keys:
        if f == frame:
            return v
        if f > frame:
            if prev is None:
                return v
            t = (frame - prev[0]) / (f - prev[0])
            return interp(prev[1], v, t)
        prev = (f, v)
    return prev[1]


def bone_transforms(model, frame=None):
    """Returns a function per bone mapping a rest-pose vertex to its posed position."""
    funcs = []
    for b in model['bones']:
        if frame is None:
            q, t, s = (0.0, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        else:
            q = _sample(b.get('rotation'), frame, _nlerp, (0.0, 0.0, 0.0, 1.0))
            t = _sample(b.get('translation'), frame, _lerp, (0.0, 0.0, 0.0))
            s = _sample(b.get('scaling'), frame, _lerp, (1.0, 1.0, 1.0))
        parent = funcs[b['parent']] if b['parent'] >= 0 else None
        funcs.append(_make_transform(b['pivot'], q, t, s, parent))
    return funcs


def _make_transform(pivot, q, t, s, parent):
    def f(v):
        p = (v[0] - pivot[0], v[1] - pivot[1], v[2] - pivot[2])
        p = (p[0] * s[0], p[1] * s[1], p[2] * s[2])
        p = quat_rotate(q, p)
        p = (p[0] + pivot[0] + t[0], p[1] + pivot[1] + t[1], p[2] + pivot[2] + t[2])
        return parent(p) if parent else p

    def rot(n):
        n = quat_rotate(q, n)
        return parent.rot(n) if parent else n
    f.rot = rot
    return f


def _look_at(eye, target):
    fx, fy, fz = (target[0] - eye[0], target[1] - eye[1], target[2] - eye[2])
    fl = math.sqrt(fx * fx + fy * fy + fz * fz)
    f = (fx / fl, fy / fl, fz / fl)
    up = (0.0, 0.0, 1.0)
    r = (f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0])
    rl = math.sqrt(sum(c * c for c in r))
    r = (r[0] / rl, r[1] / rl, r[2] / rl)
    u = (r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0])
    return f, r, u


def render(model, texture, tex_size, width, height, eye, target, fov=0.6, frame=None,
           background=None, team=TEAM_COLOUR):
    """Renders the model; returns (pixels, coverage mask)."""
    f, r, u = _look_at(eye, target)
    scale = 1.0 / math.tan(fov / 2)
    xf = bone_transforms(model, frame)
    zbuf = [1e30] * (width * height)
    px = list(background) if background else [(0, 0, 0)] * (width * height)
    mask = [False] * (width * height)

    for gi, g in enumerate(model['geosets']):
        unshaded = gi == 1
        verts = []
        for v, n, uv, b in zip(g['vertices'], g['normals'], g['uvs'], g['bones']):
            group = b if isinstance(b, (tuple, list)) else (b,)
            ps = [xf[k](v) for k in group]
            p = tuple(sum(q[c] for q in ps) / len(ps) for c in range(3))
            ns = [xf[k].rot(n) for k in group]
            n2 = tuple(sum(q[c] for q in ns) / len(ns) for c in range(3))
            d = (p[0] - eye[0], p[1] - eye[1], p[2] - eye[2])
            cz = d[0] * f[0] + d[1] * f[1] + d[2] * f[2]
            cx = d[0] * r[0] + d[1] * r[1] + d[2] * r[2]
            cy = d[0] * u[0] + d[1] * u[1] + d[2] * u[2]
            if cz <= 1.0:
                verts.append(None)
                continue
            sx = width / 2 + cx / cz * scale * width / 2
            sy = height / 2 - cy / cz * scale * height / 2
            light = max(0.0, n2[0] * LIGHT[0] + n2[1] * LIGHT[1] + n2[2] * LIGHT[2])
            verts.append((sx, sy, cz, uv, 0.42 + 0.75 * light))
        for a, bb, c in g['triangles']:
            va, vb, vc = verts[a], verts[bb], verts[c]
            if va is None or vb is None or vc is None:
                continue
            area = (vb[0] - va[0]) * (vc[1] - va[1]) - (vb[1] - va[1]) * (vc[0] - va[0])
            if area >= 0:   # back face (screen y points down)
                continue
            minx = max(0, int(min(va[0], vb[0], vc[0])))
            maxx = min(width - 1, int(max(va[0], vb[0], vc[0])) + 1)
            miny = max(0, int(min(va[1], vb[1], vc[1])))
            maxy = min(height - 1, int(max(va[1], vb[1], vc[1])) + 1)
            for y in range(miny, maxy + 1):
                py = y + 0.5
                for x in range(minx, maxx + 1):
                    pxx = x + 0.5
                    w0 = ((vb[0] - pxx) * (vc[1] - py) - (vb[1] - py) * (vc[0] - pxx)) / area
                    w1 = ((vc[0] - pxx) * (va[1] - py) - (vc[1] - py) * (va[0] - pxx)) / area
                    w2 = 1.0 - w0 - w1
                    if w0 < 0 or w1 < 0 or w2 < 0:
                        continue
                    z = w0 * va[2] + w1 * vb[2] + w2 * vc[2]
                    i = y * width + x
                    if z >= zbuf[i]:
                        continue
                    zbuf[i] = z
                    tu = w0 * va[3][0] + w1 * vb[3][0] + w2 * vc[3][0]
                    tv = w0 * va[3][1] + w1 * vb[3][1] + w2 * vc[3][1]
                    col = texture[min(tex_size - 1, int(tv * tex_size)) * tex_size
                                  + min(tex_size - 1, int(tu * tex_size))]
                    if not unshaded and len(col) > 3 and col[3] < 255:
                        # team colour shows through the texture's alpha
                        a = col[3] / 255.0
                        col = tuple(int(col[c] * a + team[c] * (1 - a)) for c in range(3))
                    if not unshaded:
                        k = w0 * va[4] + w1 * vb[4] + w2 * vc[4]
                        col = (min(255, int(col[0] * k)), min(255, int(col[1] * k)), min(255, int(col[2] * k)))
                    px[i] = col
                    mask[i] = True
    return px, mask


def _downsample(px, w, h, k):
    out = []
    for y in range(h // k):
        for x in range(w // k):
            acc = [0, 0, 0]
            for dy in range(k):
                for dx in range(k):
                    p = px[(y * k + dy) * w + x * k + dx]
                    acc[0] += p[0]
                    acc[1] += p[1]
                    acc[2] += p[2]
            out.append(tuple(c // (k * k) for c in acc))
    return out


def hero_icon(model, texture, tex_size, eye, target, fov=0.62, frame=None):
    """64x64 command card icon in the classic style (bevelled frame)."""
    size, k = 192, 3
    bg = []
    for y in range(size):
        for x in range(size):
            d = math.hypot(x - size * 0.55, y - size * 0.62) / size
            glow = max(0.0, 1.0 - d * 1.6)
            bg.append((int(30 + 190 * glow ** 1.5), int(10 + 70 * glow ** 2), int(8 + 10 * glow)))
    px, _ = render(model, texture, tex_size, size, size, eye=eye, target=target, fov=fov, frame=frame,
                   background=bg)
    icon = _downsample(px, size, size, k)
    out = []
    for y in range(64):
        for x in range(64):
            c = icon[y * 64 + x]
            edge = min(x, y, 63 - x, 63 - y)
            if edge < 3:
                light = (x < 3 or y < 3) and not (x > 60 or y > 60)
                f = 1.45 - 0.15 * edge if light else 0.45 + 0.1 * edge
                c = tuple(min(255, int(v * f + (40 if light else 0))) for v in c)
            out.append(c)
    return out


def disabled_icon(icon):
    out = []
    for r, g, b in icon:
        v = int((0.3 * r + 0.59 * g + 0.11 * b) * 0.55)
        out.append((v, v, v))
    return out


def preview(model, texture, tex_size, frames, size=320):
    """A strip of renders at the given animation frames, for documentation."""
    tiles = []
    for frame in frames:
        bg = [(26, 24, 30)] * (size * 2 * size * 2)
        px, _ = render(model, texture, tex_size, size * 2, size * 2, eye=(230.0, -150.0, 120.0),
                       target=(0.0, 0.0, 58.0), fov=0.62, frame=frame, background=bg)
        tiles.append(_downsample(px, size * 2, size * 2, 2))
    out = []
    for y in range(size):
        for t in tiles:
            out.extend(t[y * size:(y + 1) * size])
    return out, size * len(tiles), size

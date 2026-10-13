"""Low-polygon modelling in the manner of the classic Warcraft III units:
angular lofts through hand-placed cross sections, with smoothing groups
worked out from the angles between faces (soft over gentle curves, a crease
where two faces meet at a sharp angle)."""

import math


def add(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def sub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def mul(a, s):
    return (a[0] * s, a[1] * s, a[2] * s)


def dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a, b):
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def length(a):
    return math.sqrt(dot(a, a))


def norm(a):
    n = length(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 1.0)


def centroid(points):
    k = 1.0 / len(points)
    return (sum(p[0] for p in points) * k, sum(p[1] for p in points) * k, sum(p[2] for p in points) * k)


def frame(direction, hint=(1.0, 0.0, 0.0)):
    """Two unit axes across a direction: the first as close to the hint as
    possible, the second completing a right-handed set."""
    d = norm(direction)
    a = norm(sub(hint, mul(d, dot(hint, d))))
    return a, cross(d, a)


def section(center, ax, ay, pts):
    """A cross section: 2D points in the plane spanned by ax and ay."""
    return [add(center, add(mul(ax, a), mul(ay, b))) for a, b in pts]


class Builder:
    """Collects geosets in the form mdx.write expects."""

    def __init__(self, geoset_count, atlas):
        self.geosets = [{'vertices': [], 'normals': [], 'uvs': [], 'bones': [], 'triangles': []}
                        for _ in range(geoset_count)]
        self.atlas = atlas
        self.xf = None          # optional point transform applied to everything emitted

    def mesh(self, geo, region, points, uvs, bones, faces, smooth=50.0, outward=None):
        """faces are polygons of point indices. Their winding is fixed up so
        they face away from the part's centre (or along `outward`). Normals
        are averaged over the neighbouring faces (welded by position) that
        meet this face at less than `smooth` degrees."""
        if self.xf:
            points = [self.xf(p) for p in points]
            if outward:
                o = self.xf((0.0, 0.0, 0.0))
                outward = sub(self.xf(outward), o)
        tris = []
        for f in faces:
            for i in range(1, len(f) - 1):
                tris.append((f[0], f[i], f[i + 1]))
        fn = [cross(sub(points[b], points[a]), sub(points[c], points[a])) for a, b, c in tris]
        keep = [length(n) > 1e-6 for n in fn]
        mid = centroid(points)
        score = 0.0
        for (a, b, c), n, k in zip(tris, fn, keep):
            if k:
                ref = outward if outward else sub(centroid((points[a], points[b], points[c])), mid)
                score += dot(n, ref)
        if score < 0:
            tris = [(a, c, b) for a, b, c in tris]
            fn = [mul(n, -1.0) for n in fn]
        unit = [norm(n) for n in fn]
        weld = {}
        key_of = []
        for p in points:
            key = (round(p[0], 3), round(p[1], 3), round(p[2], 3))
            key_of.append(weld.setdefault(key, len(weld)))
        around = {}
        for t, tri in enumerate(tris):
            if keep[t]:
                for v in tri:
                    around.setdefault(key_of[v], []).append(t)
        limit = math.cos(math.radians(smooth))
        g = self.geosets[geo]
        made = {}
        for t, tri in enumerate(tris):
            if not keep[t]:
                continue
            out = []
            for v in tri:
                acc = (0.0, 0.0, 0.0)
                for o in around[key_of[v]]:
                    if dot(unit[o], unit[t]) >= limit:
                        acc = add(acc, fn[o])
                n = norm(acc)
                key = (v, round(n[0], 2), round(n[1], 2), round(n[2], 2))
                idx = made.get(key)
                if idx is None:
                    idx = len(g['vertices'])
                    g['vertices'].append(points[v])
                    g['normals'].append(n)
                    g['uvs'].append(self.atlas(region, *uvs[v]))
                    b = bones[v]
                    g['bones'].append(b if isinstance(b, tuple) else (b,))
                    made[key] = idx
                out.append(idx)
            g['triangles'].append(tuple(out))

    def loft(self, geo, region, sections, bones, caps=(), smooth=50.0, us=None, vs=None, closed=True, outward=None,
             v_range=(0.0, 1.0)):
        """A skin through cross sections (lists of points, all the same
        length). bones: one entry per section, one for all, or a function of
        the point. caps: 'start' and/or 'end' close the ends. us: u per
        section point (else by perimeter); vs: v per section (else by
        distance along the sections)."""
        n, m = len(sections[0]), len(sections)
        if callable(bones):
            bone_of, per_section = bones, None
        else:
            bone_of, per_section = None, bones if isinstance(bones, list) else [bones] * m
        cents = [centroid(s) for s in sections]
        dist = [0.0]
        for i in range(1, m):
            dist.append(dist[-1] + length(sub(cents[i], cents[i - 1])))
        total = dist[-1] or 1.0
        cols = n + 1 if closed else n
        pts, uvs, bl = [], [], []
        for i, sec in enumerate(sections):
            if us:
                u_of = list(us) + ([1.0] if closed else [])
            else:
                per = [0.0]
                for j in range(1, cols):
                    per.append(per[-1] + length(sub(sec[j % n], sec[j - 1])))
                u_of = [x / (per[-1] or 1.0) for x in per]
            v = vs[i] if vs else v_range[0] + (v_range[1] - v_range[0]) * dist[i] / total
            for j in range(cols):
                pts.append(sec[j % n])
                uvs.append((u_of[j], v))
                bl.append(bone_of(sec[j % n]) if bone_of else per_section[i])
        faces = []
        for i in range(m - 1):
            for j in range(cols - 1):
                a = i * cols + j
                faces.append([a, a + 1, a + cols + 1, a + cols])
        for end in caps:
            i = 0 if end == 'start' else m - 1
            c = len(pts)
            pts.append(cents[i])
            uvs.append((0.5, uvs[i * cols][1]))
            bl.append(bone_of(cents[i]) if bone_of else per_section[i])
            for j in range(n):
                faces.append([c, i * cols + j, i * cols + (j + 1) % n])
        self.mesh(geo, region, pts, uvs, bl, faces, smooth=smooth, outward=outward)

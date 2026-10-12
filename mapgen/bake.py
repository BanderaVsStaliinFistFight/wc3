"""Light baking for the generated models: ambient occlusion is traced through
a voxel grid of the mesh and painted into the texture, the way the classic
Warcraft III artists painted shading into their skins."""

import math

from .lowpoly import cross, norm


def _directions(count):
    """Cosine-weighted directions over the +Z hemisphere (a Fibonacci spiral)."""
    golden = math.pi * (3.0 - math.sqrt(5.0))
    out = []
    for i in range(count):
        u = (i + 0.5) / count
        r = math.sqrt(u)
        a = i * golden
        out.append((r * math.cos(a), r * math.sin(a), math.sqrt(1.0 - u)))
    return out


def vertex_occlusion(geosets, cell=1.5, rays=16, reach=15.0):
    """Ambient occlusion per vertex (1 = open, 0 = buried), as lists parallel
    to each geoset's vertices."""
    pts = [p for g in geosets for p in g['vertices']]
    lo = [min(p[k] for p in pts) - 3 * cell for k in range(3)]
    hi = [max(p[k] for p in pts) + 3 * cell for k in range(3)]
    nx, ny, nz = (int((hi[k] - lo[k]) / cell) + 1 for k in range(3))
    solid = bytearray(nx * ny * nz)
    inv = 1.0 / cell

    def mark(p):
        solid[(int((p[2] - lo[2]) * inv) * ny + int((p[1] - lo[1]) * inv)) * nx + int((p[0] - lo[0]) * inv)] = 1

    for g in geosets:
        v = g['vertices']
        for ia, ib, ic in g['triangles']:
            a, b, c = v[ia], v[ib], v[ic]
            longest = max(math.dist(a, b), math.dist(b, c), math.dist(c, a))
            n = max(1, int(math.ceil(longest / (cell * 0.5))))
            for i in range(n + 1):
                for j in range(n + 1 - i):
                    fa, fb = i / n, j / n
                    mark((a[0] + (b[0] - a[0]) * fa + (c[0] - a[0]) * fb,
                          a[1] + (b[1] - a[1]) * fa + (c[1] - a[1]) * fb,
                          a[2] + (b[2] - a[2]) * fa + (c[2] - a[2]) * fb))

    dirs = _directions(rays)
    step = cell * 0.6
    out = []
    for g in geosets:
        values = []
        for p, n in zip(g['vertices'], g['normals']):
            ref = (0.0, 0.0, 1.0) if abs(n[2]) < 0.9 else (1.0, 0.0, 0.0)
            t = norm(cross(ref, n))
            b = cross(n, t)
            ox, oy, oz = p[0] + n[0] * cell * 0.9, p[1] + n[1] * cell * 0.9, p[2] + n[2] * cell * 0.9
            blocked = 0.0
            for dx, dy, dz in dirs:
                rx = t[0] * dx + b[0] * dy + n[0] * dz
                ry = t[1] * dx + b[1] * dy + n[1] * dz
                rz = t[2] * dx + b[2] * dy + n[2] * dz
                d = step
                while d < reach:
                    ix = int((ox + rx * d - lo[0]) * inv)
                    iy = int((oy + ry * d - lo[1]) * inv)
                    iz = int((oz + rz * d - lo[2]) * inv)
                    if not (0 <= ix < nx and 0 <= iy < ny and 0 <= iz < nz):
                        break
                    if solid[(iz * ny + iy) * nx + ix]:
                        blocked += 1.0 - d / reach
                        break
                    d += step
            values.append(1.0 - blocked / rays)
        out.append(values)
    return out


def bake(geoset, values, size, regions):
    """Rasterises per-vertex values into texture space. Returns a list of
    size * size floats, None where no triangle covers a texel; uncovered
    texels next to covered ones are filled in so mipmaps don't bleed."""
    acc = [None] * (size * size)
    uvs = geoset['uvs']
    for ia, ib, ic in geoset['triangles']:
        (ua, va), (ub, vb), (uc, vc) = uvs[ia], uvs[ib], uvs[ic]
        ax, ay, bx, by, cx, cy = ua * size, va * size, ub * size, vb * size, uc * size, vc * size
        area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
        if abs(area) < 1e-9:
            continue
        ka, kb, kc = values[ia], values[ib], values[ic]
        x0 = max(0, int(min(ax, bx, cx)))
        x1 = min(size - 1, int(max(ax, bx, cx)))
        y0 = max(0, int(min(ay, by, cy)))
        y1 = min(size - 1, int(max(ay, by, cy)))
        for y in range(y0, y1 + 1):
            py = y + 0.5
            for x in range(x0, x1 + 1):
                px = x + 0.5
                w0 = ((bx - px) * (cy - py) - (by - py) * (cx - px)) / area
                w1 = ((cx - px) * (ay - py) - (cy - py) * (ax - px)) / area
                w2 = 1.0 - w0 - w1
                if w0 < -1e-6 or w1 < -1e-6 or w2 < -1e-6:
                    continue
                k = w0 * ka + w1 * kb + w2 * kc
                i = y * size + x
                acc[i] = k if acc[i] is None else (acc[i] + k) * 0.5
    # grow the covered area a few texels within each region
    inside = bytearray(size * size)
    for r, (x0, y0, x1, y1) in enumerate(regions):
        for y in range(y0, y1):
            inside[y * size + x0:y * size + x1] = bytes([r + 1]) * (x1 - x0)
    for _ in range(4):
        grown = list(acc)
        for i, k in enumerate(acc):
            if k is not None or not inside[i]:
                continue
            x, y = i % size, i // size
            total, n = 0.0, 0
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1)):
                xx, yy = x + dx, y + dy
                if 0 <= xx < size and 0 <= yy < size:
                    j = yy * size + xx
                    if acc[j] is not None and inside[j] == inside[i]:
                        total += acc[j]
                        n += 1
            if n:
                grown[i] = total / n
        acc = grown
    return acc

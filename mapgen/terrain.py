"""Procedural (but deterministic) terrain, pathing, doodads and minimap for
the map described in layout.py."""

import math
import random

from . import layout as L
from . import formats as F

GROUND_TILES = ['Ldrt', 'Ldro', 'Ldrg', 'Lrok', 'Lgrs', 'Lgrd', 'Vcbp']
T_DIRT, T_ROUGH, T_GRASSDIRT, T_ROCK, T_GRASS, T_DARKGRASS, T_COBBLE = range(7)
CLIFF_TILES = ['CLdi', 'CLgr']
NO_CLIFF_TEXTURE = 15

WATER_RAW = 0x2000          # water level stored in the corners
WATER_Z = -89.6             # world height of that water level (Lordaeron water offset -0.7 levels)
DEEP_DEPTH = 60.0           # deeper than this is not walkable

TEXTURE_COLOURS = {
    T_DIRT: (128, 104, 72), T_ROUGH: (110, 92, 70), T_GRASSDIRT: (104, 116, 64),
    T_ROCK: (118, 114, 106), T_GRASS: (72, 120, 48), T_DARKGRASS: (52, 92, 40),
    T_COBBLE: (150, 142, 128),
}


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def smoothstep(e0, e1, x):
    if e1 == e0:
        return 1.0 if x >= e1 else 0.0
    t = max(0.0, min(1.0, (x - e0) / (e1 - e0)))
    return t * t * (3 - 2 * t)


def seg_dist(px, py, ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    ll = dx * dx + dy * dy
    t = 0.0 if ll == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
    qx, qy = ax + t * dx, ay + t * dy
    return math.hypot(px - qx, py - qy)


def poly_dist(px, py, pts):
    return min(seg_dist(px, py, *pts[i], *pts[i + 1]) for i in range(len(pts) - 1))


def ellipse(px, py, e):
    cx, cy, rx, ry = e
    return math.sqrt(((px - cx) / rx) ** 2 + ((py - cy) / ry) ** 2)


class Noise:
    """Smooth value noise with a fixed seed."""

    def __init__(self, seed):
        self.seed = seed

    def _h(self, ix, iy):
        n = (ix * 374761393 + iy * 668265263 + self.seed * 1442695041) & 0xFFFFFFFF
        n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
        return ((n ^ (n >> 16)) & 0xFFFF) / 65535.0

    def value(self, x, y):
        ix, iy = math.floor(x), math.floor(y)
        fx, fy = x - ix, y - iy
        sx, sy = fx * fx * (3 - 2 * fx), fy * fy * (3 - 2 * fy)
        a = self._h(ix, iy)
        b = self._h(ix + 1, iy)
        c = self._h(ix, iy + 1)
        d = self._h(ix + 1, iy + 1)
        return (a + (b - a) * sx) + ((c + (d - c) * sx) - (a + (b - a) * sx)) * sy

    def fbm(self, x, y, octaves=4):
        total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
        for _ in range(octaves):
            total += amp * self.value(x * freq, y * freq)
            norm += amp
            amp *= 0.5
            freq *= 2.0
        return total / norm


def river_center(x):
    return L.RIVER_BASE_Y + 160.0 * math.sin((x + 800.0) / 2100.0) + 60.0 * math.sin(x / 700.0 + 0.7)


def ford_factor(x):
    best = 0.0
    for fx in L.FORDS_X:
        d = abs(x - fx)
        best = max(best, 1.0 - smoothstep(L.FORD_HALF_WIDTH * 0.55, L.FORD_HALF_WIDTH, d))
    return best


class Corner:
    __slots__ = ('height', 'water', 'edge', 'ramp', 'blight', 'is_water', 'boundary',
                 'texture', 'variation', 'cliff_variation', 'cliff_texture', 'layer', 'z')

    def __init__(self):
        self.height = 0x2000
        self.water = WATER_RAW
        self.edge = False
        self.ramp = False
        self.blight = False
        self.is_water = False
        self.boundary = False
        self.texture = T_GRASS
        self.variation = 0
        self.cliff_variation = 0
        self.cliff_texture = NO_CLIFF_TEXTURE
        self.layer = 2
        self.z = 0.0


class Terrain:
    tileset = L.TILESET
    custom_tileset = True     # Vcbp comes from the Village tileset
    ground_tiles = GROUND_TILES
    cliff_tiles = CLIFF_TILES
    width = L.WIDTH
    height = L.HEIGHT

    def __init__(self):
        self.rng = random.Random(L.SEED)
        self.hill_noise = Noise(L.SEED + 1)
        self.tex_noise = Noise(L.SEED + 2)
        self.tex_noise2 = Noise(L.SEED + 3)
        self.tree_noise = Noise(L.SEED + 4)
        self.edge_noise = Noise(L.SEED + 5)
        self.corners = [[Corner() for _ in range(self.width + 1)] for _ in range(self.height + 1)]
        self.trails = self._make_trails()
        self.doodads = []
        self.warnings = []
        self._build()

    # -- coordinates ------------------------------------------------------

    @staticmethod
    def corner_xy(cx, cy):
        return -L.HALF_W + 128.0 * cx, -L.HALF_H + 128.0 * cy

    @staticmethod
    def tile_center(tx, ty):
        return -L.HALF_W + 128.0 * tx + 64.0, -L.HALF_H + 128.0 * ty + 64.0

    def in_margin_tile(self, tx, ty):
        return (tx < L.BOUNDS[0] or tx >= self.width - L.BOUNDS[1]
                or ty < L.BOUNDS[2] or ty >= self.height - L.BOUNDS[3])

    @staticmethod
    def _make_trails():
        """A footpath from every camp and boss lair to the nearest road."""
        trails = []
        spots = [c['pos'] for c in L.CAMPS] + [b['pos'] for b in L.BOSSES]
        for px, py in spots:
            best = None
            for pts, _hw in L.ROADS:
                for i in range(len(pts) - 1):
                    (ax, ay), (bx, by) = pts[i], pts[i + 1]
                    dx, dy = bx - ax, by - ay
                    ll = dx * dx + dy * dy
                    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / ll))
                    qx, qy = ax + t * dx, ay + t * dy
                    d = math.hypot(px - qx, py - qy)
                    if best is None or d < best[0]:
                        best = (d, qx, qy)
            if best[0] > 200:
                trails.append((px, py, best[1], best[2]))
        return trails

    def trail_distance(self, x, y):
        if not self.trails:
            return 1e9
        return min(seg_dist(x, y, *t) for t in self.trails)

    def road_distance(self, x, y):
        best = 1e9
        for pts, hw in L.ROADS:
            best = min(best, poly_dist(x, y, pts) - hw)
        return best

    # -- the generator ----------------------------------------------------

    def _build(self):
        self._ridges()
        self._heights_and_water()
        self._textures()
        self._edges()
        self._fix_cliff_corners()
        self._finalize_z()
        self._pathing()
        self._place_doodads()
        self._validate_layout()

    def _ridges(self):
        W, H = self.width, self.height
        for cy in range(H + 1):
            for cx in range(W + 1):
                x, y = self.corner_xy(cx, cy)
                for e in L.RIDGES:
                    wobble = 0.18 * (self.edge_noise.fbm(x / 700.0, y / 700.0, 3) - 0.5)
                    if ellipse(x, y, e) < 1.0 + wobble:
                        self.corners[cy][cx].layer = 3
        # Remove single raised corners and diagonal-only patterns, which make
        # awkward cliff shapes: repeat until stable.
        changed = True
        while changed:
            changed = False
            for ty in range(H):
                for tx in range(W):
                    cs = [self.corners[ty][tx], self.corners[ty][tx + 1],
                          self.corners[ty + 1][tx], self.corners[ty + 1][tx + 1]]
                    lv = [c.layer for c in cs]
                    if lv[0] == lv[3] and lv[1] == lv[2] and lv[0] != lv[1]:
                        for c in cs:
                            c.layer = 3
                        changed = True
            for cy in range(1, H):
                for cx in range(1, W):
                    c = self.corners[cy][cx]
                    if c.layer == 3:
                        n = sum(self.corners[cy + dy][cx + dx].layer == 3
                                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
                        if n <= 1:
                            c.layer = 2
                            changed = True

    def _near_ridge(self, cx, cy, r):
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                x2, y2 = cx + dx, cy + dy
                if 0 <= x2 <= self.width and 0 <= y2 <= self.height and self.corners[y2][x2].layer == 3:
                    return True
        return False

    def _flatness(self, x, y):
        """1 where the ground may roll freely, 0 where it must stay flat."""
        f = 1.0
        for cx, cy, r in L.CLEARINGS:
            f = min(f, smoothstep(r * 0.6, r + 300, math.hypot(x - cx, y - cy)))
        f = min(f, smoothstep(0, 500, self.road_distance(x, y)))
        for camp in L.CAMPS:
            f = min(f, smoothstep(250, 600, math.hypot(x - camp['pos'][0], y - camp['pos'][1])))
        for b in L.BOSSES:
            f = min(f, smoothstep(300, 700, math.hypot(x - b['pos'][0], y - b['pos'][1])))
        return f

    def _heights_and_water(self):
        W, H = self.width, self.height
        for cy in range(H + 1):
            for cx in range(W + 1):
                x, y = self.corner_xy(cx, cy)
                c = self.corners[cy][cx]
                n = self.hill_noise.fbm(x / 1800.0, y / 1800.0, 4) - 0.5
                z = 190.0 * n * self._flatness(x, y)
                if self._near_ridge(cx, cy, 2):
                    z = 0.0

                # river
                d = abs(y - river_center(x))
                hw = L.RIVER_HALF_WIDTH
                if d < hw + 384:
                    bottom = -260.0 + 135.0 * ford_factor(x)
                    shore = min(z, -30.0) if d < hw else z
                    t = smoothstep(0.0, hw, d)
                    rz = bottom + (-30.0 - bottom) * t
                    if d >= hw:
                        rz = -30.0 + (z + 30.0) * smoothstep(hw, hw + 384, d)
                    z = min(z, rz) if d < hw else rz
                    del shore
                    c.is_water = True

                # lakes
                for (lx, ly), rx, ry in L.LAKES:
                    e = ellipse(x, y, (lx, ly, rx, ry))
                    if e < 1.6:
                        lz = -230.0 + 200.0 * smoothstep(0.0, 1.0, e)
                        if e >= 1.0:
                            lz = -30.0 + (z + 30.0) * smoothstep(1.0, 1.6, e)
                        z = min(z, lz)
                        c.is_water = True

                c.z = z

    def _textures(self):
        W, H = self.width, self.height
        rng = self.rng
        for cy in range(H + 1):
            for cx in range(W + 1):
                x, y = self.corner_xy(cx, cy)
                c = self.corners[cy][cx]
                n1 = self.tex_noise.fbm(x / 900.0, y / 900.0, 3)
                n2 = self.tex_noise2.fbm(x / 500.0, y / 500.0, 3)
                tex = T_GRASS
                if n1 > 0.58:
                    tex = T_DARKGRASS
                elif n2 > 0.66:
                    tex = T_GRASSDIRT

                for kind, _tree, _dens, e in L.FORESTS:
                    if ellipse(x, y, e) < 0.9 and n2 > 0.35:
                        tex = T_DARKGRASS
                if ellipse(x, y, (-5200, 1700, 2300, 2100)) < 0.8 and n1 > 0.62:
                    tex = T_GRASSDIRT

                # north: rougher ground
                if y > 3000 and n2 > 0.55:
                    tex = T_ROUGH
                # quarry and graveyard
                if math.hypot(x - 3328, y - 4608) < 700:
                    tex = T_ROCK if n2 > 0.45 else T_ROUGH
                if math.hypot(x + 3328, y - 4608) < 650:
                    tex = T_ROUGH if n2 > 0.5 else T_DARKGRASS
                # bosses' lairs
                for b in L.BOSSES:
                    if math.hypot(x - b['pos'][0], y - b['pos'][1]) < 420 + 120 * n2:
                        tex = T_ROUGH if b['key'] != 'dragon' else T_ROCK

                # river and lake beds and banks
                if c.z < -40:
                    tex = T_ROUGH if n2 > 0.5 else T_GRASSDIRT
                if c.z < -110:
                    tex = T_ROCK if n2 > 0.6 else T_ROUGH

                # roads
                rd = self.road_distance(x, y)
                if rd < 0:
                    tex = T_DIRT
                elif rd < 90 and n2 > 0.45:
                    tex = T_ROUGH
                elif self.trail_distance(x, y) < 70 + 60 * n1:
                    tex = T_ROUGH if n2 > 0.5 else T_GRASSDIRT

                # town plaza and outposts
                if math.hypot(x - L.TOWN[0], y - L.TOWN[1]) < 820 + 120 * (n1 - 0.5):
                    tex = T_COBBLE
                for o in L.OUTPOSTS:
                    if math.hypot(x - o['pos'][0], y - o['pos'][1]) < 300:
                        tex = T_COBBLE
                for b in L.BASES:
                    if math.hypot(x - b['hall'][0], y - b['hall'][1]) < 420:
                        tex = T_ROUGH if n2 > 0.4 else T_DIRT

                # ridges
                if self._near_ridge(cx, cy, 1):
                    tex = T_ROCK if n2 > 0.35 else T_ROUGH

                # blight around the citadel
                dc = math.hypot(x - L.CITADEL[0], y - L.CITADEL[1])
                if dc < L.CITADEL_RADIUS + 300 * (self.edge_noise.fbm(x / 600.0, y / 600.0, 3) - 0.5):
                    c.blight = True
                    if tex in (T_GRASS, T_DARKGRASS, T_GRASSDIRT):
                        tex = T_ROUGH

                c.texture = tex
                r = rng.random()
                c.variation = 16 if r < 0.05 else 17 if r < 0.10 else rng.choice((0, 4, 8, 12))

    def _edges(self):
        W, H = self.width, self.height
        for cy in range(H + 1):
            for cx in range(W + 1):
                c = self.corners[cy][cx]
                if cx < W and cy < H and self.in_margin_tile(cx, cy):
                    c.edge = True

    def _fix_cliff_corners(self):
        W, H = self.width, self.height
        for cy in range(H + 1):
            for cx in range(W + 1):
                if self._near_ridge(cx, cy, 1):
                    c = self.corners[cy][cx]
                    c.cliff_texture = 0
                    c.is_water = False

    def _finalize_z(self):
        for row in self.corners:
            for c in row:
                raw = int(round(0x2000 + 4.0 * c.z))
                c.height = max(0x0400, min(0x3C00, raw))
                c.z = (c.height - 0x2000) / 4.0 + (c.layer - 2) * 128.0

    # -- sampling ---------------------------------------------------------

    def ground_z(self, x, y):
        fx = (x + L.HALF_W) / 128.0
        fy = (y + L.HALF_H) / 128.0
        ix = max(0, min(self.width - 1, int(math.floor(fx))))
        iy = max(0, min(self.height - 1, int(math.floor(fy))))
        tx, ty = fx - ix, fy - iy
        c = self.corners
        a = c[iy][ix].z + (c[iy][ix + 1].z - c[iy][ix].z) * tx
        b = c[iy + 1][ix].z + (c[iy + 1][ix + 1].z - c[iy + 1][ix].z) * tx
        return a + (b - a) * ty

    def tile_is_cliff(self, tx, ty):
        c = self.corners
        layers = {c[ty][tx].layer, c[ty][tx + 1].layer, c[ty + 1][tx].layer, c[ty + 1][tx + 1].layer}
        return len(layers) > 1

    def tile_blighted(self, tx, ty):
        c = self.corners
        return c[ty][tx].blight and c[ty][tx + 1].blight and c[ty + 1][tx].blight and c[ty + 1][tx + 1].blight

    # -- pathing ----------------------------------------------------------

    def _pathing(self):
        W, H = self.width, self.height
        pw = W * 4
        cells = bytearray(pw * H * 4)
        for ty in range(H):
            for tx in range(W):
                margin = self.in_margin_tile(tx, ty)
                cliff = self.tile_is_cliff(tx, ty)
                blight = self.tile_blighted(tx, ty)
                for sy in range(4):
                    for sx in range(4):
                        x = -L.HALF_W + 128.0 * tx + 32.0 * sx + 16.0
                        y = -L.HALF_H + 128.0 * ty + 32.0 * sy + 16.0
                        if margin:
                            v = 0xCE
                        elif cliff:
                            v = 0xCA
                        else:
                            depth = WATER_Z - self.ground_z(x, y)
                            if depth > DEEP_DEPTH:
                                v = F.PATH_NO_WALK | F.PATH_NO_BUILD
                            elif depth > 0:
                                v = F.PATH_NO_BUILD
                            else:
                                v = F.PATH_NO_WATER
                            if blight and depth <= 0:
                                v |= F.PATH_BLIGHT
                        cells[(ty * 4 + sy) * pw + tx * 4 + sx] = v
        self.pathing = cells

    def cell_walkable(self, x, y):
        cx = int((x + L.HALF_W) // 32)
        cy = int((y + L.HALF_H) // 32)
        if not (0 <= cx < self.width * 4 and 0 <= cy < self.height * 4):
            return False
        return not self.pathing[cy * self.width * 4 + cx] & F.PATH_NO_WALK

    def area_walkable(self, x, y, r):
        for dy in range(-int(r), int(r) + 1, 32):
            for dx in range(-int(r), int(r) + 1, 32):
                if not self.cell_walkable(x + dx, y + dy):
                    return False
        return True

    # -- doodads ----------------------------------------------------------

    def _blocked_for_trees(self, x, y, tx, ty):
        if self.tile_is_cliff(tx, ty):
            return True
        for cx, cy, r in L.CLEARINGS:
            if math.hypot(x - cx, y - cy) < r:
                return True
        if self.road_distance(x, y) < 150:
            return True
        if self.trail_distance(x, y) < 170:
            return True
        for camp in L.CAMPS:
            if math.hypot(x - camp['pos'][0], y - camp['pos'][1]) < 420:
                return True
        for b in L.BOSSES:
            if math.hypot(x - b['pos'][0], y - b['pos'][1]) < 560:
                return True
        for sx, sy in L.SIGNPOSTS:
            if math.hypot(x - sx, y - sy) < 200:
                return True
        if math.hypot(x - L.RAID_SPAWN[0], y - L.RAID_SPAWN[1]) < 500:
            return True
        # keep everything around water a few tiles open
        for dx, dy in ((0, 0), (-96, 0), (96, 0), (0, -96), (0, 96)):
            if self.ground_z(x + dx, y + dy) < -45:
                return True
        return False

    def _tree_density(self, x, y):
        best, tree = 0.0, 'LTlt'
        edge = min(x - L.PLAY_MIN_X, L.PLAY_MAX_X - x, y - L.PLAY_MIN_Y, L.PLAY_MAX_Y - y)
        if edge < 700:
            best = 0.92 - 0.5 * smoothstep(350, 700, edge)
            tree = 'CTtr' if y > 4200 and abs(x) < 3200 else 'LTlt'
        for kind, tid, dens, e in L.FORESTS:
            d = ellipse(x, y, e)
            if d < 1.0:
                v = dens * (1.0 - smoothstep(0.65, 1.0, d))
                if v > best:
                    best, tree = v, tid
        for tid, e in L.GROVES:
            d = ellipse(x, y, e)
            if d < 1.0:
                v = 0.9 * (1.0 - smoothstep(0.75, 1.0, d))
                if v > best:
                    best, tree = v, tid
        n = self.tree_noise.fbm(x / 650.0, y / 650.0, 3)
        best *= 0.35 + 1.3 * n
        best = max(best, 0.025)
        return min(best, 0.97), tree

    def _add(self, did, x, y, var=0, scale=1.0, angle=None, flags=F.DOODAD_VISIBLE_SOLID, z=None):
        if angle is None:
            angle = self.rng.uniform(0, 2 * math.pi)
        if z is None:
            z = self.ground_z(x, y)
        self.doodads.append({'id': did, 'x': float(x), 'y': float(y), 'z': float(z),
                             'variation': var, 'scale': scale, 'angle': angle, 'flags': flags})

    def _place_doodads(self):
        rng = self.rng
        variations = {'LTlt': 10, 'FTtw': 10, 'ATtr': 5, 'CTtr': 5}
        self.tree_tiles = set()
        for ty in range(self.height):
            for tx in range(self.width):
                if self.in_margin_tile(tx, ty):
                    continue
                x, y = self.tile_center(tx, ty)
                dens, tree = self._tree_density(x, y)
                if rng.random() >= dens:
                    continue
                if self._blocked_for_trees(x, y, tx, ty):
                    continue
                self._add(tree, x, y, rng.randrange(variations[tree]),
                          round(rng.uniform(0.85, 1.15), 3), 4.712389)
                self.tree_tiles.add((tx, ty))

        def free_spot(x, y, r=96):
            tx = int((x + L.HALF_W) // 128)
            ty = int((y + L.HALF_H) // 128)
            if (tx, ty) in self.tree_tiles or self.in_margin_tile(tx, ty) or self.tile_is_cliff(tx, ty):
                return False
            if self.road_distance(x, y) < 40:
                return False
            return self.ground_z(x, y) > -40

        # flowers and shrubs in the open countryside
        for _ in range(900):
            x = rng.uniform(L.PLAY_MIN_X + 400, L.PLAY_MAX_X - 400)
            y = rng.uniform(L.PLAY_MIN_Y + 400, L.PLAY_MAX_Y - 400)
            if not free_spot(x, y) or math.hypot(x - L.CITADEL[0], y - L.CITADEL[1]) < 2000:
                continue
            if math.hypot(x - L.TOWN[0], y - L.TOWN[1]) < 900:
                continue
            if rng.random() < 0.6:
                self._add('ZPfw', x, y, rng.randrange(5), round(rng.uniform(0.8, 1.2), 3))
            else:
                self._add('ZPsh', x, y, rng.randrange(3), round(rng.uniform(0.8, 1.2), 3))

        # reeds along the river and lakes
        for _ in range(2600):
            x = rng.uniform(L.PLAY_MIN_X + 300, L.PLAY_MAX_X - 300)
            y = rng.uniform(L.PLAY_MIN_Y + 300, L.PLAY_MAX_Y - 300)
            z = self.ground_z(x, y)
            if -105 < z < -60 and ford_factor(x) < 0.2:
                if rng.random() < 0.7:
                    self._add('LPrs', x, y, rng.randrange(4), round(rng.uniform(0.8, 1.2), 3))
                else:
                    self._add('APct', x, y, 0, round(rng.uniform(0.8, 1.2), 3))
            elif z < -170 and rng.random() < 0.08:
                self._add('LPfp', x, y, rng.randrange(3), 1.0, z=WATER_Z)

        # bones and scorched remains in the blight
        for _ in range(400):
            a = rng.uniform(0, 2 * math.pi)
            r = rng.uniform(600, L.CITADEL_RADIUS + 300)
            x = L.CITADEL[0] + r * math.cos(a)
            y = L.CITADEL[1] + r * math.sin(a)
            if y > L.PLAY_MAX_Y - 300 or not free_spot(x, y):
                continue
            if rng.random() < 0.6:
                self._add('LOrb', x, y, rng.randrange(4), round(rng.uniform(0.8, 1.2), 3))
            else:
                self._add('AOsr', x, y, rng.randrange(3), round(rng.uniform(0.8, 1.2), 3))
        for _ in range(70):
            x = -3328 + rng.uniform(-650, 650)
            y = 4608 + rng.uniform(-650, 650)
            if free_spot(x, y):
                self._add('LOrb', x, y, rng.randrange(4), round(rng.uniform(0.8, 1.2), 3))

        # rocks at the quarry and the dragon roost (destructible rock chunks)
        for cx, cy, n in ((3328, 4608, 14), (-5760, 5760, 10)):
            for _ in range(n):
                x = cx + rng.uniform(-750, 750)
                y = cy + rng.uniform(-750, 750)
                if math.hypot(x - cx, y - cy) < 420 or not free_spot(x, y):
                    continue
                self._add('LTrc', x, y, rng.randrange(6), 1.0)

        # crates and barrels at the bandit camp and in town
        for cx, cy, n in ((5888, 2304, 8), (0, -5568, 6)):
            for _ in range(n):
                a = rng.uniform(0, 2 * math.pi)
                r = rng.uniform(560, 760) if cx else rng.uniform(900, 1050)
                x, y = cx + r * math.cos(a), cy + r * math.sin(a)
                if not free_spot(x, y) or self.road_distance(x, y) < 60:
                    continue
                self._add(rng.choice(('LTcr', 'LTbr', 'LTbx')), x, y,
                          rng.randrange(2) if False else 0, 1.0)

        # torches around the plaza and the outposts, signposts at crossings
        for i in range(10):
            a = 2 * math.pi * i / 10 + 0.3
            self._add('LOtz', L.TOWN[0] + 880 * math.cos(a), L.TOWN[1] + 880 * math.sin(a), 0, 1.0)
        for o in L.OUTPOSTS:
            for i in range(4):
                a = math.pi / 4 + i * math.pi / 2
                self._add('LOth', o['pos'][0] + 300 * math.cos(a), o['pos'][1] + 300 * math.sin(a), 0, 1.0)
        for sx, sy in L.SIGNPOSTS:
            self._add('LOsp', sx, sy, 0, 1.0)
        # hay and wheat by the farms
        for _ in range(30):
            x = rng.uniform(1100, 1900)
            y = rng.uniform(-6500, -5800)
            if free_spot(x, y):
                self._add(rng.choice(('LOhc', 'LPwh')), x, y, 0, round(rng.uniform(0.8, 1.2), 3))

    # -- sanity checks ----------------------------------------------------

    def _validate_layout(self):
        def check(name, x, y, r):
            if not self.area_walkable(x, y, r):
                self.warnings.append('%s at (%d, %d) is not walkable' % (name, x, y))
            tx = int((x + L.HALF_W) // 128)
            ty = int((y + L.HALF_H) // 128)
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    if (tx + dx, ty + dy) in self.tree_tiles and math.hypot(dx, dy) * 128 < r:
                        self.warnings.append('%s at (%d, %d) has trees inside' % (name, x, y))
                        return

        for i, b in enumerate(L.BASES):
            check('base %d hall' % i, *b['hall'], 300)
            check('base %d mine' % i, *b['mine'], 260)
        for s in L.TOWN_STRUCTURES:
            check('town ' + s[0], s[1], s[2], 200)
        for o in L.OUTPOSTS:
            check('outpost ' + o['name'], *o['pos'], 250)
        for c in L.CAMPS:
            check('camp ' + c['name'], *c['pos'], 200)
        for b in L.BOSSES:
            check('boss ' + b['name'], *b['pos'], 250)
        for s in L.SCOURGE_STRUCTURES:
            check('scourge ' + s[0], s[1], s[2], 200)
        check('raid spawn', *L.RAID_SPAWN, 250)
        check('lich', *L.LICH_POS, 150)
        # every point of interest must be reachable from the town on foot
        self._check_reachability()

    def _check_reachability(self):
        pw, ph = self.width * 4, self.height * 4
        start = (int((L.MILITIA_RALLY[0] + L.HALF_W) // 32), int((L.MILITIA_RALLY[1] + L.HALF_H) // 32))
        blocked = bytearray(pw * ph)
        for i, v in enumerate(self.pathing):
            if v & F.PATH_NO_WALK:
                blocked[i] = 1
        for (tx, ty) in self.tree_tiles:
            for sy in range(4):
                for sx in range(4):
                    blocked[(ty * 4 + sy) * pw + tx * 4 + sx] = 1
        seen = bytearray(pw * ph)
        stack = [start]
        seen[start[1] * pw + start[0]] = 1
        while stack:
            x, y = stack.pop()
            for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if 0 <= nx < pw and 0 <= ny < ph:
                    i = ny * pw + nx
                    if not seen[i] and not blocked[i]:
                        seen[i] = 1
                        stack.append((nx, ny))
        self.reachable = seen

        def reach(name, x, y):
            cx, cy = int((x + L.HALF_W) // 32), int((y + L.HALF_H) // 32)
            ok = any(seen[(cy + dy) * pw + cx + dx] for dy in range(-6, 7) for dx in range(-6, 7)
                     if 0 <= cx + dx < pw and 0 <= cy + dy < ph)
            if not ok:
                self.warnings.append('%s at (%d, %d) is not reachable from town' % (name, x, y))

        for i, b in enumerate(L.BASES):
            reach('base %d' % i, *b['hall'])
        for o in L.OUTPOSTS:
            reach('outpost ' + o['name'], *o['pos'])
        for c in L.CAMPS:
            reach('camp ' + c['name'], *c['pos'])
        for b in L.BOSSES:
            reach('boss ' + b['name'], *b['pos'])
        reach('citadel', *L.RAID_SPAWN)

    # -- images -----------------------------------------------------------

    def render(self, size, markers=False):
        """Top-down picture of the map (playable area), rows from the top."""
        x0, y0, x1, y1 = L.PLAY_MIN_X, L.PLAY_MIN_Y, L.PLAY_MAX_X, L.PLAY_MAX_Y
        tree_cells = self.tree_tiles
        px = []
        for row in range(size):
            y = y1 - (row + 0.5) * (y1 - y0) / size
            for col in range(size):
                x = x0 + (col + 0.5) * (x1 - x0) / size
                tx = int((x + L.HALF_W) // 128)
                ty = int((y + L.HALF_H) // 128)
                c = self.corners[ty][tx]
                r, g, b = TEXTURE_COLOURS[c.texture]
                if c.blight:
                    r, g, b = (96, 78, 96)
                z = self.ground_z(x, y)
                depth = WATER_Z - z
                if depth > 0:
                    k = min(1.0, depth / 170.0)
                    r, g, b = int(60 - 30 * k), int(110 - 40 * k), int(150 - 10 * k)
                else:
                    shade = 1.0 + max(-0.25, min(0.35, z / 300.0))
                    r, g, b = int(r * shade), int(g * shade), int(b * shade)
                if self.tile_is_cliff(tx, ty):
                    r, g, b = (70, 62, 54)
                if (tx, ty) in tree_cells:
                    r, g, b = (28, 64, 30) if c.texture != T_ROUGH or not c.blight else (60, 50, 70)
                px.append((max(0, min(255, r)), max(0, min(255, g)), max(0, min(255, b))))
        if markers:
            self._draw_markers(px, size)
        return px

    def _draw_markers(self, px, size):
        x0, y0, x1, y1 = L.PLAY_MIN_X, L.PLAY_MIN_Y, L.PLAY_MAX_X, L.PLAY_MAX_Y

        def dot(x, y, colour, radius):
            col = int((x - x0) / (x1 - x0) * size)
            row = int((y1 - y) / (y1 - y0) * size)
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if dx * dx + dy * dy <= radius * radius:
                        r2, c2 = row + dy, col + dx
                        if 0 <= r2 < size and 0 <= c2 < size:
                            px[r2 * size + c2] = colour

        k = max(2, size // 128)
        colours = [(255, 3, 3), (0, 66, 255), (28, 230, 185), (84, 0, 129)]
        for i, b in enumerate(L.BASES):
            dot(*b['hall'], colours[i], 2 * k)
            dot(*b['mine'], (255, 215, 0), k)
        dot(*L.CASTLE, (255, 252, 1), 3 * k)
        for o in L.OUTPOSTS:
            dot(*o['pos'], (255, 255, 255), 2 * k)
            dot(*o['pos'], (40, 40, 40), k)
        for c in L.CAMPS:
            dot(*c['pos'], (230, 120, 40), k)
        for b in L.BOSSES:
            dot(*b['pos'], (200, 0, 0), 2 * k)
        dot(*L.CITADEL, (40, 230, 40), 3 * k)

    def minimap_icons(self):
        span = max(L.PLAY_MAX_X - L.PLAY_MIN_X, L.PLAY_MAX_Y - L.PLAY_MIN_Y)
        ox = (span - (L.PLAY_MAX_X - L.PLAY_MIN_X)) / 2.0
        oy = (span - (L.PLAY_MAX_Y - L.PLAY_MIN_Y)) / 2.0

        def mm(x, y):
            # the minimap shows the playable area, letterboxed into 256 x 256
            return (round((ox + x - L.PLAY_MIN_X) / span * 256.0),
                    round((oy + L.PLAY_MAX_Y - y) / span * 256.0))
        icons = []
        for b in L.BASES:
            icons.append((F.MINIMAP_GOLDMINE, *mm(*b['mine']), (255, 255, 255)))
        colours = [(255, 3, 3), (0, 66, 255), (28, 230, 185), (84, 0, 129)]
        for i, b in enumerate(L.BASES):
            icons.append((F.MINIMAP_CROSS, *mm(*b['hall']), colours[i]))
        return icons

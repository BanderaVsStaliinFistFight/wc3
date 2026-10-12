"""Encoders for the files inside a Warcraft III (The Frozen Throne) map archive.

Every encoder writes the classic TFT format version (the one World Editor
1.26 produces) because every later game version, Reforged included, still
reads it.
"""

import struct


class Writer:
    def __init__(self):
        self.buf = bytearray()

    def i32(self, v):
        self.buf += struct.pack('<i', v)

    def u32(self, v):
        self.buf += struct.pack('<I', v)

    def i16(self, v):
        self.buf += struct.pack('<h', v)

    def u16(self, v):
        self.buf += struct.pack('<H', v)

    def u8(self, v):
        self.buf += struct.pack('<B', v)

    def f32(self, v):
        self.buf += struct.pack('<f', v)

    def id4(self, s):
        b = s.encode('ascii')
        if len(b) != 4:
            raise ValueError('bad id %r' % s)
        self.buf += b

    def char(self, s):
        self.buf += s.encode('ascii')[:1]

    def string(self, s):
        self.buf += s.encode('utf-8') + b'\0'

    def raw(self, b):
        self.buf += b

    def bytes(self):
        return bytes(self.buf)


# ---------------------------------------------------------------------------
# war3map.w3i
# ---------------------------------------------------------------------------

W3I_HIDE_MINIMAP = 0x0001
W3I_MODIFY_ALLY_PRIORITIES = 0x0002
W3I_MELEE = 0x0004
W3I_MASKED_PARTIALLY_VISIBLE = 0x0010
W3I_FIXED_PLAYER_SETTINGS = 0x0020
W3I_CUSTOM_FORCES = 0x0040
W3I_PROPERTIES_OPENED = 0x0400
W3I_WAVES_CLIFF = 0x0800
W3I_WAVES_ROLLING = 0x1000
W3I_REQUIRES_EXPANSION = 0x4000
W3I_ITEM_CLASSIFICATION = 0x8000

PLAYER_USER = 1
PLAYER_COMPUTER = 2
RACE_HUMAN, RACE_ORC, RACE_UNDEAD, RACE_NIGHTELF = 1, 2, 3, 4

FORCE_ALLIED = 0x01
FORCE_ALLIED_VICTORY = 0x02
FORCE_SHARE_VISION = 0x08
FORCE_SHARE_UNIT_CONTROL = 0x10


def w3i(info):
    w = Writer()
    w.i32(25)                       # TFT format
    w.i32(info.get('saves', 1))
    w.i32(info.get('editor_version', 6059))
    w.string(info['name'])
    w.string(info['author'])
    w.string(info['description'])
    w.string(info['players_recommended'])
    for v in info['camera_bounds']:
        w.f32(v)
    for v in info['bounds_complements']:
        w.i32(v)
    w.i32(info['playable_width'])
    w.i32(info['playable_height'])
    w.u32(info['flags'])
    w.char(info['tileset'])
    w.i32(-1)                       # loading screen background (none)
    w.string('')                    # custom loading screen model
    w.string(info.get('loading_text', ''))
    w.string(info.get('loading_title', ''))
    w.string(info.get('loading_subtitle', ''))
    w.i32(0)                        # game data set: default
    w.string('')                    # prologue screen path
    w.string('')                    # prologue text
    w.string('')                    # prologue title
    w.string('')                    # prologue subtitle
    w.i32(0)                        # terrain fog: none
    w.f32(3000.0)
    w.f32(5000.0)
    w.f32(0.5)
    w.raw(bytes([0, 0, 0, 255]))    # fog colour (BGRA)
    w.i32(0)                        # global weather: none
    w.string('')                    # sound environment
    w.raw(b'\0')                    # light environment: tileset default
    w.raw(bytes([255, 255, 255, 255]))  # water tint (BGRA)
    w.i32(len(info['players']))
    for p in info['players']:
        w.i32(p['id'])
        w.i32(p['type'])
        w.i32(p['race'])
        w.i32(1 if p.get('fixed_start', True) else 0)
        w.string(p['name'])
        w.f32(p['start'][0])
        w.f32(p['start'][1])
        w.u32(p.get('ally_low', 0))
        w.u32(p.get('ally_high', 0))
    w.i32(len(info['forces']))
    for f in info['forces']:
        w.u32(f['flags'])
        w.u32(f['players'])
        w.string(f['name'])
    w.i32(0)    # upgrade availability changes
    w.i32(0)    # tech availability changes
    w.i32(0)    # random unit tables
    w.i32(0)    # random item tables
    return w.bytes()


# ---------------------------------------------------------------------------
# war3map.w3e
# ---------------------------------------------------------------------------

def w3e(terrain):
    """terrain: object with tileset, ground_tiles, cliff_tiles, width, height
    (in tiles), corners[y][x] dicts."""
    w = Writer()
    w.raw(b'W3E!')
    w.i32(11)
    w.char(terrain.tileset)
    w.i32(1 if terrain.custom_tileset else 0)
    w.i32(len(terrain.ground_tiles))
    for t in terrain.ground_tiles:
        w.id4(t)
    w.i32(len(terrain.cliff_tiles))
    for t in terrain.cliff_tiles:
        w.id4(t)
    w.i32(terrain.width + 1)
    w.i32(terrain.height + 1)
    w.f32(-64.0 * terrain.width)
    w.f32(-64.0 * terrain.height)
    for row in terrain.corners:
        for c in row:
            w.u16(c.height)
            w.u16((c.water & 0x3FFF) | (0x4000 if c.edge else 0))
            flags = (0x10 if c.ramp else 0) | (0x20 if c.blight else 0) | \
                    (0x40 if c.is_water else 0) | (0x80 if c.boundary else 0)
            w.u8(flags | (c.texture & 0x0F))
            w.u8(((c.cliff_variation & 0x07) << 5) | (c.variation & 0x1F))
            w.u8(((c.cliff_texture & 0x0F) << 4) | (c.layer & 0x0F))
    return w.bytes()


# ---------------------------------------------------------------------------
# war3map.wpm / war3map.shd
# ---------------------------------------------------------------------------

PATH_NO_WALK = 0x02
PATH_NO_FLY = 0x04
PATH_NO_BUILD = 0x08
PATH_BLIGHT = 0x20
PATH_NO_WATER = 0x40


def wpm(width, height, cells):
    """cells: bytes/bytearray of size (4*width)*(4*height), row-major from the bottom."""
    w = Writer()
    w.raw(b'MP3W')
    w.i32(0)
    w.i32(width * 4)
    w.i32(height * 4)
    if len(cells) != width * height * 16:
        raise ValueError('pathing map has wrong size')
    w.raw(bytes(cells))
    return w.bytes()


def shd(width, height):
    return bytes(width * height * 16)


# ---------------------------------------------------------------------------
# war3map.doo (doodads / destructables)
# ---------------------------------------------------------------------------

DOODAD_VISIBLE_SOLID = 2


def doo(doodads):
    w = Writer()
    w.raw(b'W3do')
    w.i32(8)
    w.i32(11)
    w.i32(len(doodads))
    for n, d in enumerate(doodads):
        w.id4(d['id'])
        w.i32(d.get('variation', 0))
        w.f32(d['x'])
        w.f32(d['y'])
        w.f32(d['z'])
        w.f32(d.get('angle', 4.712389))
        s = d.get('scale', 1.0)
        w.f32(s)
        w.f32(s)
        w.f32(s)
        w.u8(d.get('flags', DOODAD_VISIBLE_SOLID))
        w.u8(d.get('life', 100))
        w.i32(-1)       # map item table pointer
        w.i32(0)        # dropped item sets
        w.i32(n)        # editor id
    w.i32(0)            # special doodads version
    w.i32(0)            # special doodads count
    return w.bytes()


# ---------------------------------------------------------------------------
# war3mapUnits.doo (only start locations: units are created by the script)
# ---------------------------------------------------------------------------

def units_doo(units):
    """Start locations ('sloc') are written the way the World Editor does."""
    w = Writer()
    w.raw(b'W3do')
    w.i32(8)
    w.i32(11)
    w.i32(len(units))
    for n, u in enumerate(units):
        w.id4(u['id'])
        w.i32(0)                    # variation
        w.f32(u['x'])
        w.f32(u['y'])
        w.f32(u.get('z', 0.0))
        w.f32(u.get('angle', 4.712389))
        w.f32(1.0)
        w.f32(1.0)
        w.f32(1.0)
        sloc = u['id'] == 'sloc'
        w.u8(2)                     # flags
        w.i32(u['player'])
        w.u8(0)
        w.u8(0)
        w.i32(0 if sloc else -1)    # hit points (-1 = default)
        w.i32(0 if sloc else -1)    # mana (-1 = default)
        w.i32(-1)                   # item table pointer
        w.i32(0)                    # dropped item sets
        w.i32(0 if sloc else 12500)  # gold amount
        w.f32(0.0 if sloc else -1.0)  # target acquisition
        w.i32(0 if sloc else 1)     # hero level
        w.i32(0)                    # strength
        w.i32(0)                    # agility
        w.i32(0)                    # intelligence
        w.i32(0)                    # inventory items
        w.i32(0)                    # modified abilities
        w.i32(0)                    # random flag: none
        w.raw(b'\x01\x00\x00\x00')  # random level (24 bit) + item class
        w.i32(-1)                   # custom colour
        w.i32(-1)                   # waygate destination
        w.i32(n)                    # creation number
    return w.bytes()


# ---------------------------------------------------------------------------
# Small editor-side files
# ---------------------------------------------------------------------------

MINIMAP_GOLDMINE = 0
MINIMAP_HOUSE = 1
MINIMAP_CROSS = 2


def mmp(icons):
    """icons: list of (type, x, y, (r, g, b)) with x, y in 0..255 minimap space."""
    w = Writer()
    w.i32(0)
    w.i32(len(icons))
    for kind, x, y, (r, g, b) in icons:
        w.i32(kind)
        w.i32(int(x))
        w.i32(int(y))
        w.raw(bytes([b, g, r, 255]))
    return w.bytes()


def w3r():
    w = Writer()
    w.i32(5)
    w.i32(0)
    return w.bytes()


def w3c():
    w = Writer()
    w.i32(0)
    w.i32(0)
    return w.bytes()


def w3s():
    w = Writer()
    w.i32(1)
    w.i32(0)
    return w.bytes()


def wtg(category, trigger_name, description):
    """A trigger file holding one custom-text trigger, so the World Editor
    can open the map and keep the script when the map is saved again."""
    w = Writer()
    w.raw(b'WTG!')
    w.i32(7)
    w.i32(1)            # categories
    w.i32(0)            # category id
    w.string(category)
    w.i32(0)            # not a comment
    w.i32(2)            # game version (TFT)
    w.i32(0)            # variables
    w.i32(1)            # triggers
    w.string(trigger_name)
    w.string(description)
    w.i32(0)            # not a comment
    w.i32(1)            # enabled
    w.i32(1)            # custom text
    w.i32(0)            # initially on
    w.i32(0)            # run on map init
    w.i32(0)            # category id
    w.i32(0)            # no GUI functions
    return w.bytes()


def wct(custom_script_comment, custom_script, trigger_texts):
    w = Writer()
    w.i32(1)
    w.string(custom_script_comment)
    for text in [custom_script] + [None] + list(trigger_texts):
        if text is None:
            w.i32(len(trigger_texts))
            continue
        data = text.encode('utf-8')
        if data:
            w.i32(len(data) + 1)
            w.raw(data + b'\0')
        else:
            w.i32(0)
    return w.bytes()


def wts(strings):
    out = []
    for n, s in strings:
        out.append('STRING %d\r\n{\r\n%s\r\n}\r\n\r\n' % (n, s))
    return '﻿' + ''.join(out)


# ---------------------------------------------------------------------------
# Images: war3mapMap.blp (minimap) and a PNG preview for the README
# ---------------------------------------------------------------------------

def _palette_index(r, g, b):
    # 6x7x6 colour cube (252 entries)
    return (r * 6 // 256) * 42 + (g * 7 // 256) * 6 + (b * 6 // 256)


def _palette():
    pal = []
    for ri in range(6):
        for gi in range(7):
            for bi in range(6):
                pal.append((ri * 255 // 5, gi * 255 // 6, bi * 255 // 5))
    while len(pal) < 256:
        pal.append((0, 0, 0))
    return pal


def _downsample(pixels, size):
    half = size // 2
    out = []
    for y in range(half):
        for x in range(half):
            acc = [0, 0, 0]
            for dy in (0, 1):
                for dx in (0, 1):
                    p = pixels[(2 * y + dy) * size + 2 * x + dx]
                    acc[0] += p[0]
                    acc[1] += p[1]
                    acc[2] += p[2]
            out.append((acc[0] // 4, acc[1] // 4, acc[2] // 4))
    return out


def blp1_paletted(pixels, size):
    """pixels: list of (r, g, b) rows top-to-bottom, size x size, size a power of two."""
    pal = _palette()
    mips = []
    cur = pixels
    cur_size = size
    while True:
        idx = bytes(_palette_index(*p) for p in cur)
        alpha = bytes([255]) * len(cur)
        mips.append(idx + alpha)
        if cur_size == 1:
            break
        cur = _downsample(cur, cur_size)
        cur_size //= 2
    header_size = 156 + 1024
    offsets = []
    sizes = []
    pos = header_size
    for m in mips:
        offsets.append(pos)
        sizes.append(len(m))
        pos += len(m)
    offsets += [0] * (16 - len(offsets))
    sizes += [0] * (16 - len(sizes))
    w = Writer()
    w.raw(b'BLP1')
    w.u32(1)        # paletted
    w.u32(8)        # alpha bits
    w.u32(size)
    w.u32(size)
    w.u32(4)        # picture type: index list + alpha list
    w.u32(1)        # has mipmaps
    for o in offsets:
        w.u32(o)
    for s in sizes:
        w.u32(s)
    for r, g, b in pal:
        w.raw(bytes([b, g, r, 0]))
    for m in mips:
        w.raw(m)
    return w.bytes()


def png(pixels, width, height):
    import zlib

    def chunk(kind, data):
        return (struct.pack('>I', len(data)) + kind + data
                + struct.pack('>I', zlib.crc32(kind + data) & 0xFFFFFFFF))
    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw += bytes(pixels[y * width + x])
    return (b'\x89PNG\r\n\x1a\n'
            + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(bytes(raw), 9))
            + chunk(b'IEND', b''))


def map_header(name, flags, max_players):
    """The 512-byte HM3W header that precedes the MPQ archive in a .w3x file."""
    w = Writer()
    w.raw(b'HM3W')
    w.i32(0)
    w.string(name)
    w.u32(flags)
    w.i32(max_players)
    data = w.bytes()
    return data + bytes(512 - len(data))

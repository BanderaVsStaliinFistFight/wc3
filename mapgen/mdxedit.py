"""Reading, editing and writing Warcraft III MDX models (version 800).

Everything the editing needs is parsed into plain objects -- geosets,
geoset animations, materials, textures, sequences, pivots, cameras and the
generic part of every node (name, ids, translation/rotation/scaling tracks).
The rest of each chunk is kept as raw bytes, so a model reads and writes
back byte for byte.
"""

import struct

NODE_CHUNKS = ('BONE', 'LITE', 'HELP', 'ATCH', 'PREM', 'PRE2', 'RIBB', 'EVTS', 'CLID')
TRACK_SIZES = {b'KGTR': 3, b'KGRT': 4, b'KGSC': 3}


class Reader:
    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos

    def u32(self):
        v = struct.unpack_from('<I', self.data, self.pos)[0]
        self.pos += 4
        return v

    def i32(self):
        v = struct.unpack_from('<i', self.data, self.pos)[0]
        self.pos += 4
        return v

    def f32(self, n=1):
        v = struct.unpack_from('<%df' % n, self.data, self.pos)
        self.pos += 4 * n
        return v if n > 1 else v[0]

    def raw(self, n):
        v = self.data[self.pos:self.pos + n]
        self.pos += n
        return v

    def tag(self):
        return self.raw(4)


def _name(raw):
    return raw.split(b'\0', 1)[0].decode('latin-1')


def _pad(text, n):
    b = text.encode('latin-1')
    if len(b) >= n:
        raise ValueError('name too long: %r' % text)
    return b + bytes(n - len(b))


class Track:
    """An animation track: keys are [frame, value, in tangent, out tangent]."""

    def __init__(self, tag, interpolation, global_sequence, keys):
        self.tag, self.interpolation, self.global_sequence, self.keys = tag, interpolation, global_sequence, keys

    @classmethod
    def read(cls, r, tag, size):
        count, interp, gseq = r.u32(), r.u32(), r.i32()
        keys = []
        for _ in range(count):
            frame = r.i32()
            value = r.f32(size) if size > 1 else (r.f32(),)
            tans = (r.f32(size) if size > 1 else (r.f32(),), r.f32(size) if size > 1 else (r.f32(),)) \
                if interp > 1 else (None, None)
            keys.append([frame, tuple(value), tans[0] and tuple(tans[0]), tans[1] and tuple(tans[1])])
        return cls(tag, interp, gseq, keys)

    def write(self):
        out = self.tag + struct.pack('<IIi', len(self.keys), self.interpolation, self.global_sequence)
        for frame, value, tin, tout in self.keys:
            out += struct.pack('<i', frame) + struct.pack('<%df' % len(value), *value)
            if self.interpolation > 1:
                out += struct.pack('<%df' % len(tin), *tin) + struct.pack('<%df' % len(tout), *tout)
        return out


class Node:
    """The generic part of every node: name, ids, flags and its transform tracks."""

    def __init__(self, name, object_id, parent, flags, tracks):
        self.name, self.object_id, self.parent, self.flags, self.tracks = name, object_id, parent, flags, tracks

    @classmethod
    def read(cls, r):
        start = r.pos
        size = r.u32()
        name = _name(r.raw(80))
        object_id, parent, flags = r.i32(), r.i32(), r.u32()
        tracks = []
        while r.pos < start + size:
            tag = r.tag()
            tracks.append(Track.read(r, tag, TRACK_SIZES[tag]))
        return cls(name, object_id, parent, flags, tracks)

    def write(self):
        body = _pad(self.name, 80) + struct.pack('<iiI', self.object_id, self.parent, self.flags)
        body += b''.join(t.write() for t in self.tracks)
        return struct.pack('<I', 4 + len(body)) + body

    def track(self, tag):
        for t in self.tracks:
            if t.tag == tag:
                return t
        return None


class NodeEntry:
    """A node plus the type specific data around it. Chunks whose entries
    carry their own size (attachments, emitters, lights) keep it in `outer`."""

    def __init__(self, kind, node, tail, outer):
        self.kind, self.node, self.tail, self.outer = kind, node, tail, outer

    @classmethod
    def read(cls, r, kind):
        if kind in ('ATCH', 'PREM', 'PRE2', 'RIBB', 'LITE'):
            start = r.pos
            size = r.u32()
            node = Node.read(r)
            tail = r.raw(start + size - r.pos)
            return cls(kind, node, tail, True)
        node = Node.read(r)
        if kind == 'BONE':
            tail = r.raw(8)
        elif kind == 'HELP':
            tail = b''
        elif kind == 'EVTS':
            start = r.pos
            r.tag()
            count = r.u32()
            r.raw(4 + 4 * count)
            tail = r.data[start:r.pos]
        elif kind == 'CLID':
            start = r.pos
            shape = r.u32()
            r.raw(12 if shape == 2 else 24)
            if shape in (2, 3):
                r.raw(4)
            tail = r.data[start:r.pos]
        else:
            raise ValueError(kind)
        return cls(kind, node, tail, False)

    def write(self):
        body = self.node.write() + self.tail
        return struct.pack('<I', 4 + len(body)) + body if self.outer else body

    # bones: the geoset and geoset animation they belong to
    @property
    def bone_geoset(self):
        return struct.unpack_from('<ii', self.tail)

    def set_bone_geoset(self, geoset, geoset_animation=-1):
        self.tail = struct.pack('<ii', geoset, geoset_animation)

    # collision shapes: their points
    def collision(self):
        shape = struct.unpack_from('<I', self.tail)[0]
        n = 1 if shape == 2 else 2
        pts = [struct.unpack_from('<3f', self.tail, 4 + 12 * i) for i in range(n)]
        radius = struct.unpack_from('<f', self.tail, 4 + 12 * n)[0] if shape in (2, 3) else None
        return shape, pts, radius

    def set_collision(self, shape, pts, radius):
        self.tail = struct.pack('<I', shape) + b''.join(struct.pack('<3f', *p) for p in pts) + \
            (struct.pack('<f', radius) if radius is not None else b'')


EXTENT = struct.Struct('<7f')


class Geoset:
    def __init__(self):
        self.vertices, self.normals, self.uvs = [], [], []
        self.faces = []                 # triangles
        self.vertex_groups = []         # matrix group index per vertex
        self.groups = []                # lists of node object ids
        self.material = 0
        self.selection_group = 0
        self.selection_flags = 0
        self.extent = (0.0,) * 7
        self.sequence_extents = []
        self.extra_uv_sets = []

    @classmethod
    def read(cls, r):
        g = cls()
        r.u32()                         # size
        assert r.tag() == b'VRTX'
        n = r.u32()
        flat = r.f32(3 * n) if n else ()
        g.vertices = [tuple(flat[i:i + 3]) for i in range(0, 3 * n, 3)]
        assert r.tag() == b'NRMS'
        n = r.u32()
        flat = r.f32(3 * n) if n else ()
        g.normals = [tuple(flat[i:i + 3]) for i in range(0, 3 * n, 3)]
        assert r.tag() == b'PTYP'
        types = [r.u32() for _ in range(r.u32())]
        assert r.tag() == b'PCNT'
        counts = [r.u32() for _ in range(r.u32())]
        if any(t != 4 for t in types):
            raise ValueError('only triangle lists are supported')
        assert r.tag() == b'PVTX'
        n = r.u32()
        idx = struct.unpack_from('<%dH' % n, r.data, r.pos)
        r.pos += 2 * n
        assert sum(counts) == n
        g.faces = [tuple(idx[i:i + 3]) for i in range(0, n, 3)]
        assert r.tag() == b'GNDX'
        n = r.u32()
        g.vertex_groups = list(r.raw(n))
        assert r.tag() == b'MTGC'
        sizes = [r.u32() for _ in range(r.u32())]
        assert r.tag() == b'MATS'
        n = r.u32()
        flat = [r.u32() for _ in range(n)]
        pos = 0
        for s in sizes:
            g.groups.append(flat[pos:pos + s])
            pos += s
        g.material, g.selection_group, g.selection_flags = r.u32(), r.u32(), r.u32()
        g.extent = EXTENT.unpack(r.raw(28))
        g.sequence_extents = [EXTENT.unpack(r.raw(28)) for _ in range(r.u32())]
        assert r.tag() == b'UVAS'
        sets = r.u32()
        for k in range(sets):
            assert r.tag() == b'UVBS'
            n = r.u32()
            flat = r.f32(2 * n) if n else ()
            uv = [tuple(flat[i:i + 2]) for i in range(0, 2 * n, 2)]
            if k == 0:
                g.uvs = uv
            else:
                g.extra_uv_sets.append(uv)
        return g

    def write(self):
        n = len(self.vertices)
        idx = [i for f in self.faces for i in f]
        flat_groups = [b for grp in self.groups for b in grp]
        body = (b'VRTX' + struct.pack('<I', n) + b''.join(struct.pack('<3f', *v) for v in self.vertices)
                + b'NRMS' + struct.pack('<I', n) + b''.join(struct.pack('<3f', *v) for v in self.normals)
                + b'PTYP' + struct.pack('<II', 1, 4)
                + b'PCNT' + struct.pack('<II', 1, len(idx))
                + b'PVTX' + struct.pack('<I', len(idx)) + struct.pack('<%dH' % len(idx), *idx)
                + b'GNDX' + struct.pack('<I', n) + bytes(self.vertex_groups)
                + b'MTGC' + struct.pack('<I', len(self.groups)) + b''.join(struct.pack('<I', len(g))
                                                                          for g in self.groups)
                + b'MATS' + struct.pack('<I', len(flat_groups)) + b''.join(struct.pack('<I', b) for b in flat_groups)
                + struct.pack('<III', self.material, self.selection_group, self.selection_flags)
                + EXTENT.pack(*self.extent)
                + struct.pack('<I', len(self.sequence_extents))
                + b''.join(EXTENT.pack(*e) for e in self.sequence_extents)
                + b'UVAS' + struct.pack('<I', 1 + len(self.extra_uv_sets)))
        for uv in [self.uvs] + self.extra_uv_sets:
            body += b'UVBS' + struct.pack('<I', len(uv)) + b''.join(struct.pack('<2f', *t) for t in uv)
        return struct.pack('<I', 4 + len(body)) + body

    def bones_of(self, vertex):
        return self.groups[self.vertex_groups[vertex]]


class GeosetAnimation:
    def __init__(self, geoset, alpha=1.0, color=(1.0, 1.0, 1.0), flags=0, tracks=b''):
        self.geoset, self.alpha, self.color, self.flags, self.tracks = geoset, alpha, color, flags, tracks

    @classmethod
    def read(cls, r):
        start = r.pos
        size = r.u32()
        alpha, flags = r.f32(), r.u32()
        color = r.f32(3)
        geoset = r.i32()
        tracks = r.raw(start + size - r.pos)
        return cls(geoset, alpha, tuple(color), flags, tracks)

    def write(self):
        body = struct.pack('<fI3fi', self.alpha, self.flags, *self.color, self.geoset) + self.tracks
        return struct.pack('<I', 4 + len(body)) + body


class Texture:
    def __init__(self, path='', replaceable=0, flags=0):
        self.path, self.replaceable, self.flags = path, replaceable, flags

    @classmethod
    def read(cls, r):
        replaceable = r.u32()
        path = _name(r.raw(260))
        return cls(path, replaceable, r.u32())

    def write(self):
        return struct.pack('<I', self.replaceable) + _pad(self.path, 260) + struct.pack('<I', self.flags)


class Sequence:
    def __init__(self, raw):
        self.name = _name(raw[:80])
        self.start, self.end, self.move_speed, self.flags, self.rarity, self.sync = \
            struct.unpack_from('<IIfIfI', raw, 80)
        self.extent = EXTENT.unpack_from(raw, 104)

    def write(self):
        return (_pad(self.name, 80) + struct.pack('<IIfIfI', self.start, self.end, self.move_speed, self.flags,
                                                   self.rarity, self.sync) + EXTENT.pack(*self.extent))


class Camera:
    def __init__(self, raw):
        self.name = _name(raw[4:84])
        self.position = struct.unpack_from('<3f', raw, 84)
        self.fov, self.far, self.near = struct.unpack_from('<3f', raw, 96)
        self.target = struct.unpack_from('<3f', raw, 108)
        self.tracks = raw[120:]

    def write(self):
        body = (_pad(self.name, 80) + struct.pack('<3f', *self.position)
                + struct.pack('<3f', self.fov, self.far, self.near) + struct.pack('<3f', *self.target) + self.tracks)
        return struct.pack('<I', 4 + len(body)) + body


def _sized_entries(data):
    """Splits a chunk into entries that start with their own inclusive size."""
    out, pos = [], 0
    while pos < len(data):
        size = struct.unpack_from('<I', data, pos)[0]
        out.append(data[pos:pos + size])
        pos += size
    return out


class Model:
    """A whole model. chunks keeps the chunk order; parsed chunks are
    regenerated from their objects when written."""

    def __init__(self, data):
        if data[:4] != b'MDLX':
            raise ValueError('not an MDX model')
        self.chunks = []
        pos = 4
        while pos < len(data):
            tag = data[pos:pos + 4].decode('latin-1')
            size = struct.unpack_from('<I', data, pos + 4)[0]
            self.chunks.append([tag, data[pos + 8:pos + 8 + size]])
            pos += 8 + size
        get = dict((t, d) for t, d in self.chunks)
        self.version = struct.unpack('<I', get['VERS'])[0]
        if self.version != 800:
            raise ValueError('only MDX version 800 is supported')
        modl = get['MODL']
        self.name = _name(modl[:80])
        self.animation_file = modl[80:340]
        self.extent = EXTENT.unpack_from(modl, 340)
        self.blend_time = struct.unpack_from('<I', modl, 368)[0]
        seqs = get.get('SEQS', b'')
        self.sequences = [Sequence(seqs[i:i + 132]) for i in range(0, len(seqs), 132)]
        self.materials = _sized_entries(get.get('MTLS', b''))     # raw, size-prefixed
        texs = get.get('TEXS', b'')
        self.textures = [Texture.read(Reader(texs, i)) for i in range(0, len(texs), 268)]
        self.geosets = []
        r = Reader(get.get('GEOS', b''))
        while r.pos < len(r.data):
            self.geosets.append(Geoset.read(r))
        self.geoset_animations = []
        r = Reader(get.get('GEOA', b''))
        while r.pos < len(r.data):
            self.geoset_animations.append(GeosetAnimation.read(r))
        self.nodes = {kind: [] for kind in NODE_CHUNKS}
        for kind in NODE_CHUNKS:
            r = Reader(get.get(kind, b''))
            while r.pos < len(r.data):
                self.nodes[kind].append(NodeEntry.read(r, kind))
        pivt = get.get('PIVT', b'')
        self.pivots = [struct.unpack_from('<3f', pivt, i) for i in range(0, len(pivt), 12)]
        self.cameras = [Camera(e) for e in _sized_entries(get.get('CAMS', b''))]

    # -- queries ---------------------------------------------------------------

    def all_nodes(self):
        """(kind, entry) for every node, in object id order."""
        out = [(kind, e) for kind in NODE_CHUNKS for e in self.nodes[kind]]
        return sorted(out, key=lambda ke: ke[1].node.object_id)

    def node(self, name):
        for _, e in self.all_nodes():
            if e.node.name.strip() == name:
                return e
        raise KeyError(name)

    def sequence(self, name):
        for s in self.sequences:
            if s.name == name:
                return s
        raise KeyError(name)

    # -- writing ---------------------------------------------------------------

    def write(self):
        parts = {
            'VERS': struct.pack('<I', self.version),
            'MODL': _pad(self.name, 80) + self.animation_file + EXTENT.pack(*self.extent)
            + struct.pack('<I', self.blend_time),
            'SEQS': b''.join(s.write() for s in self.sequences),
            'MTLS': b''.join(self.materials),
            'TEXS': b''.join(t.write() for t in self.textures),
            'GEOS': b''.join(g.write() for g in self.geosets),
            'GEOA': b''.join(a.write() for a in self.geoset_animations),
            'PIVT': b''.join(struct.pack('<3f', *p) for p in self.pivots),
            'CAMS': b''.join(c.write() for c in self.cameras),
        }
        for kind in NODE_CHUNKS:
            parts[kind] = b''.join(e.write() for e in self.nodes[kind])
        present = [t for t, _ in self.chunks]
        # a chunk that gained entries is placed where the format expects it
        order = ['VERS', 'MODL', 'SEQS', 'GLBS', 'MTLS', 'TEXS', 'TXAN', 'GEOS', 'GEOA', 'BONE', 'LITE', 'HELP',
                 'ATCH', 'PIVT', 'PREM', 'PRE2', 'RIBB', 'CAMS', 'EVTS', 'CLID']
        for tag in order:
            if tag not in present and parts.get(tag):
                at = 0
                for i, (t, _) in enumerate(self.chunks):
                    if t in order and order.index(t) < order.index(tag):
                        at = i + 1
                self.chunks.insert(at, [tag, b''])
                present.insert(at, tag)
        out = bytearray(b'MDLX')
        for tag, data in self.chunks:
            if tag in parts:
                data = parts[tag]
            out += tag.encode('latin-1') + struct.pack('<I', len(data)) + data
        return bytes(out)


def material(layers, priority=0, flags=0):
    """A material from layers (filter mode, shading flags, texture id, alpha)."""
    body = b''
    for filter_mode, shading, texture, alpha in layers:
        body += struct.pack('<IIIiiIf', 28, filter_mode, shading, texture, -1, 0, alpha)
    body = struct.pack('<iI', priority, flags) + b'LAYS' + struct.pack('<I', len(layers)) + body
    return struct.pack('<I', 4 + len(body)) + body


def layer_textures(raw):
    """The texture ids of a raw material's layers."""
    count = struct.unpack_from('<I', raw, 16)[0]
    out, pos = [], 20
    for _ in range(count):
        size = struct.unpack_from('<I', raw, pos)[0]
        out.append(struct.unpack_from('<i', raw, pos + 12)[0])
        pos += size
    return out

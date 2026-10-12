"""Writer for Warcraft III models in the MDX format, version 800 (the classic
format every game version can load).

The model is described with plain Python data:

    model = {
        'name': str,
        'sequences': [{'name', 'start', 'end', 'move_speed', 'looping', 'rarity'}],
        'textures': [{'path': str, 'replaceable': int}],
        'materials': [{'layers': [{'texture': int, 'filter': int, 'shading': int}]}],
        'geosets': [{'material': int, 'vertices': [(x, y, z)], 'normals': [...],
                     'uvs': [(u, v)], 'bones': [tuple of bone indices per vertex],
                     'triangles': [(a, b, c)]}],
        'bones': [{'name', 'parent', 'pivot', 'translation', 'rotation', 'scaling'}],
        'attachments': [{'name', 'parent', 'pivot'}],
        'collision': [{'name', 'parent', 'pivot', 'center', 'radius'}],
        'cameras': [{'name', 'position', 'target', 'fov', 'far', 'near'}],
    }

Animation tracks are lists of (frame, value) pairs; rotations are
quaternions (x, y, z, w). Bones are given in parent-first order.
"""

import math
import struct

NODE_HELPER = 0
NODE_BONE = 0x100
NODE_ATTACHMENT = 0x800
NODE_COLLISION = 0x2000

FILTER_NONE = 0
FILTER_TRANSPARENT = 1
FILTER_BLEND = 2
FILTER_ADDITIVE = 3

SHADE_UNSHADED = 0x1
SHADE_TWO_SIDED = 0x10
SHADE_UNFOGGED = 0x20

INTERP_LINEAR = 1


def _name(s, n):
    b = s.encode('ascii')
    if len(b) >= n:
        raise ValueError('name too long: %r' % s)
    return b + bytes(n - len(b))


def _chunk(tag, data):
    return tag + struct.pack('<I', len(data)) + data


def _extent(points):
    if not points:
        return struct.pack('<7f', 0, 0, 0, 0, 0, 0, 0)
    mn = [min(p[i] for p in points) for i in range(3)]
    mx = [max(p[i] for p in points) for i in range(3)]
    radius = max(math.sqrt(sum(c * c for c in p)) for p in points)
    return struct.pack('<7f', radius, *mn, *mx)


def _track(tag, keys):
    data = tag + struct.pack('<IIi', len(keys), INTERP_LINEAR, -1)
    for frame, value in keys:
        data += struct.pack('<i', int(frame)) + struct.pack('<%df' % len(value), *value)
    return data


def _node(name, object_id, parent, flags, tracks=b''):
    return struct.pack('<I', 96 + len(tracks)) + _name(name, 80) + struct.pack('<iiI', object_id, parent, flags) + tracks


def write(model):
    points = [v for g in model['geosets'] for v in g['vertices']]
    extent = _extent(points)
    out = bytearray(b'MDLX')
    out += _chunk(b'VERS', struct.pack('<I', 800))
    out += _chunk(b'MODL', _name(model['name'], 80) + bytes(260) + extent + struct.pack('<I', 150))

    seqs = b''
    for s in model['sequences']:
        seqs += (_name(s['name'], 80) + struct.pack('<IIfIfI', s['start'], s['end'], s.get('move_speed', 0.0),
                                                      0 if s.get('looping', True) else 1, s.get('rarity', 0.0), 0)
                 + extent)
    out += _chunk(b'SEQS', seqs)

    mtls = b''
    for m in model['materials']:
        layers = b''
        for layer in m['layers']:
            layers += struct.pack('<IIIiiIf', 28, layer.get('filter', FILTER_NONE), layer.get('shading', 0),
                                  layer['texture'], -1, 0, layer.get('alpha', 1.0))
        body = struct.pack('<iI', m.get('priority', 0), 0) + b'LAYS' + struct.pack('<I', len(m['layers'])) + layers
        mtls += struct.pack('<I', 4 + len(body)) + body
    out += _chunk(b'MTLS', mtls)

    texs = b''
    for t in model['textures']:
        texs += struct.pack('<I', t.get('replaceable', 0)) + _name(t.get('path', ''), 260) + struct.pack('<I', 0)
    out += _chunk(b'TEXS', texs)

    geos = b''
    for g in model['geosets']:
        verts, normals, uvs = g['vertices'], g['normals'], g['uvs']
        n = len(verts)
        if not (n == len(normals) == len(uvs) == len(g['bones'])):
            raise ValueError('geoset arrays differ in length')
        if n > 65535:
            raise ValueError('too many vertices')
        # a matrix group per distinct bone combination; the game averages the
        # bones of a group, which gives smooth bends at the joints
        vertex_groups = [tuple(b) if isinstance(b, (tuple, list)) else (b,) for b in g['bones']]
        groups = sorted(set(vertex_groups))
        group_of = {b: i for i, b in enumerate(groups)}
        if len(groups) > 255:
            raise ValueError('too many matrix groups')
        flat = [b for grp in groups for b in grp]
        indices = [i for tri in g['triangles'] for i in tri]
        body = (b'VRTX' + struct.pack('<I', n) + b''.join(struct.pack('<3f', *v) for v in verts)
                + b'NRMS' + struct.pack('<I', n) + b''.join(struct.pack('<3f', *v) for v in normals)
                + b'PTYP' + struct.pack('<II', 1, 4)
                + b'PCNT' + struct.pack('<II', 1, len(indices))
                + b'PVTX' + struct.pack('<I', len(indices)) + struct.pack('<%dH' % len(indices), *indices)
                + b'GNDX' + struct.pack('<I', n) + bytes(group_of[b] for b in vertex_groups)
                + b'MTGC' + struct.pack('<I', len(groups)) + struct.pack('<%dI' % len(groups), *[len(x) for x in groups])
                + b'MATS' + struct.pack('<I', len(flat)) + struct.pack('<%dI' % len(flat), *flat)
                + struct.pack('<III', g['material'], 0, 0)
                + _extent(verts)
                + struct.pack('<I', len(model['sequences'])) + _extent(verts) * len(model['sequences'])
                + b'UVAS' + struct.pack('<I', 1)
                + b'UVBS' + struct.pack('<I', n) + b''.join(struct.pack('<2f', *uv) for uv in uvs))
        geos += struct.pack('<I', 4 + len(body)) + body
    out += _chunk(b'GEOS', geos)

    object_id = 0
    pivots = []
    bones = b''
    for b in model['bones']:
        tracks = b''
        if b.get('translation'):
            tracks += _track(b'KGTR', b['translation'])
        if b.get('rotation'):
            tracks += _track(b'KGRT', b['rotation'])
        if b.get('scaling'):
            tracks += _track(b'KGSC', b['scaling'])
        bones += _node(b['name'], object_id, b['parent'], NODE_BONE, tracks) + struct.pack('<ii', -1, -1)
        pivots.append(b['pivot'])
        object_id += 1
    out += _chunk(b'BONE', bones)

    atch = b''
    for i, a in enumerate(model.get('attachments', [])):
        body = _node(a['name'], object_id, a['parent'], NODE_ATTACHMENT) + bytes(260) + struct.pack('<i', i)
        atch += struct.pack('<I', 4 + len(body)) + body
        pivots.append(a['pivot'])
        object_id += 1

    clid = b''
    for c in model.get('collision', []):
        clid += (_node(c['name'], object_id, c['parent'], NODE_COLLISION)
                 + struct.pack('<I3ff', 2, *c['center'], c['radius']))
        pivots.append(c['pivot'])
        object_id += 1

    if atch:
        out += _chunk(b'ATCH', atch)
    out += _chunk(b'PIVT', b''.join(struct.pack('<3f', *p) for p in pivots))

    cams = b''
    for c in model.get('cameras', []):
        cams += (struct.pack('<I', 120) + _name(c['name'], 80) + struct.pack('<3f', *c['position'])
                 + struct.pack('<3f', c.get('fov', 0.7854), c.get('far', 1000.0), c.get('near', 8.0))
                 + struct.pack('<3f', *c['target']))
    if cams:
        out += _chunk(b'CAMS', cams)
    if clid:
        out += _chunk(b'CLID', clid)
    return bytes(out)


# ---------------------------------------------------------------------------
# quaternion helpers
# ---------------------------------------------------------------------------

def quat_axis(axis, degrees):
    a = math.radians(degrees) / 2.0
    s = math.sin(a)
    x, y, z = axis
    return (x * s, y * s, z * s, math.cos(a))


def quat_mul(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return (aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw,
            aw * bw - ax * bx - ay * by - az * bz)


def quat_euler(roll=0.0, pitch=0.0, yaw=0.0):
    """Rotation about X (roll), then Y (pitch), then Z (yaw), in degrees.
    Models face +X with +Z up: positive pitch tips the top forward."""
    q = quat_axis((1, 0, 0), roll)
    q = quat_mul(quat_axis((0, 1, 0), pitch), q)
    q = quat_mul(quat_axis((0, 0, 1), yaw), q)
    return q


def quat_rotate(q, v):
    x, y, z, w = q
    vx, vy, vz = v
    # q * v * q^-1
    ix = w * vx + y * vz - z * vy
    iy = w * vy + z * vx - x * vz
    iz = w * vz + x * vy - y * vx
    iw = -x * vx - y * vy - z * vz
    return (ix * w + iw * -x + iy * -z - iz * -y,
            iy * w + iw * -y + iz * -x - ix * -z,
            iz * w + iw * -z + ix * -y - iy * -x)

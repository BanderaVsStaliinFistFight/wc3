"""Object editor data -- custom units (war3map.w3u) and abilities
(war3map.w3a) -- and the import list (war3map.imp), in the formats the
classic World Editor writes."""

import struct

INT, REAL, UNREAL, STRING = 0, 1, 2, 3
VERSION = 2                 # the expansion's object data version
IMPORT_CUSTOM_PATH = 10     # the import is stored under its full path


def _id(s):
    b = s.encode('ascii')
    if len(b) != 4:
        raise ValueError('object ids have four characters: %r' % s)
    return b


def _value(kind, value):
    if kind == INT:
        return struct.pack('<i', value)
    if kind in (REAL, UNREAL):
        return struct.pack('<f', value)
    return value.encode('utf-8') + b'\0'


def _table(objects, levels):
    out = struct.pack('<i', len(objects))
    for base, new, mods in objects:
        out += _id(base) + _id(new) + struct.pack('<i', len(mods))
        for mod in mods:
            if levels:
                field, kind, level, data, value = mod if len(mod) == 5 else (mod[0], mod[1], 0, 0, mod[2])
                out += _id(field) + struct.pack('<iii', kind, level, data)
            else:
                field, kind, value = mod
                out += _id(field) + struct.pack('<i', kind)
            out += _value(kind, value) + struct.pack('<i', 0)
    return out


def w3u(custom):
    """custom: [(base id, new id, [(field, kind, value)])]."""
    return struct.pack('<i', VERSION) + _table([], False) + _table(custom, False)


def w3a(custom):
    """custom: [(base id, new id, [(field, kind, value) or
    (field, kind, level, data pointer, value)])]."""
    return struct.pack('<i', VERSION) + _table([], True) + _table(custom, True)


def imp(paths):
    out = struct.pack('<ii', 1, len(paths))
    for p in paths:
        out += bytes([IMPORT_CUSTOM_PATH]) + p.encode('utf-8') + b'\0'
    return out


def read(data, levels):
    """Parses w3u/w3a data back into {new id: (base id, {(field, level): value})}."""
    pos = 4
    out = {}
    for _ in range(2):
        count = struct.unpack_from('<i', data, pos)[0]
        pos += 4
        for _ in range(count):
            base, new = data[pos:pos + 4].decode(), data[pos + 4:pos + 8]
            new = new.decode() if new != b'\0\0\0\0' else base
            n = struct.unpack_from('<i', data, pos + 8)[0]
            pos += 12
            mods = {}
            for _ in range(n):
                field = data[pos:pos + 4].decode()
                kind = struct.unpack_from('<i', data, pos + 4)[0]
                pos += 8
                level = 0
                if levels:
                    level = struct.unpack_from('<i', data, pos)[0]
                    pos += 8
                if kind == INT:
                    value = struct.unpack_from('<i', data, pos)[0]
                    pos += 4
                elif kind in (REAL, UNREAL):
                    value = struct.unpack_from('<f', data, pos)[0]
                    pos += 4
                else:
                    end = data.index(b'\0', pos)
                    value = data[pos:end].decode('utf-8')
                    pos = end + 1
                if data[pos:pos + 4] not in (b'\0\0\0\0', base.encode(), new.encode()):
                    raise ValueError('bad modification end marker')
                pos += 4
                mods[(field, level)] = value
            out[new] = (base, mods)
    if pos != len(data):
        raise ValueError('trailing bytes in object data')
    return out

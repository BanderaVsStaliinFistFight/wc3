"""Minimal MPQ (format version 0) writer and reader, as used by Warcraft III maps.

Files are stored zlib-compressed in 4 KiB sectors (the same layout the World
Editor produces). Hash and block tables are encrypted with the standard MPQ
keys. No file-level encryption is used.
"""

import struct
import zlib

MPQ_FILE_COMPRESS = 0x00000200
MPQ_FILE_EXISTS = 0x80000000
SECTOR_SHIFT = 3
SECTOR_SIZE = 512 << SECTOR_SHIFT

HASH_TABLE_OFFSET = 0
HASH_NAME_A = 1
HASH_NAME_B = 2
HASH_FILE_KEY = 3

COMPRESSION_ZLIB = 0x02


def _build_crypt_table():
    table = [0] * 0x500
    seed = 0x00100001
    for index1 in range(0x100):
        index2 = index1
        for _ in range(5):
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp1 = (seed & 0xFFFF) << 0x10
            seed = (seed * 125 + 3) % 0x2AAAAB
            temp2 = seed & 0xFFFF
            table[index2] = temp1 | temp2
            index2 += 0x100
    return table


CRYPT_TABLE = _build_crypt_table()


def hash_string(name, hash_type):
    seed1 = 0x7FED7FED
    seed2 = 0xEEEEEEEE
    for ch in name.upper().replace('/', '\\').encode('ascii'):
        value = CRYPT_TABLE[(hash_type << 8) + ch]
        seed1 = (value ^ (seed1 + seed2)) & 0xFFFFFFFF
        seed2 = (ch + seed1 + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return seed1


def encrypt(data, key):
    words = struct.unpack('<%dI' % (len(data) // 4), data)
    out = []
    seed1 = key
    seed2 = 0xEEEEEEEE
    for value in words:
        seed2 = (seed2 + CRYPT_TABLE[0x400 + (seed1 & 0xFF)]) & 0xFFFFFFFF
        out.append((value ^ (seed1 + seed2)) & 0xFFFFFFFF)
        seed1 = ((((~seed1) << 0x15) + 0x11111111) | (seed1 >> 0x0B)) & 0xFFFFFFFF
        seed2 = (value + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return struct.pack('<%dI' % len(out), *out)


def decrypt(data, key):
    words = struct.unpack('<%dI' % (len(data) // 4), data)
    out = []
    seed1 = key
    seed2 = 0xEEEEEEEE
    for value in words:
        seed2 = (seed2 + CRYPT_TABLE[0x400 + (seed1 & 0xFF)]) & 0xFFFFFFFF
        plain = (value ^ (seed1 + seed2)) & 0xFFFFFFFF
        out.append(plain)
        seed1 = ((((~seed1) << 0x15) + 0x11111111) | (seed1 >> 0x0B)) & 0xFFFFFFFF
        seed2 = (plain + seed2 + (seed2 << 5) + 3) & 0xFFFFFFFF
    return struct.pack('<%dI' % len(out), *out)


def _compress_file(data):
    """Return the stored bytes of a sector-compressed file."""
    sectors = [data[i:i + SECTOR_SIZE] for i in range(0, len(data), SECTOR_SIZE)]
    table_size = 4 * (len(sectors) + 1)
    blobs = []
    offsets = [table_size]
    for sector in sectors:
        packed = bytes([COMPRESSION_ZLIB]) + zlib.compress(sector, 9)
        blob = packed if len(packed) < len(sector) else sector
        blobs.append(blob)
        offsets.append(offsets[-1] + len(blob))
    return struct.pack('<%dI' % len(offsets), *offsets) + b''.join(blobs)


class MpqWriter:
    def __init__(self):
        self.files = []

    def add(self, name, data):
        if isinstance(data, str):
            data = data.encode('utf-8')
        if any(n.lower() == name.lower() for n, _ in self.files):
            raise ValueError('duplicate file %s' % name)
        self.files.append((name, bytes(data)))

    def build(self, with_listfile=True):
        files = list(self.files)
        if with_listfile:
            listing = '\r\n'.join(n for n, _ in files) + '\r\n'
            files.append(('(listfile)', listing.encode('ascii')))

        hash_size = 16
        while hash_size < len(files) * 2:
            hash_size *= 2

        body = bytearray()
        blocks = []
        offset = 32
        for name, data in files:
            stored = _compress_file(data) if data else b''
            flags = MPQ_FILE_EXISTS | (MPQ_FILE_COMPRESS if data else 0)
            blocks.append((offset, len(stored), len(data), flags))
            body += stored
            offset += len(stored)

        hash_entries = [None] * hash_size
        for block_index, (name, _) in enumerate(files):
            slot = hash_string(name, HASH_TABLE_OFFSET) & (hash_size - 1)
            while hash_entries[slot] is not None:
                slot = (slot + 1) & (hash_size - 1)
            hash_entries[slot] = (hash_string(name, HASH_NAME_A), hash_string(name, HASH_NAME_B), 0, 0, block_index)

        hash_raw = bytearray()
        for entry in hash_entries:
            if entry is None:
                hash_raw += struct.pack('<IIHHI', 0xFFFFFFFF, 0xFFFFFFFF, 0xFFFF, 0xFFFF, 0xFFFFFFFF)
            else:
                hash_raw += struct.pack('<IIHHI', *entry)
        block_raw = b''.join(struct.pack('<IIII', *b) for b in blocks)

        hash_offset = offset
        block_offset = hash_offset + len(hash_raw)
        archive_size = block_offset + len(block_raw)
        header = struct.pack('<4sIIHHIIII', b'MPQ\x1a', 32, archive_size, 0, SECTOR_SHIFT,
                             hash_offset, block_offset, hash_size, len(blocks))
        return (header + bytes(body)
                + encrypt(bytes(hash_raw), hash_string('(hash table)', HASH_FILE_KEY))
                + encrypt(block_raw, hash_string('(block table)', HASH_FILE_KEY)))


class MpqReader:
    """Reader for archives produced by MpqWriter (used by the tests)."""

    def __init__(self, data):
        start = 0
        while data[start:start + 4] != b'MPQ\x1a':
            start += 512
            if start >= len(data):
                raise ValueError('no MPQ header')
        self.data = data
        self.start = start
        (_, header_size, self.archive_size, self.format_version, self.sector_shift,
         hash_offset, block_offset, hash_count, block_count) = struct.unpack_from('<4sIIHHIIII', data, start)
        raw = data[start + hash_offset:start + hash_offset + 16 * hash_count]
        raw = decrypt(raw, hash_string('(hash table)', HASH_FILE_KEY))
        self.hashes = [struct.unpack_from('<IIHHI', raw, 16 * i) for i in range(hash_count)]
        raw = data[start + block_offset:start + block_offset + 16 * block_count]
        raw = decrypt(raw, hash_string('(block table)', HASH_FILE_KEY))
        self.blocks = [struct.unpack_from('<IIII', raw, 16 * i) for i in range(block_count)]

    def _find(self, name):
        size = len(self.hashes)
        slot = hash_string(name, HASH_TABLE_OFFSET) & (size - 1)
        a = hash_string(name, HASH_NAME_A)
        b = hash_string(name, HASH_NAME_B)
        for _ in range(size):
            entry = self.hashes[slot]
            if entry[4] == 0xFFFFFFFF:
                return None
            if entry[0] == a and entry[1] == b:
                return self.blocks[entry[4]]
            slot = (slot + 1) & (size - 1)
        return None

    def has(self, name):
        return self._find(name) is not None

    def read(self, name):
        block = self._find(name)
        if block is None:
            raise KeyError(name)
        offset, stored_size, size, flags = block
        stored = self.data[self.start + offset:self.start + offset + stored_size]
        if not flags & MPQ_FILE_COMPRESS:
            return stored[:size]
        sector_size = 512 << self.sector_shift
        count = (size + sector_size - 1) // sector_size
        offsets = struct.unpack_from('<%dI' % (count + 1), stored, 0)
        out = bytearray()
        for i in range(count):
            blob = stored[offsets[i]:offsets[i + 1]]
            expected = min(sector_size, size - i * sector_size)
            if len(blob) < expected:
                if blob[0] != COMPRESSION_ZLIB:
                    raise ValueError('unsupported compression %d' % blob[0])
                blob = zlib.decompress(blob[1:])
            out += blob
        return bytes(out)

    def names(self):
        return [n for n in self.read('(listfile)').decode('ascii').split('\r\n') if n]

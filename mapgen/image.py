"""Image helpers: palette quantisation, BLP1 textures and PNG output.

Pixels are lists of (r, g, b) or (r, g, b, a) tuples, rows from the top.
"""

import struct
import zlib

from . import jpeg


def downsample(pixels, w, h):
    w2, h2 = max(1, w // 2), max(1, h // 2)
    channels = len(pixels[0])
    out = []
    for y in range(h2):
        for x in range(w2):
            acc = [0] * channels
            n = 0
            for dy in (0, 1):
                for dx in (0, 1):
                    sx, sy = min(w - 1, 2 * x + dx), min(h - 1, 2 * y + dy)
                    p = pixels[sy * w + sx]
                    for c in range(channels):
                        acc[c] += p[c]
                    n += 1
            out.append(tuple(a // n for a in acc))
    return out, w2, h2


def median_cut(counts, n):
    """counts: {colour: count}. Returns a palette of up to n colours."""
    def stats(items):
        total = sum(k for _, k in items)
        best_ch, best_range = 0, -1
        for ch in range(3):
            lo = min(c[ch] for c, _ in items)
            hi = max(c[ch] for c, _ in items)
            if hi - lo > best_range:
                best_ch, best_range = ch, hi - lo
        return best_range * total ** 0.5 if len(items) > 1 else -1.0, best_ch

    boxes = [(list(counts.items()),) + stats(list(counts.items()))]
    while len(boxes) < n:
        i = max(range(len(boxes)), key=lambda k: boxes[k][1])
        items, score, ch = boxes[i]
        if score <= 0:
            break
        boxes.pop(i)
        items.sort(key=lambda e: e[0][ch])
        total = sum(k for _, k in items)
        acc, cut = 0, 1
        for j, (_, k) in enumerate(items):
            acc += k
            if acc >= total / 2:
                cut = max(1, min(len(items) - 1, j + 1))
                break
        for part in (items[:cut], items[cut:]):
            boxes.append((part,) + stats(part))
    palette = []
    for items, _, _ in boxes:
        total = sum(k for _, k in items)
        palette.append(tuple(int(round(sum(c[ch] * k for c, k in items) / total)) for ch in range(3)))
    return palette


def _quantize(levels):
    """Shared 256 colour palette for all mip levels, then Floyd-Steinberg
    dithering so smooth gradients survive the palette."""
    counts = {}
    for px, _, _ in levels:
        for c in px:
            key = (c[0] & 0xFC | 2, c[1] & 0xFC | 2, c[2] & 0xFC | 2)
            counts[key] = counts.get(key, 0) + 1
    palette = median_cut(counts, 256)
    cache = {}

    def nearest(r, g, b):
        key = (r >> 2, g >> 2, b >> 2)
        idx = cache.get(key)
        if idx is None:
            best = 1 << 30
            for k, (pr, pg, pb) in enumerate(palette):
                d = (pr - r) * (pr - r) * 3 + (pg - g) * (pg - g) * 4 + (pb - b) * (pb - b) * 2
                if d < best:
                    best, idx = d, k
            cache[key] = idx
        return idx

    out = []
    for px, w, h in levels:
        indices = bytearray(w * h)
        err = [[0.0] * (w + 2) for _ in range(3)]
        for y in range(h):
            nxt = [[0.0] * (w + 2) for _ in range(3)]
            for x in range(w):
                c = px[y * w + x]
                r = min(255, max(0, int(c[0] + err[0][x + 1])))
                g = min(255, max(0, int(c[1] + err[1][x + 1])))
                b = min(255, max(0, int(c[2] + err[2][x + 1])))
                k = nearest(r, g, b)
                indices[y * w + x] = k
                pr, pg, pb = palette[k]
                for ch, e in ((0, r - pr), (1, g - pg), (2, b - pb)):
                    e *= 0.85
                    err[ch][x + 2] += e * 0.4375
                    nxt[ch][x] += e * 0.1875
                    nxt[ch][x + 1] += e * 0.3125
                    nxt[ch][x + 2] += e * 0.0625
            err = nxt
        out.append(bytes(indices))
    while len(palette) < 256:
        palette.append((0, 0, 0))
    return palette, out


def blp1(pixels, w, h, mipmaps=True):
    """Paletted BLP1 texture with an 8-bit alpha channel, the format most
    Warcraft III textures use. Pixels without alpha are opaque."""
    levels = [(pixels, w, h)]
    if mipmaps:
        while w > 1 or h > 1:
            pixels, w, h = downsample(pixels, w, h)
            levels.append((pixels, w, h))
    palette, indices = _quantize(levels)
    blobs = []
    for (px, lw, lh), idx in zip(levels, indices):
        alpha = bytes(c[3] if len(c) > 3 else 255 for c in px)
        blobs.append(idx + alpha)
    offsets, sizes = [], []
    pos = 156 + 1024
    for b in blobs:
        offsets.append(pos)
        sizes.append(len(b))
        pos += len(b)
    offsets += [0] * (16 - len(offsets))
    sizes += [0] * (16 - len(sizes))
    out = bytearray(b'BLP1')
    out += struct.pack('<6I', 1, 8, levels[0][1], levels[0][2], 4, 1 if mipmaps else 0)
    out += struct.pack('<16I', *offsets)
    out += struct.pack('<16I', *sizes)
    for r, g, b in palette:
        out += bytes([b, g, r, 0])
    for b in blobs:
        out += b
    return bytes(out)


def read_blp(data):
    """The full-size image of a BLP1 texture, JPEG or paletted, as
    (pixels, width, height) with (r, g, b, a) pixels."""
    if data[:4] != b'BLP1':
        raise ValueError('not a BLP1 texture')
    compression, alpha_bits, w, h = struct.unpack('<4I', data[4:20])
    offset, size = struct.unpack('<I', data[28:32])[0], struct.unpack('<I', data[92:96])[0]
    if compression == 0:
        header_size = struct.unpack('<I', data[156:160])[0]
        jw, jh, planes = jpeg.decode(data[160:160 + header_size] + data[offset:offset + size])
        if (jw, jh) != (w, h):
            raise ValueError('JPEG size does not match the BLP header')
        b, g, r = planes[:3]
        a = planes[3] if len(planes) > 3 and alpha_bits else [255] * (w * h)
        return list(zip(r, g, b, a)), w, h
    palette = [(data[156 + 4 * k + 2], data[156 + 4 * k + 1], data[156 + 4 * k]) for k in range(256)]
    blob = data[offset:offset + size]
    n = w * h
    if alpha_bits == 8:
        alpha = blob[n:2 * n]
    elif alpha_bits == 1:
        alpha = [255 if blob[n + i // 8] >> (i % 8) & 1 else 0 for i in range(n)]
    else:
        alpha = [255] * n
    return [palette[blob[i]] + (alpha[i],) for i in range(n)], w, h


def png(pixels, width, height):
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

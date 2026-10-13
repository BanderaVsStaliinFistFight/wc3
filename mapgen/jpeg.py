"""A baseline JPEG decoder, enough for the JPEG-compressed BLP textures that
Warcraft III models ship with.

Blizzard's BLP files keep their channels as stored (blue, green, red, alpha)
with no colour transform, so decode() hands back the raw component planes and
leaves their meaning to the caller.
"""

import math

ZIGZAG = [0, 1, 8, 16, 9, 2, 3, 10, 17, 24, 32, 25, 18, 11, 4, 5, 12, 19, 26, 33, 40, 48,
          41, 34, 27, 20, 13, 6, 7, 14, 21, 28, 35, 42, 49, 56, 57, 50, 43, 36, 29, 22,
          15, 23, 30, 37, 44, 51, 58, 59, 52, 45, 38, 31, 39, 46, 53, 60, 61, 54, 47, 55, 62, 63]

# COS[x][u] = C(u) / 2 * cos((2x + 1) u pi / 16), the 1D inverse DCT basis
COS = [[(math.sqrt(0.5) if u == 0 else 1.0) * 0.5 * math.cos((2 * x + 1) * u * math.pi / 16) for u in range(8)]
       for x in range(8)]


class Huffman:
    def __init__(self, counts, symbols):
        self.lookup = {}            # (length, code) -> symbol
        code, k = 0, 0
        for length in range(1, 17):
            for _ in range(counts[length - 1]):
                self.lookup[(length, code)] = symbols[k]
                code += 1
                k += 1
            code <<= 1


class Bits:
    def __init__(self, data, pos):
        self.data = data
        self.pos = pos
        self.acc = 0
        self.n = 0

    def bit(self):
        if self.n == 0:
            b = self.data[self.pos]
            self.pos += 1
            if b == 0xFF:
                if self.data[self.pos] == 0:
                    self.pos += 1               # a stuffed zero byte
                else:
                    b = 0                       # a marker: pad with zeros
                    self.pos -= 1
            self.acc, self.n = b, 8
        self.n -= 1
        return (self.acc >> self.n) & 1

    def bits(self, count):
        v = 0
        for _ in range(count):
            v = (v << 1) | self.bit()
        return v

    def symbol(self, table):
        code, length = 0, 0
        lookup = table.lookup
        while length < 16:
            code = (code << 1) | self.bit()
            length += 1
            s = lookup.get((length, code))
            if s is not None:
                return s
        raise ValueError('bad Huffman code')

    def restart(self):
        """Skip to the RSTn marker and past it."""
        self.n = 0
        while not (self.data[self.pos] == 0xFF and 0xD0 <= self.data[self.pos + 1] <= 0xD7):
            self.pos += 1
        self.pos += 2


def extend(v, size):
    return v - (1 << size) + 1 if size and v < (1 << (size - 1)) else v


def idct(coef):
    """8x8 inverse DCT of dequantised coefficients in natural order."""
    tmp = [0.0] * 64
    for u in range(8):                      # columns of coefficients -> rows of samples
        col = [coef[v * 8 + u] for v in range(8)]
        if not any(col):
            continue
        for y in range(8):
            c = COS[y]
            tmp[y * 8 + u] = sum(c[v] * col[v] for v in range(8) if col[v])
    out = [0] * 64
    for y in range(8):
        row = tmp[y * 8:y * 8 + 8]
        for x in range(8):
            c = COS[x]
            s = c[0] * row[0] + c[1] * row[1] + c[2] * row[2] + c[3] * row[3] + c[4] * row[4] + c[5] * row[5] \
                + c[6] * row[6] + c[7] * row[7]
            out[y * 8 + x] = min(255, max(0, int(round(s + 128))))
    return out


def decode(data):
    """Returns (width, height, planes): one list of samples per component,
    each width * height long, rows from the top."""
    quant, dc_tables, ac_tables = {}, {}, {}
    frame = None
    restart_interval = 0
    pos = 2
    if data[:2] != b'\xff\xd8':
        raise ValueError('not a JPEG')
    while True:
        while data[pos] != 0xFF:
            pos += 1
        marker = data[pos + 1]
        pos += 2
        if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
            continue
        if marker == 0xD9:
            raise ValueError('no image data')
        length = (data[pos] << 8) | data[pos + 1]
        seg = data[pos + 2:pos + length]
        pos += length
        if marker == 0xDB:                                  # quantisation tables
            i = 0
            while i < len(seg):
                precision, tid = seg[i] >> 4, seg[i] & 15
                i += 1
                if precision:
                    q = [(seg[i + 2 * k] << 8) | seg[i + 2 * k + 1] for k in range(64)]
                    i += 128
                else:
                    q = list(seg[i:i + 64])
                    i += 64
                quant[tid] = q
        elif marker == 0xC4:                                # Huffman tables
            i = 0
            while i < len(seg):
                cls, tid = seg[i] >> 4, seg[i] & 15
                counts = list(seg[i + 1:i + 17])
                total = sum(counts)
                table = Huffman(counts, list(seg[i + 17:i + 17 + total]))
                (ac_tables if cls else dc_tables)[tid] = table
                i += 17 + total
        elif marker in (0xC0, 0xC1):                        # baseline frame
            height, width = (seg[1] << 8) | seg[2], (seg[3] << 8) | seg[4]
            comps = []
            for k in range(seg[5]):
                cid, hv, tq = seg[6 + 3 * k:9 + 3 * k]
                comps.append({'id': cid, 'h': hv >> 4, 'v': hv & 15, 'tq': tq})
            frame = (width, height, comps)
        elif marker == 0xDD:
            restart_interval = (seg[0] << 8) | seg[1]
        elif marker == 0xDA:                                # start of scan
            if frame is None:
                raise ValueError('scan before frame')
            for k in range(seg[0]):
                cid, tables = seg[1 + 2 * k], seg[2 + 2 * k]
                for c in frame[2]:
                    if c['id'] == cid:
                        c['td'], c['ta'] = tables >> 4, tables & 15
            return _scan(data, pos, frame, quant, dc_tables, ac_tables, restart_interval)
        elif 0xC2 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            raise ValueError('only baseline JPEG is supported')


def _scan(data, pos, frame, quant, dc_tables, ac_tables, restart_interval):
    width, height, comps = frame
    hmax = max(c['h'] for c in comps)
    vmax = max(c['v'] for c in comps)
    mcux = (width + 8 * hmax - 1) // (8 * hmax)
    mcuy = (height + 8 * vmax - 1) // (8 * vmax)
    for c in comps:
        c['bw'] = mcux * c['h'] * 8
        c['plane'] = [0] * (c['bw'] * mcuy * c['v'] * 8)
        c['pred'] = 0
    bits = Bits(data, pos)
    done = 0
    for my in range(mcuy):
        for mx in range(mcux):
            if restart_interval and done and done % restart_interval == 0:
                bits.restart()
                for c in comps:
                    c['pred'] = 0
            for c in comps:
                q = quant[c['tq']]
                dc, ac = dc_tables[c['td']], ac_tables[c['ta']]
                for by in range(c['v']):
                    for bx in range(c['h']):
                        coef = [0] * 64
                        size = bits.symbol(dc)
                        c['pred'] += extend(bits.bits(size), size)
                        coef[0] = c['pred'] * q[0]
                        k = 1
                        while k < 64:
                            rs = bits.symbol(ac)
                            run, size = rs >> 4, rs & 15
                            if size == 0:
                                if run != 15:
                                    break
                                k += 16
                                continue
                            k += run
                            coef[ZIGZAG[k]] = extend(bits.bits(size), size) * q[k]
                            k += 1
                        block = idct(coef)
                        x0 = (mx * c['h'] + bx) * 8
                        y0 = (my * c['v'] + by) * 8
                        plane, bw = c['plane'], c['bw']
                        for y in range(8):
                            plane[(y0 + y) * bw + x0:(y0 + y) * bw + x0 + 8] = block[y * 8:y * 8 + 8]
            done += 1
    planes = []
    for c in comps:
        sx, sy = hmax // c['h'], vmax // c['v']
        plane, bw = c['plane'], c['bw']
        planes.append([plane[(y // sy) * bw + x // sx] for y in range(height) for x in range(width)])
    return width, height, planes

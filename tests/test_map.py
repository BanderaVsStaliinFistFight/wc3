"""Tests for the map builder.

Run with:  python3 -m unittest discover -s tests

Optional extra checks need Blizzard's script headers (not included in this
repository). Point these environment variables at them to enable:
    WC3_COMMON_J    path to common.j
    WC3_BLIZZARD_J  path to Blizzard.j
    PJASS           path to a pjass binary (https://github.com/lep/pjass)
"""

import os
import re
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import build  # noqa: E402
from mapgen import layout as L  # noqa: E402
from mapgen.mpq import MpqReader, MpqWriter  # noqa: E402

MAP_FILES = ['war3map.w3i', 'war3map.w3e', 'war3map.wpm', 'war3map.shd', 'war3map.doo',
             'war3mapUnits.doo', 'war3map.mmp', 'war3mapMap.blp', 'war3map.w3r', 'war3map.w3c',
             'war3map.w3s', 'war3map.wtg', 'war3map.wct', 'war3map.j']


class Reader:
    def __init__(self, data):
        self.b = data
        self.p = 0

    def i32(self):
        v = struct.unpack_from('<i', self.b, self.p)[0]
        self.p += 4
        return v

    def f32(self):
        v = struct.unpack_from('<f', self.b, self.p)[0]
        self.p += 4
        return v

    def raw(self, n):
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def string(self):
        end = self.b.index(b'\0', self.p)
        v = self.b[self.p:end].decode('utf-8')
        self.p = end + 1
        return v


class BuiltMap(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        path = os.path.join(cls.tmp.name, 'test.w3x')
        cls.path, cls.terrain = build.build(out=path, quiet=True)
        with open(path, 'rb') as f:
            cls.data = f.read()
        cls.mpq = MpqReader(cls.data)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_header(self):
        self.assertEqual(self.data[:4], b'HM3W')
        self.assertEqual(self.data[512:516], b'MPQ\x1a')

    def test_all_files_present(self):
        names = self.mpq.names()
        for n in MAP_FILES:
            self.assertIn(n, names)
            self.assertTrue(self.mpq.has(n))
            self.assertGreater(len(self.mpq.read(n)), 0)

    def test_no_layout_warnings(self):
        self.assertEqual(self.terrain.warnings, [])

    def test_w3i(self):
        r = Reader(self.mpq.read('war3map.w3i'))
        self.assertEqual(r.i32(), 25)
        r.i32()
        r.i32()
        self.assertEqual(r.string(), L.MAP_NAME)
        r.string()
        r.string()
        r.string()
        cam = [r.f32() for _ in range(8)]
        self.assertEqual(cam[:4], [float(v) for v in L.CAMERA])
        self.assertEqual([r.i32() for _ in range(4)], list(L.BOUNDS))
        self.assertEqual(r.i32(), L.WIDTH - 12)
        self.assertEqual(r.i32(), L.HEIGHT - 12)
        r.i32()
        self.assertEqual(r.raw(1), b'L')
        r.i32()
        for _ in range(4):
            r.string()
        r.i32()
        for _ in range(4):
            r.string()
        r.i32()
        r.f32()
        r.f32()
        r.f32()
        r.raw(4)
        r.i32()
        r.string()
        r.raw(1)
        r.raw(4)
        players = r.i32()
        self.assertEqual(players, 6)
        for _ in range(players):
            r.i32(), r.i32(), r.i32(), r.i32(), r.string(), r.f32(), r.f32(), r.i32(), r.i32()
        forces = r.i32()
        self.assertEqual(forces, 2)
        for _ in range(forces):
            r.i32(), r.i32(), r.string()
        self.assertEqual([r.i32() for _ in range(4)], [0, 0, 0, 0])
        self.assertEqual(r.p, len(r.b))

    def test_w3e(self):
        r = Reader(self.mpq.read('war3map.w3e'))
        self.assertEqual(r.raw(4), b'W3E!')
        self.assertEqual(r.i32(), 11)
        self.assertEqual(r.raw(1), b'L')
        r.i32()
        ground = [r.raw(4) for _ in range(r.i32())]
        cliffs = [r.raw(4) for _ in range(r.i32())]
        self.assertLessEqual(len(ground), 16)
        self.assertEqual(cliffs, [b'CLdi', b'CLgr'])
        w, h = r.i32(), r.i32()
        self.assertEqual((w, h), (L.WIDTH + 1, L.HEIGHT + 1))
        self.assertEqual((r.f32(), r.f32()), (-64.0 * L.WIDTH, -64.0 * L.HEIGHT))
        self.assertEqual(len(r.b) - r.p, w * h * 7)

    def test_cliffs_are_well_formed(self):
        c = self.terrain.corners
        for ty in range(L.HEIGHT):
            for tx in range(L.WIDTH):
                lv = [c[ty][tx].layer, c[ty][tx + 1].layer, c[ty + 1][tx].layer, c[ty + 1][tx + 1].layer]
                self.assertLessEqual(max(lv) - min(lv), 1)
                self.assertFalse(lv[0] == lv[3] and lv[1] == lv[2] and lv[0] != lv[1],
                                 'diagonal cliff at tile %d,%d' % (tx, ty))

    def test_pathing_and_shadows(self):
        wpm = self.mpq.read('war3map.wpm')
        self.assertEqual(wpm[:4], b'MP3W')
        w, h = struct.unpack_from('<ii', wpm, 8)
        self.assertEqual((w, h), (L.WIDTH * 4, L.HEIGHT * 4))
        self.assertEqual(len(wpm), 16 + w * h)
        self.assertEqual(len(self.mpq.read('war3map.shd')), w * h)

    def test_doodads(self):
        doo = self.mpq.read('war3map.doo')
        self.assertEqual(doo[:4], b'W3do')
        version, sub, count = struct.unpack_from('<iii', doo, 4)
        self.assertEqual((version, sub), (8, 11))
        self.assertEqual(count, len(self.terrain.doodads))
        self.assertEqual(len(doo), 16 + count * 50 + 8)
        limits = {'LTlt': 10, 'FTtw': 10, 'ATtr': 5, 'CTtr': 5, 'ZPfw': 5, 'ZPsh': 3, 'LPrs': 4,
                  'LPfp': 3, 'LOrb': 4, 'AOsr': 3, 'LTrc': 6}
        for d in self.terrain.doodads:
            self.assertLess(d['variation'], limits.get(d['id'], 1), d)
            self.assertTrue(L.PLAY_MIN_X <= d['x'] <= L.PLAY_MAX_X and L.PLAY_MIN_Y <= d['y'] <= L.PLAY_MAX_Y, d)

    def test_minimap(self):
        blp = self.mpq.read('war3mapMap.blp')
        self.assertEqual(blp[:4], b'BLP1')
        content, alpha, w, h = struct.unpack_from('<iiii', blp, 4)
        self.assertEqual((content, w, h), (1, 256, 256))

    def test_script(self):
        script = self.mpq.read('war3map.j').decode('utf-8')
        self.assertNotIn('//#LAYOUT', script)
        self.assertNotIn('//#CONFIG', script)
        functions = set(re.findall(r'^function (\w+)', script, re.M))
        self.assertIn('main', functions)
        self.assertIn('config', functions)
        for name in re.findall(r'ExecuteFunc\("(\w+)"\)', script):
            self.assertIn(name, functions)
        for name in re.findall(r'\bfunction (\w+)\)', script):
            self.assertIn(name, functions)
        self.assertNotIn('\t', script)

    def test_world_editor_trigger_files(self):
        wtg = self.mpq.read('war3map.wtg')
        self.assertEqual(wtg[:8], b'WTG!\x07\x00\x00\x00')
        wct = self.mpq.read('war3map.wct')
        self.assertEqual(struct.unpack_from('<i', wct, 0)[0], 1)
        custom = wct.decode('utf-8', 'replace')
        self.assertIn('function InitGame', custom)
        self.assertNotIn('function main', custom)
        self.assertIn('InitTrig_Init', custom)


class Mpq(unittest.TestCase):
    def test_roundtrip(self):
        files = {'a.txt': b'hello', 'big.bin': bytes(range(256)) * 300,
                 'Sub\\Dir\\file.j': b'x' * 9000, 'random.bin': os.urandom(5000)}
        w = MpqWriter()
        for name, data in files.items():
            w.add(name, data)
        r = MpqReader(b'\0' * 512 + w.build())
        for name, data in files.items():
            self.assertEqual(r.read(name), data)
            self.assertEqual(r.read(name.lower()), data)
        self.assertFalse(r.has('missing.txt'))


@unittest.skipUnless(os.environ.get('PJASS') and os.environ.get('WC3_COMMON_J') and os.environ.get('WC3_BLIZZARD_J'),
                     'set PJASS, WC3_COMMON_J and WC3_BLIZZARD_J to run pjass')
class Pjass(unittest.TestCase):
    def test_pjass(self):
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = build.build(out=os.path.join(tmp, 'm.w3x'), quiet=True)
            script = os.path.join(tmp, 'war3map.j')
            with open(path, 'rb') as f, open(script, 'wb') as out:
                out.write(MpqReader(f.read()).read('war3map.j'))
            res = subprocess.run([os.environ['PJASS'], os.environ['WC3_COMMON_J'],
                                  os.environ['WC3_BLIZZARD_J'], script], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stdout + res.stderr)


@unittest.skipUnless(os.environ.get('WC3_COMMON_J') and os.environ.get('WC3_BLIZZARD_J'),
                     'set WC3_COMMON_J and WC3_BLIZZARD_J to run the script simulator')
class Simulation(unittest.TestCase):
    def test_scenarios(self):
        import jass_sim
        with tempfile.TemporaryDirectory() as tmp:
            path, _ = build.build(out=os.path.join(tmp, 'm.w3x'), quiet=True)
            script = os.path.join(tmp, 'war3map.j')
            with open(path, 'rb') as f, open(script, 'wb') as out:
                out.write(MpqReader(f.read()).read('war3map.j'))
            paths = [os.environ['WC3_COMMON_J'], os.environ['WC3_BLIZZARD_J'], script]
            for name, (users, seed, fn) in jass_sim.SCENARIOS.items():
                world, vm = jass_sim.boot(paths, users, seed)
                failures = []
                fn(world, vm, failures)
                self.assertEqual(vm.errors, [], name)
                self.assertEqual(failures, [], name)


if __name__ == '__main__':
    unittest.main()

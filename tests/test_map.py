"""Tests for the map builder.

Run with:  python3 -m unittest discover -s tests

Optional extra checks need Blizzard's script headers (not included in this
repository). Point these environment variables at them to enable:
    WC3_COMMON_J    path to common.j
    WC3_BLIZZARD_J  path to Blizzard.j
    PJASS           path to a pjass binary (https://github.com/lep/pjass)
"""

import importlib.util
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
from mapgen import brawler, dwarf, hero, image, jpeg, mdxedit, objects  # noqa: E402
from mapgen.mpq import MpqReader, MpqWriter  # noqa: E402

MAP_FILES = ['war3map.w3i', 'war3map.w3e', 'war3map.wpm', 'war3map.shd', 'war3map.doo',
             'war3mapUnits.doo', 'war3map.mmp', 'war3mapMap.blp', 'war3map.w3r', 'war3map.w3c',
             'war3map.w3s', 'war3map.wtg', 'war3map.wct', 'war3map.j', 'war3map.w3u', 'war3map.w3a',
             'war3map.imp']


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


    def test_custom_heroes(self):
        units = objects.read(self.mpq.read('war3map.w3u'), levels=False)
        abilities = objects.read(self.mpq.read('war3map.w3a'), levels=True)
        script = self.mpq.read('war3map.j').decode('utf-8')
        for hero_id, name, module in ((hero.THANE_ID, hero.THANE_NAME, dwarf),
                                      (hero.BRAWLER_ID, hero.BRAWLER_NAME, brawler)):
            base, mods = units[hero_id]
            self.assertEqual(base, 'Hmkg')
            self.assertEqual(mods[('unam', 0)], name)
            self.assertEqual(mods[('umdl', 0)], module.MODEL_PATH)
            self.assertEqual(mods[('uico', 0)], module.ICON_PATH)
            self.assertIn("'%s'" % hero_id, script)
            for ability in mods[('uhab', 0)].split(','):
                self.assertIn(ability, abilities)
                self.assertIn(('anam', 0), abilities[ability][1])
        # every imported file is in the archive and listed in war3map.imp
        imp = self.mpq.read('war3map.imp')
        version, count = struct.unpack_from('<ii', imp, 0)
        listed = [p.decode() for p in imp[8:].split(b'\0')[:count]]
        self.assertEqual(version, 1)
        for path in listed:
            self.assertEqual(path[0], chr(objects.IMPORT_CUSTOM_PATH))
            self.assertTrue(self.mpq.has(path[1:]), path)
        self.assertEqual(sorted(p[1:] for p in listed),
                         sorted([dwarf.MODEL_PATH, dwarf.PORTRAIT_PATH, dwarf.TEXTURE_PATH,
                                 brawler.MODEL_PATH, brawler.PORTRAIT_PATH, brawler.TEXTURE_PATH,
                                 brawler.ICON_PATH, brawler.DISABLED_ICON_PATH]))

    def test_hero_models(self):
        for path in (dwarf.MODEL_PATH, dwarf.PORTRAIT_PATH, brawler.MODEL_PATH, brawler.PORTRAIT_PATH):
            mdx = self.mpq.read(path)
            self.assertEqual(mdx[:4], b'MDLX')
            self.assertEqual(struct.unpack_from('<4sII', mdx, 4), (b'VERS', 4, 800))
            mdxedit.Model(mdx)
        for path, size in ((dwarf.TEXTURE_PATH, dwarf.TEX), (brawler.TEXTURE_PATH, 256), (brawler.ICON_PATH, 64),
                           (brawler.DISABLED_ICON_PATH, 64)):
            tex = self.mpq.read(path)
            self.assertEqual(tex[:4], b'BLP1')
            self.assertEqual(struct.unpack_from('<ii', tex, 12), (size, size))


def check_well_formed(test, model, texture_path):
    data = model.write()
    again = mdxedit.Model(data)
    test.assertEqual(again.write(), data)
    ids = {e.node.object_id for _, e in model.all_nodes()}
    test.assertEqual(sorted(ids), list(range(len(model.pivots))))
    for g in model.geosets:
        n = len(g.vertices)
        test.assertGreater(n, 0)
        test.assertTrue(n == len(g.normals) == len(g.uvs) == len(g.vertex_groups))
        test.assertTrue(all(0 <= i < n for f in g.faces for i in f))
        test.assertTrue(all(0 <= k < len(g.groups) for k in g.vertex_groups))
        test.assertTrue(all(b in ids for grp in g.groups for b in grp))
        test.assertLess(g.material, len(model.materials))
    for a in model.geoset_animations:
        test.assertLess(a.geoset, len(model.geosets))
    test.assertIn(texture_path, [t.path for t in model.textures])


class HeroData(unittest.TestCase):
    def test_hotkeys_match_tooltips(self):
        """The letter a tooltip highlights is the ability's real hotkey, and no
        hero has two abilities on one key or one on a command key."""
        for _, hero_id, unit_mods in hero.UNITS:
            uhab = [m[-1] for m in unit_mods if m[0] == 'uhab'][0].split(',')
            keys = []
            for base, new, mods in hero.ABILITIES:
                if new not in uhab:
                    continue
                fields = {m[0]: m[-1] for m in mods}
                tip = fields['atp1']
                letter = re.search(r'\|cffffcc00(.)\|r', tip).group(1)
                self.assertEqual(letter.upper(), fields['ahky'], new)
                self.assertEqual(fields['arhk'], fields['ahky'], new)
                self.assertIn(fields['anam'], re.sub(r'\|c[0-9a-f]{8}|\|r', '', tip), new)
                keys.append(fields['ahky'])
            self.assertEqual(len(keys), 4, hero_id)
            self.assertEqual(len(set(keys)), 4, hero_id)
            self.assertFalse(set(keys) & set('MSHAPO'), hero_id)


class Jpeg(unittest.TestCase):
    def test_decodes_blp_texture(self):
        pixels, w, h = image.read_blp(brawler.read_reference('texture'))
        self.assertEqual((w, h, len(pixels)), (256, 256, 256 * 256))
        # a pale cheek, the blue iris, and the transparent texels the body's edges use
        cheek = pixels[85 * w + 150]
        self.assertTrue(all(abs(a - b) <= 2 for a, b in zip(cheek, (226, 196, 177, 255))), cheek)
        iris = pixels[71 * w + 159]
        self.assertGreater(iris[2], iris[0] + 15)
        self.assertIn(0, {p[3] for p in pixels})

    @unittest.skipUnless(importlib.util.find_spec('PIL'), 'Pillow not installed')
    def test_matches_libjpeg(self):
        import io
        from PIL import Image
        data = brawler.read_reference('icon')
        offset, size = struct.unpack_from('<I', data, 28)[0], struct.unpack_from('<I', data, 92)[0]
        header = struct.unpack_from('<I', data, 156)[0]
        stream = data[160:160 + header] + data[offset:offset + size]
        w, h, planes = jpeg.decode(stream)
        ref = Image.open(io.BytesIO(stream)).tobytes()               # Pillow reads it as inverted CMYK
        worst = max(abs(255 - ref[4 * i + c] - planes[c][i]) for i in range(w * h) for c in range(4))
        self.assertLessEqual(worst, 1)


class BrawlerModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.files = brawler.build()
        cls.model = mdxedit.Model(cls.files[brawler.MODEL_PATH])
        cls.portrait = mdxedit.Model(cls.files[brawler.PORTRAIT_PATH])
        cls.texture, cls.w, cls.h = image.read_blp(cls.files[brawler.TEXTURE_PATH])
        cls.original, _, _ = image.read_blp(brawler.read_reference('texture'))

    def test_reference_models_round_trip(self):
        for member in ('model', 'portrait'):
            data = brawler.read_reference(member)
            self.assertEqual(mdxedit.Model(data).write(), data)

    def test_well_formed(self):
        for model in (self.model, self.portrait):
            check_well_formed(self, model, brawler.TEXTURE_PATH)
            self.assertNotIn(brawler.SOURCE_TEXTURE, [t.path for t in model.textures])

    def test_only_colours_change(self):
        """Tenebrae's mesh and animations are kept as they are; the only new
        geometry is one glow over each eye."""
        for member, model in (('model', self.model), ('portrait', self.portrait)):
            original = mdxedit.Model(brawler.read_reference(member))
            self.assertEqual(len(model.geosets), len(original.geosets) + 1)
            for a, b in zip(model.geosets, original.geosets):
                self.assertEqual((a.vertices, a.faces, a.uvs), (b.vertices, b.faces, b.uvs))
            self.assertEqual([s.write() for s in model.sequences], [s.write() for s in original.sequences])
            glow = model.geosets[-1]
            self.assertEqual(len(glow.faces), 4)
            ys = sorted(v[1] for v in glow.vertices)
            self.assertAlmostEqual(ys[0] + ys[-1], 2 * sum(ys) / len(ys), delta=1.0)    # one each side
            layers = mdxedit.layer_textures(model.materials[glow.material])
            self.assertEqual(model.textures[layers[0]].path, brawler.TEXTURE_PATH)

    def test_recoloured(self):
        w = self.w
        cheek, beard = self.texture[85 * w + 150], self.texture[140 * w + 140]
        self.assertLess(max(cheek[:3]), 140)                    # dark slate skin
        self.assertGreater(cheek[2], cheek[0])
        self.assertLess(max(beard[:3]), 50)                     # near black beard
        for x, y in ((158, 71), (154, 69), (162, 73)):          # pupil, white, iris: all glowing red
            eye = self.texture[y * w + x]
            self.assertGreater(eye[0], 200, (x, y))
            self.assertGreater(eye[0], max(eye[1], eye[2]) + 80, (x, y))
        # alpha is untouched (but for the glow sprite) and Tenebrae's signature (no triangle uses it) keeps
        # its colours
        gx, gy, size = brawler.GLOW
        sprite = {(gy + y) * w + gx + x for y in range(size) for x in range(size)}
        self.assertEqual([p[3] for i, p in enumerate(self.texture) if i not in sprite],
                         [p[3] for i, p in enumerate(self.original) if i not in sprite])
        signature = [i for i, p in enumerate(self.original) if p[2] > p[0] + 40 and p[1] > p[0] + 40]
        self.assertGreater(len(signature), 100)
        changed = sum(1 for i in signature if max(abs(a - b) for a, b in zip(self.texture[i], self.original[i])) > 24)
        self.assertLess(changed, len(signature) // 20)

    def test_icons(self):
        icon, w, h = image.read_blp(self.files[brawler.ICON_PATH])
        disabled, _, _ = image.read_blp(self.files[brawler.DISABLED_ICON_PATH])
        original, _, _ = image.read_blp(brawler.read_reference('icon'))
        for ex, ey in brawler.ICON_EYES:
            eye = icon[int(ey) * w + int(ex)]
            self.assertGreater(eye[0], 200)
            self.assertGreater(eye[0], max(eye[1], eye[2]) + 80)
        frame = [i for i in range(w * h) if min(i % w, i // w, w - 1 - i % w, h - 1 - i // w) < 4]
        self.assertTrue(all(max(abs(a - b) for a, b in zip(icon[i], original[i])) <= 24 for i in frame))
        self.assertTrue(all(p[0] == p[1] == p[2] for p in disabled))


class HeroModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model, cls.portrait = dwarf.build_models()

    def test_reference_models_round_trip(self):
        for member in ('King/King.mdx', 'King/King_Portrait.mdx'):
            data = dwarf.read_reference(member)
            self.assertEqual(mdxedit.Model(data).write(), data)

    def test_well_formed(self):
        for model in (self.model, self.portrait):
            check_well_formed(self, model, dwarf.TEXTURE_PATH)

    def test_dwarf_changes(self):
        king = mdxedit.Model(dwarf.read_reference('King/King.mdx'))
        top = max(v[2] for g in self.model.geosets for v in g.vertices)
        self.assertLess(top, max(v[2] for g in king.geosets for v in g.vertices) - 15)
        hidden = {a.geoset for a in self.model.geoset_animations if a.alpha == 0.0}
        visible = [g for i, g in enumerate(self.model.geosets) if i not in hidden]
        self.assertGreater(min(v[2] for g in visible for v in g.vertices), -1.0)
        # the crown is gone, the sword's glow hidden, the sword now a hammer
        head = self.model.node('Bone_Head').node.object_id
        armour = self.model.geosets[dwarf.ARMOUR]
        self.assertFalse(any(armour.bones_of(i) == [head] for i in range(len(armour.vertices))))
        glow = [a for a in self.model.geoset_animations if a.geoset == dwarf.SWORD_GLOW]
        self.assertEqual(glow[0].alpha, 0.0)
        hammer = self.model.geosets[dwarf.SWORD]
        layers = mdxedit.layer_textures(self.model.materials[hammer.material])
        self.assertEqual(self.model.textures[layers[0]].path, dwarf.TEXTURE_PATH)
        self.assertEqual(self.model.sequence('Walk').move_speed, dwarf.WALK_SPEED)
        # the beard grew: the hair geosets reach well below the King's chin
        self.assertLess(min(v[2] for v in self.model.geosets[9].vertices), 100.7 - dwarf.DROP - 10)

    def test_portrait(self):
        names = [s.name for s in self.portrait.sequences]
        self.assertIn('Portrait - 1', names)
        self.assertIn('Portrait Talk - 1', names)
        self.assertEqual(len(self.portrait.cameras), 1)
        animated = {a.geoset for a in self.portrait.geoset_animations}
        self.assertEqual(animated, set(range(len(self.portrait.geosets))))

    def test_atlas_regions_do_not_overlap(self):
        cells = set()
        for name, (x0, y0, x1, y1) in dwarf.REGIONS.items():
            self.assertTrue(0 <= x0 < x1 <= dwarf.TEX and 0 <= y0 < y1 <= dwarf.TEX, name)
            for y in range(y0, y1, 8):
                for x in range(x0, x1, 8):
                    self.assertNotIn((x, y), cells, name)
                    cells.add((x, y))


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

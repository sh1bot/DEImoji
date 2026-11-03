"""Check real HarfBuzz shaping, including feedback through earlier ligatures."""
import ctypes as C
import ctypes.util
from io import BytesIO
from pathlib import Path
import sys
import struct
import tempfile
import tomllib
import unittest
from unittest import mock
import subprocess
import json
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cluster_ligatures import add_cluster_ligatures, remove_cluster_ligatures, CLUSTER_NAMES
from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))
import cache_fonts


GLYPHS = ['.notdef', 'space', 'z', 'f', 'z2', 'z3', 'f2', 'f3',
          'a', 'b', 'ab', 'zwj', 'female', 'zwoman']


def make_font():
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(GLYPHS)
    fb.setupCharacterMap({32: 'space', 0x1F9DF: 'z', 0x1F33B: 'f',
                          97: 'a', 98: 'b', 0x200D: 'zwj', 0x2640: 'female'})
    fb.setupGlyf({name: TTGlyphPen(None).glyph() for name in GLYPHS})
    fb.setupHorizontalMetrics({name: (1000, 0) for name in GLYPHS})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({'familyName': 'Cluster Test', 'styleName': 'Regular'})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.setupMaxp()
    addOpenTypeFeaturesFromString(fb.font, '''
        languagesystem DFLT dflt;
        feature ccmp {
            sub z zwj female by zwoman;
            sub z z z by z3;
            sub z z by z2;
            sub f f f by f3;
            sub f f by f2;
        } ccmp;
        feature liga { sub a b by ab; } liga;
        feature kern { pos a b -10; } kern;
    ''')
    return fb.font


class Info(C.Structure):
    _fields_ = [(key, C.c_uint32) for key in
                ('codepoint', 'mask', 'cluster', 'var1', 'var2')]


class Feature(C.Structure):
    _fields_ = [(key, C.c_uint32) for key in ('tag', 'value', 'start', 'end')]


def shape(font, text, calt=True):
    hb = C.CDLL(ctypes.util.find_library('harfbuzz'))
    def bind(name, result, *args):
        fn = getattr(hb, name)
        fn.restype, fn.argtypes = result, list(args)
        return fn
    ptr = C.c_void_p
    out = BytesIO()
    font.save(out)
    data = out.getvalue()
    blob = bind('hb_blob_create', ptr, C.c_char_p, C.c_uint, C.c_int, ptr, ptr)(
        data, len(data), 0, None, None)
    face = bind('hb_face_create', ptr, ptr, C.c_uint)(blob, 0)
    hbfont = bind('hb_font_create', ptr, ptr)(face)
    bind('hb_ot_font_set_funcs', None, ptr)(hbfont)
    buf = bind('hb_buffer_create', ptr)()
    utf8 = text.encode()
    bind('hb_buffer_add_utf8', None, ptr, C.c_char_p, C.c_int, C.c_uint, C.c_int)(
        buf, utf8, len(utf8), 0, len(utf8))
    bind('hb_buffer_guess_segment_properties', None, ptr)(buf)
    setting = Feature(int.from_bytes(b'calt', 'big'), int(calt), 0, 0xFFFFFFFF)
    bind('hb_shape', None, ptr, ptr, C.POINTER(Feature), C.c_uint)(hbfont, buf, C.byref(setting), 1)
    count = C.c_uint()
    infos = bind('hb_buffer_get_glyph_infos', C.POINTER(Info), ptr,
                 C.POINTER(C.c_uint))(buf, C.byref(count))
    order = font.getGlyphOrder()
    result = [order[infos[i].codepoint] for i in range(count.value)]
    for kind, value in [('buffer', buf), ('font', hbfont), ('face', face), ('blob', blob)]:
        bind('hb_' + kind + '_destroy', None, ptr)(value)
    return result


def reference(count):
    groups = []
    while count >= 2:
        if count == 4:
            take = 2
        elif count <= 3:
            take = count
        elif len(groups) < 3:
            take = 3
        else:
            take = 2 + ((groups[-3] - 2) ^ (groups[-1] - 2))
        groups.append(take)
        count -= take
    if count:
        groups.append(1)
    return groups


class ClusterTests(unittest.TestCase):
    def setUp(self):
        self.font = make_font()
        self.original_gpos = self.font['GPOS'].compile(self.font)
        add_cluster_ligatures(self.font)

    def test_feature_merge_and_roundtrip(self):
        self.assertEqual(self.font['GPOS'].compile(self.font), self.original_gpos)
        self.assertEqual(shape(self.font, 'ab'), ['ab'])
        tags = [r.FeatureTag for r in self.font['GSUB'].table.FeatureList.FeatureRecord]
        self.assertEqual(tags, sorted(tags))
        binary = BytesIO()
        self.font.save(binary)
        self.font = TTFont(BytesIO(binary.getvalue()))
        out = BytesIO()
        self.font.saveXML(out)
        restored = TTFont()
        restored.importXML(BytesIO(out.getvalue()))
        self.assertEqual(shape(restored, '🧟' * 40), shape(self.font, '🧟' * 40))

    def test_all_run_lengths(self):
        for emoji, base in [('🧟', 'z'), ('🌻', 'f')]:
            for n in list(range(101)) + [1000]:
                with self.subTest(emoji=emoji, n=n):
                    self.assertEqual(shape(self.font, emoji * n),
                                     [base + str(k) if k > 1 else base for k in reference(n)])

    def test_period_seven_per_cluster(self):
        groups = shape(self.font, '🧟' * 200)
        self.assertEqual(groups[:7], ['z3', 'z3', 'z3', 'z2', 'z3', 'z2', 'z2'])
        self.assertEqual(groups[:7], groups[7:14])
        self.assertEqual(groups[7:14], groups[14:21])

    def test_boundaries_and_modified_input(self):
        z = shape(self.font, '🧟' * 19)
        f = shape(self.font, '🌻' * 20)
        self.assertEqual(shape(self.font, '🧟' * 19 + '🌻' * 20), z + f)
        self.assertEqual(shape(self.font, '🧟' * 19 + ' ' + '🧟' * 19), z + ['space'] + z)
        self.assertEqual(shape(self.font, '🧟\u200d♀' * 3), ['zwoman'] * 3)

    def test_calt_can_be_disabled(self):
        self.assertEqual(shape(self.font, '🧟' * 8 + '🌻' * 8, calt=False), ['z'] * 8 + ['f'] * 8)

    def test_install_is_idempotent(self):
        before = self.font['GSUB'].compile(self.font)
        add_cluster_ligatures(self.font)
        self.assertEqual(before, self.font['GSUB'].compile(self.font))

    def test_recover_native_font_for_cache(self):
        original = make_font()['GSUB'].compile(make_font())
        remove_cluster_ligatures(self.font)
        self.assertEqual(original, self.font['GSUB'].compile(self.font))
        add_cluster_ligatures(self.font)
        self.assertEqual(shape(self.font, '🧟' * 18),
                         ['z3', 'z3', 'z3', 'z2', 'z3', 'z2', 'z2'])

    def test_cache_recovery_rejects_unrecognized_font(self):
        with self.assertRaises(ValueError):
            remove_cluster_ligatures(make_font())

    def test_cache_recovery_supports_extension_lookups(self):
        from fontTools.ttLib.tables import otTables
        for lookup in self.font['GSUB'].table.LookupList.Lookup:
            if lookup.LookupType not in (4, 6):
                continue
            wrapped = []
            for table in lookup.SubTable:
                extension = otTables.ExtensionSubst()
                extension.Format = 1
                extension.ExtensionLookupType = lookup.LookupType
                extension.ExtSubTable = table
                wrapped.append(extension)
            lookup.LookupType = 7
            lookup.SubTable = wrapped
        binary = BytesIO()
        self.font.save(binary)
        font = TTFont(BytesIO(binary.getvalue()))
        remove_cluster_ligatures(font)
        add_cluster_ligatures(font)
        self.assertEqual(shape(font, '🧟' * 18),
                         ['z3', 'z3', 'z3', 'z2', 'z3', 'z2', 'z2'])

    def test_missing_artwork_is_noop(self):
        font = make_font()
        for table in font['GSUB'].table.LookupList.Lookup[0].SubTable:
            table.ligatures.pop('z', None)
            table.ligatures.pop('f', None)
        original = font['GSUB'].compile(font)
        add_cluster_ligatures(font)
        self.assertEqual(font['GSUB'].compile(font), original)

    def test_wide_artwork(self):
        root = Path(__file__).resolve().parents[1] / 'ligatures'
        for name in CLUSTER_NAMES:
            svg = ET.parse(root / 'svg' / (name + '.svg')).getroot()
            box = tuple(map(float, svg.attrib['viewBox'].split()))
            data = (root / 'png/128' / (name + '.png')).read_bytes()
            self.assertEqual(data[:8], b'\x89PNG\r\n\x1a\n')
            width, height = struct.unpack('>II', data[16:24])
            self.assertEqual(box, (0, 0, width, height))
            self.assertEqual(height, 128)
            self.assertGreater(width, 136)
            self.assertLessEqual(width, 255)

    def test_both_colr_configs_include_assets(self):
        root = Path(__file__).resolve().parents[1]
        for name in ('all', 'noflags'):
            config = tomllib.loads((root / 'colrv1' / (name + '.toml')).read_text())
            sources = config['master']['regular']['srcs']
            for asset in CLUSTER_NAMES:
                self.assertEqual(sources.count('../ligatures/svg/' + asset + '.svg'), 1)
            self.assertFalse(any(s.startswith('../svg/') for s in sources))


class NativeCacheTests(unittest.TestCase):
    def test_rules_and_ui_do_not_invalidate_artwork(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.run(['git', *args], cwd=root, check=True,
                                      stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            def commit():
                git('add', '.')
                git('-c', 'user.name=Cache Test', '-c', 'user.email=cache@example.invalid',
                    'commit', '-m', 'test')
            git('init')
            (root / 'Makefile').write_text('native build')
            (root / 'cluster_ligatures.py').write_text('rules v1')
            (root / 'web').mkdir()
            (root / 'web/app.js').write_text('ui v1')
            (root / '2D/svg').mkdir(parents=True)
            art = root / '2D/svg/emoji_u1f9df.svg'
            art.write_text('artwork v1')
            commit()
            with mock.patch.object(cache_fonts, 'ROOT', root), mock.patch.object(
                    cache_fonts, 'compiler_info', return_value={'compiler': 'v1'}):
                original = cache_fonts.cache_key()
                (root / 'cluster_ligatures.py').write_text('rules v2')
                (root / 'web/app.js').write_text('ui v2')
                commit()
                self.assertEqual(original, cache_fonts.cache_key())
                art.write_text('artwork v2')
                commit()
                self.assertNotEqual(original, cache_fonts.cache_key())

    def test_apply_preserves_cached_native_fonts(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cache = root / 'native'
            cache.mkdir()
            for name in cache_fonts.FONTS:
                make_font().save(cache / name)
            metadata = {'key': 'test', 'hashes': {
                name: cache_fonts.digest(cache / name) for name in cache_fonts.FONTS}}
            (cache / 'cache.json').write_text(json.dumps(metadata))
            with mock.patch.object(cache_fonts, 'ROOT', root), mock.patch.object(cache_fonts, 'CACHE', cache):
                self.assertTrue(cache_fonts.verify('test'))
                self.assertFalse(cache_fonts.verify('different-key'))
                cache_fonts.apply('test')
                font = TTFont(root / '2D/fonts/NotoColorEmoji.ttf')
                self.assertEqual(shape(font, '🧟' * 18),
                                 ['z3', 'z3', 'z3', 'z2', 'z3', 'z2', 'z2'])
                self.assertTrue(cache_fonts.verify('test'))
                (cache / 'NotoColorEmoji.ttf').write_bytes(b'corrupt')
                self.assertFalse(cache_fonts.verify('test'))


if __name__ == '__main__':
    unittest.main()

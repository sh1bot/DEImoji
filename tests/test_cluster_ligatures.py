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
from cluster_ligatures import add_cluster_ligatures, remove_cluster_ligatures, CLUSTER_NAMES, NATIVE_CLUSTER_NAMES
from fontTools.fontBuilder import FontBuilder
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'web'))
import cache_fonts


GLYPHS = ['.notdef', 'space', 'z', 'f', 'z2', 'z3', 'f2', 'f3',
          'a', 'b', 'ab', 'zwj', 'female', 'zwoman']


def make_font(with_poop=False):
    glyphs = GLYPHS + (['p', 'p2', 'p3'] if with_poop else [])
    fb = FontBuilder(1000, isTTF=True)
    fb.setupGlyphOrder(glyphs)
    fb.setupCharacterMap({32: 'space', 0x1F9DF: 'z', 0x1F33B: 'f',
                          97: 'a', 98: 'b', 0x200D: 'zwj', 0x2640: 'female',
                          **({0x1F4A9: 'p'} if with_poop else {})})
    fb.setupGlyf({name: TTGlyphPen(None).glyph() for name in glyphs})
    fb.setupHorizontalMetrics({name: (1000, 0) for name in glyphs})
    fb.setupHorizontalHeader(ascent=800, descent=-200)
    fb.setupNameTable({'familyName': 'Cluster Test', 'styleName': 'Regular'})
    fb.setupOS2(sTypoAscender=800, sTypoDescender=-200,
                usWinAscent=800, usWinDescent=200)
    fb.setupPost()
    fb.setupMaxp()
    features = '''
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
    '''
    if with_poop:
        features = features.replace('sub z zwj female',
                                    'sub p p p by p3; sub p p by p2; sub z zwj female')
    addOpenTypeFeaturesFromString(fb.font, features)
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
        elif len(groups) < 4:
            take = 3
        else:
            take = 2 + ((groups[-4] - 2) ^ (groups[-3] - 2))
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

    def test_period_fifteen_per_cluster(self):
        groups = shape(self.font, '🧟' * 200)
        self.assertEqual(groups[:15], ['z' + str(n) for n in
                         (3, 3, 3, 3, 2, 2, 2, 3, 2, 2, 3, 3, 2, 3, 2)])
        self.assertEqual(groups[:15], groups[15:30])
        self.assertEqual(groups[15:30], groups[30:45])

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
                         ['z' + str(n) for n in reference(18)])

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
                         ['z' + str(n) for n in reference(18)])

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
            asset_root = root / 'supplemental/poop' if '1f4a9' in name else root
            svg = ET.parse(asset_root / 'svg' / (name + '.svg')).getroot()
            box = tuple(map(float, svg.attrib['viewBox'].split()))
            data = (asset_root / 'png/128' / (name + '.png')).read_bytes()
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
            for asset in NATIVE_CLUSTER_NAMES:
                self.assertEqual(sources.count('../ligatures/svg/' + asset + '.svg'), 1)
            self.assertFalse(any(s.startswith('../svg/') for s in sources))


class PoopClusterTests(unittest.TestCase):
    def setUp(self):
        self.native = make_font(with_poop=True)
        self.font = make_font(with_poop=True)
        add_cluster_ligatures(self.font)

    def test_all_lengths_and_mixed_families(self):
        for n in list(range(101)) + [1000]:
            with self.subTest(n=n):
                expected = ['p' + str(k) if k > 1 else 'p' for k in reference(n)]
                self.assertEqual(shape(self.font, '💩' * n), expected)
        text = '💩' * 40 + '🧟' * 40 + '🌻' * 40
        self.assertEqual(shape(self.font, text), sum([
            [base + str(k) for k in reference(40)] for base in ('p', 'z', 'f')], []))
        self.assertEqual(shape(self.font, '💩' * 8, calt=False), ['p'] * 8)

    def test_period_fifteen_and_cache_roundtrip(self):
        groups = shape(self.font, '💩' * 200)
        self.assertEqual(groups[:15], groups[15:30])
        self.assertEqual(groups[15:30], groups[30:45])
        self.assertEqual(groups[:15].count('p3'), 8)
        self.assertEqual(groups[:15].count('p2'), 7)
        data = BytesIO()
        self.font.save(data)
        restored = TTFont(BytesIO(data.getvalue()))
        remove_cluster_ligatures(restored)
        self.assertEqual(restored['GSUB'].compile(restored), self.native['GSUB'].compile(self.native))

    def test_supplemental_artwork_checksum_and_recovery(self):
        from supplemental_artwork import _verify_bundle, add_supplemental_artwork, remove_supplemental_artwork
        self.assertEqual(len(_verify_bundle()), 64)
        # The compiled supplement provides a small, real COLRv1 fixture.
        from supplemental_artwork import ART
        font = TTFont(ART / 'Poop-COLRv1.ttf', recalcBBoxes=False)
        source_gsub = font['GSUB'].compile(font)
        for lookup in font['GSUB'].table.LookupList.Lookup:
            from cluster_ligatures import _ligature_tables
            for table in _ligature_tables(lookup):
                table.ligatures.clear()
        native_gsub = font['GSUB'].compile(font)
        original_order = font.getGlyphOrder()[:]
        original_palette = font['CPAL'].compile(font)
        info = add_supplemental_artwork(font)
        self.assertIsNotNone(info)
        self.assertTrue(info['overlap_gpos'])
        self.assertEqual(font['GPOS'].table.FeatureList.FeatureRecord[0].FeatureTag, 'kern')
        subtable = font['GPOS'].table.LookupList.Lookup[0].SubTable[0]
        values = [record.Value1.XAdvance for row in subtable.Class1Record
                  for record in row.Class2Record]
        self.assertIn(-41, values)
        self.assertEqual(set(values), {0, -41})
        base = font.getBestCmap()[0x1F4A9]
        for lookup in font['GPOS'].table.LookupList.Lookup:
            for table in lookup.SubTable:
                if base not in table.Coverage.glyphs:
                    continue
                left = table.ClassDef1.classDefs.get(base, 0)
                right = table.ClassDef2.classDefs.get(base, 0)
                self.assertEqual(table.Class1Record[left].Class2Record[right].Value1.XAdvance, 0)
        order = font.getGlyphOrder()[:]
        self.assertEqual(add_supplemental_artwork(font), info)
        self.assertEqual(font.getGlyphOrder(), order)
        data = BytesIO()
        font.save(data)
        restored = TTFont(BytesIO(data.getvalue()), recalcBBoxes=False)
        remove_supplemental_artwork(restored, info)
        self.assertNotIn('GPOS', restored)
        self.assertEqual(len(restored.getGlyphOrder()), len(original_order))
        self.assertEqual(restored['CPAL'].compile(restored), original_palette)
        self.assertEqual(restored['GSUB'].compile(restored), native_gsub)


class NativeCacheTests(unittest.TestCase):
    def test_bootstrap_across_compilers_requires_identical_native_sources(self):
        native = make_font()
        font = make_font()
        add_cluster_ligatures(font)
        data = BytesIO()
        font.save(data)
        payload = data.getvalue()
        metadata = {'commit': 'published', 'native_key': 'old-compiler',
                    'native_origin_key': 'original-compiler'}
        def fetch(url):
            return json.dumps(metadata).encode() if url.endswith('build.json') else payload
        for changed, expected in (('', True), ('2D/svg/changed.svg\n', False)):
            with self.subTest(changed=changed), tempfile.TemporaryDirectory() as directory:
                cache = Path(directory)
                with mock.patch.object(cache_fonts, 'CACHE', cache), mock.patch.object(
                        cache_fonts, 'fetch', side_effect=fetch), mock.patch.object(
                        cache_fonts, 'git', return_value=changed), mock.patch.object(
                        cache_fonts.subprocess, 'run'), mock.patch.object(cache_fonts, 'stamp') as stamp:
                    self.assertEqual(cache_fonts.bootstrap('new-compiler'), expected)
                    if expected:
                        stamp.assert_called_once_with('new-compiler', origin_key='original-compiler')
                        for name in cache_fonts.FONTS:
                            recovered = TTFont(cache / name)
                            self.assertEqual(recovered['GSUB'].compile(recovered),
                                             native['GSUB'].compile(native))
                    else:
                        stamp.assert_not_called()

    def test_ready_waits_only_for_a_missing_publication(self):
        with mock.patch.object(cache_fonts, 'verify', return_value=False), mock.patch.object(
                cache_fonts, 'bootstrap', side_effect=[None, True]), mock.patch.object(
                cache_fonts.time, 'sleep') as sleep:
            self.assertTrue(cache_fonts.ready('test', wait=60))
            sleep.assert_called_once()
        with mock.patch.object(cache_fonts, 'verify', return_value=False), mock.patch.object(
                cache_fonts, 'bootstrap', return_value=False), mock.patch.object(
                cache_fonts.time, 'sleep') as sleep:
            self.assertFalse(cache_fonts.ready('test', wait=60))
            sleep.assert_not_called()

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
                (root / 'modifier_ligatures.py').write_text('modifier rules v2')
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
                self.assertTrue((root / 'build/modifiers.json').exists())
                font = TTFont(root / '2D/fonts/NotoColorEmoji.ttf')
                self.assertEqual(shape(font, '🧟' * 18),
                                 ['z' + str(n) for n in reference(18)])
                self.assertTrue(cache_fonts.verify('test'))
                (cache / 'NotoColorEmoji.ttf').write_bytes(b'corrupt')
                self.assertFalse(cache_fonts.verify('test'))



def make_modifier_font():
    font = make_font()
    gendered = ('runner', 'swimmer', 'cyclist', 'climber')
    bases = ('runner', 'woman', 'man', 'person', 'thumb', 'swimmer', 'cyclist', 'climber')
    names = ['runner', 'woman', 'man', 'person', 'thumb', 'male', 'swimmer', 'cyclist',
             'unused', 'climber'] + ['skin' + str(i) for i in range(5)]
    names += [b + str(t) + str(g) for b in bases for t in range(5)
              for g in (range(3) if b in gendered else range(1))]
    font.setGlyphOrder(font.getGlyphOrder() + names)
    for name in names:
        font['glyf'].glyphs[name] = TTGlyphPen(None).glyph()
        font['hmtx'].metrics[name] = (1000, 0)
    font['maxp'].numGlyphs = len(font.getGlyphOrder())
    for table in font['cmap'].tables:
        if table.isUnicode() and table.format == 12:
            table.cmap.update({0x1F3C3: 'runner', 0x1F469: 'woman', 0x1F468: 'man',
                               0x1F9D1: 'person', 0x1F44D: 'thumb', 0x2642: 'male',
                               0x1F3CA: 'swimmer', 0x1F6B4: 'cyclist', 0x1F9D7: 'climber',
                               **{0x1F3FB + t: 'skin' + str(t) for t in range(5)}})
    rules = []
    for t in range(5):
        for g, gender in ((1, 'female'), (2, 'male')):
            rules += [f'sub {b} skin{t} zwj {gender} by {b}{t}{g};' for b in gendered]
        rules += [f'sub {b} skin{t} by {b}{t}0;' for b in bases]
    rules += ['sub runner zwj female by woman;', 'sub z z z by z3;', 'sub z z by z2;',
              'sub f f f by f3;', 'sub f f by f2;']
    addOpenTypeFeaturesFromString(font, 'languagesystem DFLT dflt; feature ccmp {\n' +
                                 '\n'.join(rules) + '\n} ccmp;')
    return font


def reference_private_states(font, glyphs):
    """Independent suffix hash and forward-feedback model on shaped glyphs."""
    from modifier_ligatures import discover, TONE_COEFFICIENTS, GENDER_COEFFICIENTS
    eligible, _, _ = discover(font)
    buckets = [font.getGlyphID(glyph) % 5 for glyph in glyphs]
    # One suffix hash, followed by a local remapping for the ternary seeds.
    hashes5 = [0] * len(glyphs)
    for i in range(len(glyphs)-1, -1, -1):
        hashes5[i] = ((-buckets[i]) % 5 if i == len(glyphs)-1 else
                      (2 * hashes5[i+1] + buckets[i] + 1) % 5)
    hashes3 = [(((h+b+1) % 5) + b+2) % 3 for h,b in zip(hashes5,buckets)]
    streams = []
    for base, coefficients, hashes in ((5, TONE_COEFFICIENTS, hashes5),
                                       (3, GENDER_COEFFICIENTS, hashes3)):
        history = []
        values = []
        for glyph, seed in zip(glyphs, hashes):
            value = seed
            if glyph in eligible:
                if len(history) >= 4:
                    register = history[-4:]
                    if register == [1, 0, 0, 0]:
                        value = 0
                    elif register == [0, 0, 0, 0]:
                        value = coefficients[-1] % base
                    else:
                        value = sum(c * register[-1-i] for i, c in enumerate(coefficients)) % base
                history.append(value)
            else:
                history = []
            values.append(value)
        streams.append(values)
    return streams


def reference_tones(font, following, count, current='🏃'):
    # Kept as a small harness API for the full-font package verifier.
    text = current * count
    if following and following != current and count >= 2:
        text = current + following + current * (count - 2)
    return reference_private_states(font, shape(font, text, calt=False))[0]


def reference_genders(font, following, count, current='🏃'):
    text = current * count
    if following and following != current and count >= 2:
        text = current + following + current * (count - 2)
    return reference_private_states(font, shape(font, text, calt=False))[1]


def reference_variations(font, text):
    from modifier_ligatures import discover
    tone_bases, gender_bases, _ = discover(font)
    raw = shape(font, text, calt=False)
    tones, genders = reference_private_states(font, raw)
    result = []
    cmap = font.getBestCmap()
    explicit = {cmap[cp] for cp in (*range(0x1F3FB, 0x1F400), 0x200D)}
    for i, (glyph, tone, gender) in enumerate(zip(raw, tones, genders)):
        if glyph not in tone_bases or (i+1 < len(raw) and raw[i+1] in explicit):
            result.append(glyph)
        elif gender and glyph in gender_bases:
            result.append(gender_bases[glyph][tone][gender-1])
        else:
            result.append(tone_bases[glyph][tone])
    return result


class ModifierTests(unittest.TestCase):
    def setUp(self):
        self.font = make_modifier_font()
        self.info = add_cluster_ligatures(self.font)

    def test_suffix_seeds_and_full_feedback(self):
        for n in (1, 2, 3, 4, 5, 7, 8, 9, 40, 1252):
            text = '🏃' * n
            actual = shape(self.font, text)
            self.assertEqual(actual, reference_variations(self.font, text))
            if n == 1252:
                tones = [int(name[-2]) for name in actual]
                genders = [int(name[-1]) for name in actual]
                self.assertEqual(tones[:625], tones[625:1250])
                self.assertEqual([tones[:625].count(t) for t in range(5)], [125] * 5)
                self.assertEqual(genders[:81], genders[81:162])
                self.assertEqual([genders[:81].count(g) for g in range(3)], [27] * 3)
        self.assertEqual(self.info['seeding'], 'reverse-suffix-all-source-glyphs')

    def test_first_four_states_use_suffix_then_full_feedback_wins(self):
        from modifier_ligatures import TONE_COEFFICIENTS, GENDER_COEFFICIENTS
        text = '🏃' * 12
        raw = shape(self.font, text, calt=False)
        tones, genders = reference_private_states(self.font, raw)
        actual = shape(self.font, text)
        self.assertEqual([int(g[-2]) for g in actual[:4]], tones[:4])
        self.assertEqual([int(g[-1]) for g in actual[:4]], genders[:4])
        self.assertGreater(len(set(tones[:4])), 1)
        self.assertEqual(set(genders[:4]), {0,1,2})
        self.assertEqual(int(actual[4][-2]), sum(c*tones[3-i] for i,c in enumerate(TONE_COEFFICIENTS)) % 5)
        self.assertEqual(int(actual[4][-1]), sum(c*genders[3-i] for i,c in enumerate(GENDER_COEFFICIENTS)) % 3)

    def test_gender_startup_covers_three_states_in_every_bucket(self):
        from copy import deepcopy
        from modifier_ligatures import GENDERS, TONES
        raw = deepcopy(self.font)
        for record in raw['GSUB'].table.FeatureList.FeatureRecord:
            if record.FeatureTag == 'calt':
                record.Feature.LookupListIndex = [i for i in record.Feature.LookupListIndex
                                                 if i not in self.info['calt_roots'][3:]]
                record.Feature.LookupCount = len(record.Feature.LookupListIndex)
        buckets = set()
        for ch in ('🏊','🚴','🧑','🧗','🏃'):
            buckets.add(self.font.getGlyphID(self.font.getBestCmap()[ord(ch)]) % 5)
            out = shape(raw, ch*4)
            self.assertEqual({GENDERS.index(g) for g in out if g in GENDERS}, {0,1,2})
        self.assertEqual(buckets, set(range(5)))
        # The former ternary sweep ignored insertion of two identical sources.
        self.assertNotEqual(shape(self.font,'🏃a')[0][-1], shape(self.font,'🏃aaa')[0][-1])
        self.assertEqual(self.info['gender_seeding'], 'base5-hash-and-source-bucket')

    def test_distant_noise_and_assembled_emoji_contribute(self):
        # The changed glyph is beyond a bounded lookahead and is not eligible.
        a = '🏃' + 'a' * 40 + 'a'
        b = '🏃' + 'a' * 40 + 'b'
        for text in (a, b, '🏃 a', '🏃 ab', '🏃🏃🏻', '🏃🏃🏿'):
            self.assertEqual(shape(self.font, text), reference_variations(self.font, text))
        self.assertNotEqual(shape(self.font, a)[0], shape(self.font, b)[0])
        self.assertNotEqual(shape(self.font, '🏃 a')[0], shape(self.font, '🏃 b')[0])
        self.assertNotEqual(shape(self.font, '🏃🏃🏻')[0], shape(self.font, '🏃🏃🏿')[0])
        self.assertEqual(shape(self.font, a)[1:], ['a'] * 41)

    def test_sources_include_noneligible_glyphs_and_native_outputs(self):
        from modifier_ligatures import source_glyphs, MARKERS
        sources = set(source_glyphs(self.font))
        self.assertTrue({'a', 'b', 'space', 'runner00', 'runner42', 'thumb30'} <= sources)
        self.assertFalse(sources & set(MARKERS))
        self.assertNotIn('zwj', sources)
        self.assertNotIn('.notdef', sources)
        self.assertNotIn('unused', sources)  # Unreachable outline, not input noise.

    def test_mixed_bases_share_both_clocks_and_singletons_vary(self):
        for text in ('🏃👩👍🧑'*30, '🏊🚴🧗🏃🧑'*20, '🏃'*12+'👩'+'🏃'*20):
            self.assertEqual(shape(self.font, text), reference_variations(self.font, text))
        outputs = []
        for base in ('🏃', '👩', '👨', '🧑', '👍', '🏊', '🚴', '🧗'):
            self.assertEqual(shape(self.font, base), reference_variations(self.font, base))
            outputs.extend(shape(self.font, base))
        self.assertEqual(set(g[-2] for g in outputs), set('01234'))

    def test_person_uses_separate_gender_bases_and_shared_history(self):
        for text in ('🧑'*40, '🧑🏃'*20):
            self.assertEqual(shape(self.font, text), reference_variations(self.font, text))
        self.assertEqual(shape(self.font, '🧑'*40, calt=False), ['person'] * 40)

    def test_person_explicit_gender_aliases_preserve_tone(self):
        for sign, base in (('♀', 'woman'), ('♂', 'man')):
            self.assertEqual(shape(self.font, '🧑\u200d' + sign), [base])
            for t in range(5):
                text = '🧑' + chr(0x1F3FB+t) + '\u200d' + sign
                self.assertEqual(shape(self.font, text), [f'{base}{t}0'])

    def test_explicit_sequences_and_calt_off(self):
        for t in range(5):
            for suffix, gender in (('', 0), ('\u200d♀', 1), ('\u200d♂', 2)):
                for variation_selector in ('', '\ufe0f'):
                    text = ('🏃' + chr(0x1F3FB+t) + suffix + variation_selector) * 3
                    self.assertEqual(shape(self.font, text), shape(self.font, text, calt=False))
                    if not variation_selector:
                        self.assertEqual(shape(self.font, text), [f'runner{t}{gender}'] * 3)
        self.assertEqual(shape(self.font, '🏃'*40, calt=False), ['runner'] * 40)
        self.assertEqual(shape(self.font, '🏃\u200d'), shape(self.font, '🏃\u200d', calt=False))

    def test_noise_resets_feedback_but_suffix_hash_crosses_it(self):
        for text in ('🏃'*20+' '+'🏃'*20, '🏃'*20+'🏃🏻'+'🏃'*20):
            self.assertEqual(shape(self.font, text), reference_variations(self.font, text))
            self.assertEqual(shape(self.font, text)[-20:], shape(self.font, '🏃'*20))
        self.assertNotEqual(shape(self.font, '🏃 a')[0], shape(self.font, '🏃 b')[0])

    def test_roundtrip_uninstall_and_reinstall(self):
        from modifier_ligatures import remove_modifier_ligatures
        before = shape(self.font, '🏃'*50)
        out = BytesIO(); self.font.save(out)
        font = TTFont(BytesIO(out.getvalue()))
        self.assertEqual(shape(font, '🏃'*50), before)
        remove_modifier_ligatures(font, self.info)
        remove_cluster_ligatures(font)
        original = make_modifier_font()
        self.assertEqual(font.getGlyphOrder(), original.getGlyphOrder())
        self.assertEqual(font.getBestCmap(), original.getBestCmap())
        self.assertEqual(font['OS/2'].usMaxContext, original['OS/2'].usMaxContext)
        self.assertEqual(font['GSUB'].compile(font), original['GSUB'].compile(original))
        add_cluster_ligatures(font)
        self.assertEqual(shape(font, '🏃'*50), before)

    def test_install_idempotent(self):
        before = self.font['GSUB'].compile(self.font)
        self.assertEqual(add_cluster_ligatures(self.font), self.info)
        self.assertEqual(before, self.font['GSUB'].compile(self.font))

    def test_modifiers_without_optional_cluster_artwork(self):
        from modifier_ligatures import remove_modifier_ligatures
        font = make_modifier_font()
        for lookup in font['GSUB'].table.LookupList.Lookup:
            for table in getattr(lookup, 'SubTable', []):
                if hasattr(table, 'ligatures'):
                    table.ligatures.pop('z', None); table.ligatures.pop('f', None)
        original = font['GSUB'].compile(font)
        info = add_cluster_ligatures(font)
        self.assertTrue(info['created_calt'])
        self.assertEqual(shape(font, '🏃'*30), shape(self.font, '🏃'*30))
        remove_modifier_ligatures(font, info)
        self.assertEqual(font['GSUB'].compile(font), original)

    def test_marker_collision_rejected(self):
        del self.font._deimoji_modifiers
        with self.assertRaisesRegex(ValueError, 'native baseline'):
            add_cluster_ligatures(self.font)

    def test_full_periods_include_zero_and_combined_period(self):
        from modifier_ligatures import stream, TONE_COEFFICIENTS, GENDER_COEFFICIENTS, TONE_SEED, GENDER_SEED
        registers = []
        for base, coefficients, seed, period in ((5, TONE_COEFFICIENTS, TONE_SEED, 625),
                                                 (3, GENDER_COEFFICIENTS, GENDER_SEED, 81)):
            values = stream(base, coefficients, seed, period+4)
            states = [tuple(values[i:i+4]) for i in range(period)]
            self.assertEqual(len(set(states)), period)
            self.assertIn((0,0,0,0), states)
            self.assertEqual(values[:4], values[period:period+4])
            self.assertEqual([values[:period].count(v) for v in range(base)], [base**3]*base)
            registers.append(states)
        self.assertEqual(len({(registers[0][i%625], registers[1][i%81]) for i in range(50625)}), 50625)

    def test_private_states_fold_and_noise_leftovers_are_swept(self):
        from copy import deepcopy
        from modifier_ligatures import MARKERS
        from cluster_ligatures import _ligature_tables
        raw = deepcopy(self.font)
        for record in raw['GSUB'].table.FeatureList.FeatureRecord:
            if record.FeatureTag == 'calt':
                record.Feature.LookupListIndex = record.Feature.LookupListIndex[:-3]
                record.Feature.LookupCount = len(record.Feature.LookupListIndex)
        text = '🏃'*1252
        tones, genders = reference_private_states(self.font, ['runner']*1252)
        glyphs = shape(raw, text)
        self.assertEqual(glyphs[::3], ['runner']*1252)
        self.assertEqual(glyphs[1::3], ['DEImojiTone'+str(t) for t in tones])
        self.assertEqual(glyphs[2::3], ['DEImojiGender'+str(g) for g in genders])
        self.assertFalse(set(MARKERS) & set(self.font.getBestCmap().values()))
        incomplete = deepcopy(self.font)
        for lookup in incomplete['GSUB'].table.LookupList.Lookup[self.info['original_lookup_count']:]:
            for table in _ligature_tables(lookup):
                for base, rules in list(table.ligatures.items()):
                    table.ligatures[base] = [r for r in rules if not any(n in MARKERS for n in r.Component)]
        self.assertEqual(shape(incomplete, '🏃'*40+' a '+'🏃🏻'),
                         ['runner']*40+['space','a','space','runner00'])
        self.assertEqual(shape(self.font, 'ab a'), ['a','b','space','a'])
        self.assertFalse(set(MARKERS) & set(shape(self.font, text)))


class ZombieVariantTests(unittest.TestCase):
    def setUp(self):
        from zombie_artwork import install_registry
        self.font = make_modifier_font()
        self.variants = {f'z{n}':[f'crowd{n}v{i}' for i in range(5)] for n in (2,3)}
        names = [g for values in self.variants.values() for g in values]
        self.font.setGlyphOrder(self.font.getGlyphOrder()+names)
        for name in names:
            self.font['glyf'].glyphs[name] = TTGlyphPen(None).glyph()
            self.font['hmtx'].metrics[name] = (1000,0)
        self.font['maxp'].numGlyphs = len(self.font.getGlyphOrder())
        install_registry(self.font,self.variants)
        self.original = self.font['GSUB'].compile(self.font)
        self.info = add_cluster_ligatures(self.font)

    def test_five_variants_follow_one_shared_base_five_clock(self):
        for n in (1,2,3,4,8,40,4000):
            groups = reference(n)
            inputs = [f'z{size}' if size > 1 else 'z' for size in groups]
            tones, _ = reference_private_states(self.font,inputs)
            expected = [self.variants[base][tone] if base in self.variants else base
                        for base,tone in zip(inputs,tones)]
            actual = shape(self.font,'🧟'*n)
            self.assertEqual(actual,expected)
            if n == 4000:
                self.assertEqual(set(actual),{g for v in self.variants.values() for g in v})
        self.assertEqual(shape(self.font,'🧟'),['z'])
        self.assertEqual(shape(self.font,'🧟'*40,calt=False),['z']*40)
        self.assertEqual(shape(self.font,'🧟\u200d♀'),shape(self.font,'🧟\u200d♀',calt=False))
        self.assertEqual(self.info['custom_bases'],2)
        self.assertEqual(self.info['tone_bases'],8)

    def test_mixed_people_and_crowds_keep_both_histories(self):
        from modifier_ligatures import discover
        text = '🏃'*12 + '🧟'*20 + '🏃'*20
        inputs = ['runner']*12+[f'z{n}' for n in reference(20)]+['runner']*20
        tones,genders = reference_private_states(self.font,inputs)
        bases,gendered,_ = discover(self.font)
        expected = [gendered[b][t][g-1] if g and b in gendered else bases[b][t]
                    for b,t,g in zip(inputs,tones,genders)]
        self.assertEqual(shape(self.font,text),expected)

    def test_registry_survives_serialization_and_uninstall(self):
        from modifier_ligatures import remove_modifier_ligatures
        from zombie_artwork import variant_mappings
        before = shape(self.font,'🧟'*80)
        data=BytesIO();self.font.save(data)
        font=TTFont(BytesIO(data.getvalue()))
        self.assertEqual(variant_mappings(font),self.variants)
        self.assertEqual(shape(font,'🧟'*80),before)
        remove_modifier_ligatures(font,self.info);remove_cluster_ligatures(font)
        self.assertEqual(font['GSUB'].compile(font),self.original)

    def test_artwork_is_complete_distinct_and_unencoded(self):
        from zombie_artwork import ART,NAMES,verify_bundle
        self.assertEqual(len(verify_bundle()),64)
        for n in (2,3):
            pngs=[]
            for i in range(5):
                path=ART/'png/128'/f'zombie{n}_v{i}.png'
                data=path.read_bytes();pngs.append(data)
                self.assertEqual(struct.unpack('>II',data[16:24]),(184 if n==2 else 240,128))
            self.assertEqual(len(set(pngs)),5)
        mini=TTFont(ART/'Zombies-COLRv1.ttf')
        self.assertTrue(set(NAMES).issubset(mini.getGlyphOrder()))
        self.assertFalse(set(NAMES).intersection(mini.getBestCmap().values()))


if __name__ == '__main__':
    unittest.main()

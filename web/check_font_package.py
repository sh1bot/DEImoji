"""Verify the actual packaged font binaries, using the HarfBuzz test harness.

Called by check_browser after packaging, so fixture-font tests alone cannot
accidentally certify stale or incorrectly patched downloadable fonts.
"""
import hashlib
import json
from pathlib import Path
import sys

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))
from test_cluster_ligatures import shape, reference_tones, reference_genders, reference_variations
from modifier_ligatures import discover
from cluster_ligatures import _ligature_tables
from supplemental_artwork import ART, NAMES, _verify_bundle


def check_font_package(site):
    metadata = json.loads((site / 'build.json').read_text())
    bundle = _verify_bundle()
    for name, expected in metadata['page_hashes'].items():
        assert hashlib.sha256((site / name).read_bytes()).hexdigest() == expected, ('page checksum', name)
    for name, expected in metadata['font_hashes'].items():
        actual = hashlib.sha256((site / 'fonts' / name).read_bytes()).hexdigest()
        assert actual == expected, ('font checksum', name, actual, expected)
    checked = []
    for name in ('DEImoji-CBDT.ttf', 'DEImoji-COLRv1.ttf', 'DEImoji-COLRv1.woff2'):
        font = TTFont(site / 'fonts' / name, recalcBBoxes=False)
        # WOFF2 is the same logical COLRv1 font and must pass shaping too.
        published = name.replace('.woff2', '.ttf')
        info = metadata['modifiers'][published]
        assert info['version'] >= 3, ('stale modifier bundle', name)
        assert info['seeding'] == 'reverse-suffix-all-source-glyphs'
        assert info['state_periods'] == [625, 81]
        assert info['combined_period'] == 50625
        assert metadata['artwork'][published]['bundle'] == bundle, ('stale artwork bundle', name)
        assert metadata['artwork'][published]['style'] == 'noto-white-smile-v2'
        # Save a decoded webfont as TTF for the HarfBuzz harness.
        font.flavor = None
        tones, genders, _ = discover(font)
        base = font.getBestCmap()[0x1F3C3]
        ts = reference_tones(font, '🏃', 1252)
        gs = reference_genders(font, '🏃', 1252)
        expected = [genders[base][t][g-1] if g else tones[base][t]
                    for t, g in zip(ts, gs)]
        actual = shape(font, '🏃' * 1252)
        assert actual == expected, ('full-font feedback', name)
        markers = set(font.getGlyphOrder()[-info['marker_count']:])
        assert not markers.intersection(font.getBestCmap().values())
        assert not markers.intersection(actual), ('leaked private states', name)
        assert shape(font, '🏃' * 8, calt=False) == [base] * 8
        explicit = ' '.join('🏃' + chr(0x1F3FB+t) + suffix for t in range(5)
                            for suffix in ('', '\u200d♀', '\u200d♂',
                                           '\u200d♀\ufe0f', '\u200d♂\ufe0f'))
        assert shape(font, explicit) == shape(font, explicit, calt=False), ('explicit modifiers', name)
        noise_results = []
        for tail in ('🌻', '💩', '🏃🏻', '🏃🏿'):
            text = '🏃' + ' ' * 40 + tail
            actual_noise = shape(font, text)
            assert actual_noise == reference_variations(font, text), ('distant seed noise', name, tail)
            noise_results.append(actual_noise[0])
        assert len(set(noise_results)) > 1, ('suffix noise ignored', name)
        if 'CBDT' in font:
            # Compare embedded PNG bytes, not just a claimed manifest label.
            poop = font.getBestCmap()[0x1F4A9]
            outputs = {}
            for lookup in font['GSUB'].table.LookupList.Lookup:
                for table in _ligature_tables(lookup):
                    for lig in table.ligatures.get(poop, []):
                        if len(lig.Component) in (1, 2) and set(lig.Component) == {poop}:
                            outputs[len(lig.Component)+1] = lig.LigGlyph
            assert set(outputs) == {2, 3}
            for count, asset in zip((2, 3), NAMES):
                assert font['CBDT'].strikeData[0][outputs[count]].imageData == (
                    ART / 'png/128' / (asset + '.png')).read_bytes(), ('embedded poop PNG', count)
        checked.append(name)
    return dict(commit=metadata['commit'], font_hashes=metadata['font_hashes'],
                page_hashes=metadata['page_hashes'],
                artwork_bundle=bundle, artwork_style='noto-white-smile-v2',
                shaped_fonts=checked, state_periods=[625, 81], combined_period=50625,
                feedback_outputs_checked_per_font=1252,
                explicit_runner_sequences_checked_per_font=25,
                seeding='reverse-suffix-all-source-glyphs',
                distant_noneligible_noise_checked=True,
                private_state_cleanup=True, bitmap_artwork_bytes_verified=True)

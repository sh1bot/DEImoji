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
from test_cluster_ligatures import shape, reference, reference_cluster_stream, reference_clusters, reference_private_states, reference_tones, reference_genders, reference_variations
from modifier_ligatures import discover
from cluster_ligatures import _ligature_tables
from supplemental_artwork import ART, NAMES, _verify_bundle
from fixed_cluster_artwork import FAMILIES as FIXED_FAMILIES, ART as FIXED_ART, verify_bundle as verify_fixed
from zombie_artwork import variant_mappings, verify_bundle as verify_zombies, ART as ZOMBIES, NAMES as ZOMBIE_NAMES


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
        assert info['version'] >= 5, ('stale modifier bundle', name)
        assert info['seeding'] == 'reverse-suffix-all-source-glyphs'
        assert info['gender_seeding'] == 'base5-hash-and-source-bucket'
        assert info['state_periods'] == [625, 81]
        assert info['combined_period'] == 50625
        assert info['binary_degree']==5 and info['binary_period']==31
        assert info['feedback_context']=='all-expanded-source-glyphs'
        assert info['marker_layout']=='residue-aligned'
        assert [gid%5 for gid in info['tone_marker_gids']]==list(range(5))
        assert [gid%3 for gid in info['gender_marker_gids']]==list(range(3))
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
        elder = font.getBestCmap()[0x1F9D3]
        assert elder in genders, ('older person missing gender mappings', name)
        elderly = shape(font,'🧓'*1252)
        assert elderly == reference_variations(font,'🧓'*1252), ('older-person feedback',name)
        choices = [set(tones[elder])] + [set(row[g] for row in genders[elder]) for g in (0,1)]
        first = shape(font,'🧓'*4)
        assert all(set(first).intersection(group) for group in choices), ('older-person genders',name)
        cmap = font.getBestCmap()
        for cp, target_cp, g in ((0x2640,0x1F475,0),(0x2642,0x1F474,1)):
            assert shape(font,'🧓\u200d'+chr(cp)) == [cmap[target_cp]]
            for t in range(5):
                tone = chr(0x1F3FB+t)
                target = genders[elder][t][g]
                assert shape(font,'🧓'+tone+'\u200d'+chr(cp)) == [target]
                for suffix in ('','\ufe0f'):
                    typed = chr(target_cp)+tone+suffix
                    assert shape(font,typed) == shape(font,typed,calt=False), ('explicit older person',name)
        # Inspect actual private gender seeds before either feedback pass.
        # Cover every source bucket, rather than checking only one runner ID.
        cmap = font.getBestCmap()
        characters = {glyph:chr(cp) for cp,glyph in cmap.items()}
        bucket_examples = {}
        for glyph in genders:
            bucket_examples.setdefault(font.getGlyphID(glyph) % 5, characters[glyph])
        assert set(bucket_examples) == set(range(5)), ('missing gender seed buckets', name)
        originals = []
        for record in font['GSUB'].table.FeatureList.FeatureRecord:
            if record.FeatureTag == 'calt':
                originals.append((record,record.Feature.LookupListIndex[:]))
                record.Feature.LookupListIndex = [i for i in record.Feature.LookupListIndex
                                                 if i not in info['calt_roots'][3:]]
                record.Feature.LookupCount = len(record.Feature.LookupListIndex)
        private_genders = [font.getGlyphOrder()[gid] for gid in info['gender_marker_gids']]
        try:
            for bucket,ch in bucket_examples.items():
                seed_glyphs = shape(font,ch*4)
                seeds = [private_genders.index(g) for g in seed_glyphs if g in private_genders]
                assert len(seeds) == 4 and set(seeds) == {0,1,2}, ('poor gender startup',name,bucket,seeds)
        finally:
            for record,indices in originals:
                record.Feature.LookupListIndex = indices
                record.Feature.LookupCount = len(indices)
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
        variants = variant_mappings(font)
        zombie_info = metadata['artwork'][published]['zombies']
        assert zombie_info['bundle'] == verify_zombies()
        assert len(variants) == 2 and all(len(v) == 5 for v in variants.values())
        order = font.getGlyphOrder()
        crowd_bases = [order[gid] for gid in zombie_info['cluster_gids']]
        units = [crowd_bases[size-2] for size in reference(4000)]
        states, _ = reference_private_states(font, units)
        expected_crowds = [variants[b][state] for b,state in zip(units,states)]
        actual_crowds = shape(font, '🧟'*4000)
        assert actual_crowds == expected_crowds, ('zombie composition feedback', name)
        assert set(actual_crowds) == {g for choices in variants.values() for g in choices}
        assert shape(font, '🧟') == shape(font, '🧟', calt=False)
        assert shape(font, '🧟\u200d♀') == shape(font, '🧟\u200d♀', calt=False)
        if 'COLR' in font:
            painted = {r.BaseGlyph for r in font['COLR'].table.BaseGlyphList.BaseGlyphPaintRecord}
            assert set(actual_crowds).issubset(painted), ('missing zombie paint graph', name)
        if 'CBDT' in font:
            for row, size in zip(zombie_info['variant_gids'], (2,3)):
                for i,gid in enumerate(row):
                    assert font['CBDT'].strikeData[0][order[gid]].imageData == (
                        ZOMBIES/'png/128'/f'zombie{size}_v{i}.png').read_bytes(), ('zombie bitmap',size,i)
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
        fixed=metadata['artwork'][published]['clusters']
        assert fixed['bundle']==verify_fixed(), ('stale fixed artwork',name)
        outputs={(e['codepoint'],e['size']):order[e['gid']] for e in fixed['entries']}
        for cp in FIXED_FAMILIES.values():
            base=cmap[cp]
            text='';expected=[];plain=[]
            for n in (1,2,3,4,5,6,7,8,15,36,80,160):
                text+=chr(cp)*n+' '
                plain.extend([base]*n+[cmap[32]])
                expected.extend(base if size==1 else outputs[cp,size] for size in reference(n))
                expected.append(cmap[32])
            expected=reference_cluster_stream(font,plain)
            if cp==0x1F386:
                joins={f'fireworks{n}':outputs[cp,n] for n in (2,3)}
                joins.update({key:order[gid] for key,gid in fixed['joining_gids'].items()})
                reverse={joins[f'fireworks{n}']:n for n in (2,3)}
                raw=expected[:]
                for i,glyph in enumerate(raw):
                    if glyph not in reverse:continue
                    left=i>0 and raw[i-1] in reverse;right=i+1<len(raw) and raw[i+1] in reverse
                    position='_middle' if left and right else '_end' if left else '_start' if right else ''
                    expected[i]=joins[f'fireworks{reverse[glyph]}'+position]
            assert shape(font,text)==expected, ('decorative LFSR grouping',name,cp)
            assert shape(font,text,calt=False)==plain
        mixed_text='💩'*23+'🌻'*40+'🎉'*21+'🔥'*40
        expected=reference_clusters(font,mixed_text)
        assert shape(font,mixed_text)==expected, ('shared binary history',name)
        # Startup follows the last observed bit, rather than repeating four trios.
        for cp in FIXED_FAMILIES.values():
            actual36=shape(font,chr(cp)*36)
            if cp==0x1F386:
                isolated={order[gid]:outputs[cp,2 if key.startswith('fireworks2_') else 3] for key,gid in fixed['joining_gids'].items()}
                actual36=[isolated.get(g,g) for g in actual36]
            assert actual36[:5]==[outputs[cp,size] for size in (3,2,3,2,3)]
        noise_mix='🏃'*8+' 🌻🌻🌻🌻🌻 '+'💩'*15+'🏃'*8
        assert shape(font,noise_mix)==reference_variations(font,noise_mix)
        for entry in fixed['entries']:
            glyph=order[entry['gid']]
            if 'CBDT' in font:
                assert font['CBDT'].strikeData[0][glyph].imageData==(FIXED_ART/'png/128'/(entry['name']+'.png')).read_bytes()
            else:
                assert glyph in painted, ('missing fixed paint',name,entry)
        for asset,gid in fixed.get('joining_gids',{}).items():
            glyph=order[gid]
            if 'CBDT' in font:
                assert font['CBDT'].strikeData[0][glyph].imageData==(FIXED_ART/'png/128'/(asset+'.png')).read_bytes()
            else:assert glyph in painted, ('missing joined firework paint',name,asset)
        checked.append(name)
    return dict(commit=metadata['commit'], font_hashes=metadata['font_hashes'],
                page_hashes=metadata['page_hashes'],
                artwork_bundle=bundle, artwork_style='noto-white-smile-v2',
                shaped_fonts=checked, state_periods=[625, 81], combined_period=50625,
                feedback_outputs_checked_per_font=1252,
                explicit_runner_sequences_checked_per_font=25,
                seeding='reverse-suffix-all-source-glyphs',
                gender_seeding='base5-hash-and-source-bucket',
                gender_seed_buckets_checked=[0,1,2,3,4],
                gender_states_in_first_four_repeats=3,
                distant_noneligible_noise_checked=True,
                fixed_cluster_artwork_checked=8, fixed_cluster_grouping='binary-lfsr-period-31',
                binary_startup='opposite-previous', binary_shared_history=True, binary_degree=5, binary_period=31,
                feedback_context='all-expanded-source-glyphs', marker_layout='residue-aligned',
                zombie_compositions_checked=10, zombie_grouping_input_length=4000,
                zombie_artwork_bundle=verify_zombies(),
                older_person_genders_checked=True,
                older_person_feedback_outputs_checked=1252,
                private_state_cleanup=True, bitmap_artwork_bytes_verified=True)


def zombie_proof_font(site, fmt, fixed=False):
    """Test-only cmap for painting private glyphs individually. Never published."""
    import base64
    from io import BytesIO
    from fontTools.ttLib import newTable
    from fontTools.ttLib.tables._c_m_a_p import CmapSubtable
    filename = 'DEImoji-COLRv1.ttf' if fmt == 'colr' else 'DEImoji-CBDT.ttf'
    font = TTFont(site/'fonts'/filename, recalcBBoxes=False)
    metadata = json.loads((site/'build.json').read_text())
    rows = ([e['gid'] for e in metadata['artwork'][filename]['clusters']['entries']],) if fixed else metadata['artwork'][filename]['zombies']['variant_gids']
    order = font.getGlyphOrder()
    table = CmapSubtable.newSubtable(12)
    table.platformID, table.platEncID, table.language = 3, 10, 0
    table.cmap = {65+i:order[gid] for i,gid in enumerate(g for row in rows for g in row)}
    font['cmap'] = newTable('cmap');font['cmap'].tableVersion=0;font['cmap'].tables=[table]
    for tag in ('GSUB','GPOS'):
        if tag in font:del font[tag]
    data=BytesIO();font.save(data)
    return 'data:font/ttf;base64,'+base64.b64encode(data.getvalue()).decode()

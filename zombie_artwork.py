"""Install ten unencoded zombie crowd glyphs and their base-five registry.

DVAR is a private, normally inactive alternate feature that records each
cluster's five artwork choices. The default calt pipeline reads that registry
at build time and folds private state directly into the selected glyph.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont

ART = Path(__file__).resolve().parent / 'ligatures/supplemental/zombies'
NAMES = tuple(f'zombie{size}_v{variant}' for size in (2, 3) for variant in range(5))
FEATURE = 'DVAR'


def verify_bundle():
    manifest = json.loads((ART/'manifest.json').read_text())
    if manifest['version'] != 1 or len(manifest['variants']) != 10:
        raise ValueError('Unknown zombie artwork bundle')
    for name, expected in manifest['files'].items():
        if hashlib.sha256((ART/name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Zombie artwork checksum mismatch: {name}')
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def variant_mappings(font):
    if 'GSUB' not in font:
        return {}
    table = font['GSUB'].table
    result = {}
    for record in table.FeatureList.FeatureRecord:
        if record.FeatureTag != FEATURE:
            continue
        for index in record.Feature.LookupListIndex:
            lookup = table.LookupList.Lookup[index]
            for sub in lookup.SubTable:
                kind = lookup.LookupType
                if kind == 7:
                    kind, sub = sub.ExtensionLookupType, sub.ExtSubTable
                if kind != 3:
                    raise ValueError('Unexpected DVAR registry lookup')
                for base, choices in sub.alternates.items():
                    if len(choices) != 5:
                        raise ValueError('DVAR requires five artwork choices')
                    result[base] = list(choices)
    return result


def install_registry(font, variants):
    from modifier_ligatures import _languages
    table = font['GSUB'].table
    records = table.FeatureList.FeatureRecord
    if any(r.FeatureTag == FEATURE for r in records):
        raise ValueError('DVAR registry already exists')
    source = ['languagesystem DFLT dflt;', f'feature {FEATURE} {{']
    source += [f"sub {base} from [{' '.join(choices)}];" for base, choices in variants.items()]
    source.append(f'}} {FEATURE};')
    temp = TTFont(); temp.setGlyphOrder(font.getGlyphOrder())
    addOpenTypeFeaturesFromString(temp, '\n'.join(source), tables=['GSUB'])
    extra = temp['GSUB'].table
    start = len(table.LookupList.Lookup)
    table.LookupList.Lookup.extend(deepcopy(extra.LookupList.Lookup))
    table.LookupList.LookupCount = len(table.LookupList.Lookup)
    record = deepcopy(extra.FeatureList.FeatureRecord[0])
    record.Feature.LookupListIndex = [start+i for i in record.Feature.LookupListIndex]
    old = list(records)
    records.append(record); records.sort(key=lambda r:r.FeatureTag)
    remap = {i:records.index(r) for i,r in enumerate(old)}
    index = records.index(record)
    for language in _languages(table):
        language.FeatureIndex = sorted([remap[i] for i in language.FeatureIndex]+[index])
        language.FeatureCount = len(language.FeatureIndex)
        if language.ReqFeatureIndex != 0xFFFF:
            language.ReqFeatureIndex = remap[language.ReqFeatureIndex]
    table.FeatureList.FeatureCount = len(records)
    return dict(start=start, count=len(extra.LookupList.Lookup))


def add_zombie_artwork(font):
    from supplemental_artwork import _tables, _append_bitmaps, _append_colr
    if 'GSUB' not in font or 0x1F9DF not in font.getBestCmap():
        return None
    base = font.getBestCmap()[0x1F9DF]
    clusters = {len(lig.Component)+1:lig.LigGlyph for table in _tables(font)
                for lig in table.ligatures.get(base, [])
                if len(lig.Component) in (1,2) and set(lig.Component) == {base}}
    if set(clusters) != {2,3}:
        return None
    if variant_mappings(font) or any(n.startswith('DEImojiZombie') for n in font.getGlyphOrder()):
        raise ValueError('Install zombie artwork only on a clean native baseline')
    info = dict(version=1, bundle=verify_bundle(), style='noto-zombie-crowds-v1',
                original_glyph_count=len(font.getGlyphOrder()),
                advance_max=font['hhea'].advanceWidthMax,
                bounds={k:getattr(font['head'],k) for k in ('xMin','yMin','xMax','yMax')},
                horizontal={k:getattr(font['hhea'],k) for k in
                            ('minLeftSideBearing','minRightSideBearing','xMaxExtent')})
    names = [f'DEImojiZombie{size}V{i}' for size in (2,3) for i in range(5)]
    if 'CBDT' in font:
        outputs = _append_bitmaps(font,info,art=ART,assets=NAMES,output_names=names,base_cp=0x1F9DF)
    else:
        outputs = _append_colr(font,info,art=ART,filename='Zombies-COLRv1.ttf',
                               output_sources=NAMES,output_names=names,base_cp=0x1F9DF,
                               part_prefix='DEImojiZombiePart')
    info['glyph_count'] = len(font.getGlyphOrder())-info['original_glyph_count']
    variants = {clusters[2]:outputs[:5], clusters[3]:outputs[5:]}
    info['registry'] = install_registry(font, variants)
    info['cluster_gids'] = [font.getGlyphID(clusters[n]) for n in (2,3)]
    info['variant_gids'] = [[font.getGlyphID(g) for g in choices] for choices in variants.values()]
    font._deimoji_zombies = info
    return info


def remove_zombie_artwork(font, info):
    from modifier_ligatures import _languages
    from supplemental_artwork import _remove_artwork_tail
    table = font['GSUB'].table
    start, count = info['registry']['start'], info['registry']['count']
    records = table.FeatureList.FeatureRecord
    features = [(i,r) for i,r in enumerate(records) if r.FeatureTag == FEATURE]
    if (info['version'] != 1 or len(features) != 1 or len(table.LookupList.Lookup) != start+count
            or features[0][1].Feature.LookupListIndex != list(range(start,start+count))):
        raise ValueError('Unrecognized zombie registry metadata')
    variants = variant_mappings(font)
    outputs = {g for choices in variants.values() for g in choices}
    expected = {font.getGlyphOrder()[gid] for row in info['variant_gids'] for gid in row}
    if outputs != expected or len(outputs) != 10 or outputs.intersection(font.getBestCmap().values()):
        raise ValueError('Unrecognized zombie artwork outputs')
    index = features[0][0]
    for i,r in enumerate(records):
        if i != index and any(n >= start for n in r.Feature.LookupListIndex):
            raise ValueError('Zombie registry lookup is shared')
    for language in _languages(table):
        if language.ReqFeatureIndex == index:
            raise ValueError('Refusing to remove required DVAR feature')
        language.FeatureIndex = [i-(i>index) for i in language.FeatureIndex if i != index]
        language.FeatureCount = len(language.FeatureIndex)
        if language.ReqFeatureIndex != 0xFFFF:
            language.ReqFeatureIndex -= language.ReqFeatureIndex > index
    records.pop(index); table.FeatureList.FeatureCount = len(records)
    del table.LookupList.Lookup[start:]; table.LookupList.LookupCount = start
    _remove_artwork_tail(font,info,outputs)
    if hasattr(font,'_deimoji_zombies'):
        del font._deimoji_zombies

"""Append the small poop artwork pack to cached CBDT/COLRv1 fonts.

Original glyph IDs are preserved. Restoration metadata lives in build.json,
allowing published fonts to bootstrap the unchanged native-artwork cache.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct

from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.otBase import BaseTable
from fontTools.ttLib.tables.C_B_D_T_ import cbdt_bitmap_format_17
from fontTools.ttLib.tables.E_B_L_C_ import eblc_index_sub_table_1

ART = Path(__file__).resolve().parent / 'ligatures/supplemental/poop'
NAMES = tuple('emoji_u' + '_'.join(['1f4a9'] * n) for n in (2, 3))


def _tables(font):
    from cluster_ligatures import _ligature_tables
    gsub = font['GSUB'].table
    return [table for record in gsub.FeatureList.FeatureRecord if record.FeatureTag == 'ccmp'
            for index in record.Feature.LookupListIndex
            for table in _ligature_tables(gsub.LookupList.Lookup[index])]


def _outputs(font):
    base = font.getBestCmap()[0x1F4A9]
    return {len(lig.Component) + 1: lig.LigGlyph for table in _tables(font)
            for lig in table.ligatures.get(base, [])
            if len(lig.Component) in (1, 2) and set(lig.Component) == {base}}


def _verify_bundle():
    manifest = json.loads((ART / 'manifest.json').read_text())
    if manifest['version'] != 1:
        raise ValueError('Unknown supplemental artwork version')
    for name, expected in manifest['files'].items():
        if hashlib.sha256((ART / name).read_bytes()).hexdigest() != expected:
            raise ValueError(f'Supplemental artwork checksum mismatch: {name}')
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def _append_metrics(font, names, metrics, vertical):
    font.setGlyphOrder(font.getGlyphOrder() + names)
    for name, horizontal in zip(names, metrics):
        font['hmtx'].metrics[name] = horizontal
        if 'vmtx' in font:
            font['vmtx'].metrics[name] = vertical
    font['maxp'].numGlyphs = len(font.getGlyphOrder())
    font['hhea'].advanceWidthMax = max(font['hhea'].advanceWidthMax,
                                      max(advance for advance, bearing in metrics))


def _append_bitmaps(font, info, art=ART, assets=NAMES, output_names=None, base_cp=0x1F4A9):
    base = font.getBestCmap()[base_cp]
    if len(font['CBDT'].strikeData) != 1 or len(font['CBLC'].strikes) != 1:
        raise ValueError('Supplemental bitmap artwork expects the native 128px strike')
    strike = font['CBLC'].strikes[0]
    old = font['CBDT'].strikeData[0][base]
    if old.metrics.height != 128:
        raise ValueError('Unexpected native bitmap height')
    names = output_names or ['DEImojiPoop2', 'DEImojiPoop3']
    pngs = [(art / 'png/128' / (name + '.png')).read_bytes() for name in assets]
    sizes = [struct.unpack('>II', png[16:24]) for png in pngs]
    if any(h != 128 or not 0 < w <= 255 for w, h in sizes):
        raise ValueError('Supplemental bitmap exceeds CBDT metrics')
    advance_scale = font['hmtx'][base][0] / old.metrics.Advance
    vertical = font['vmtx'][base] if 'vmtx' in font else None
    glyf = font['glyf'] if 'glyf' in font else None
    _append_metrics(font, names, [(round(w * advance_scale), 0) for w, h in sizes], vertical)
    if glyf is not None:
        for name in names:
            glyf.glyphs[name] = TTGlyphPen(None).glyph()
    info['bitmap'] = dict(subtables=len(strike.indexSubTables),
                          end=strike.bitmapSizeTable.endGlyphIndex,
                          width=strike.bitmapSizeTable.hori.widthMax)
    subtable = eblc_index_sub_table_1(None, font)
    subtable.indexFormat, subtable.imageFormat, subtable.imageDataOffset = 1, 17, 0
    subtable.names = names
    subtable.firstGlyphIndex = font.getGlyphID(names[0])
    subtable.lastGlyphIndex = font.getGlyphID(names[-1])
    strike.indexSubTables.append(subtable)
    strike.bitmapSizeTable.endGlyphIndex = subtable.lastGlyphIndex
    strike.bitmapSizeTable.hori.widthMax = max(info['bitmap']['width'], max(w for w, h in sizes))
    for name, png, (w, h) in zip(names, pngs, sizes):
        glyph = cbdt_bitmap_format_17(None, font)
        glyph.metrics = deepcopy(old.metrics)
        glyph.metrics.width = glyph.metrics.Advance = w
        glyph.imageData = png
        font['CBDT'].strikeData[0][name] = glyph
    return names


def _remap(value, glyphs, colors, layer_offset):
    if isinstance(value, list):
        for child in value:
            _remap(child, glyphs, colors, layer_offset)
    elif isinstance(value, BaseTable):
        for key, child in vars(value).items():
            if key in ('Glyph', 'BaseGlyph'):
                setattr(value, key, glyphs[child])
            elif key == 'PaletteIndex' and child != 0xFFFF:
                setattr(value, key, colors[child])
            elif key == 'FirstLayerIndex':
                setattr(value, key, child + layer_offset)
            else:
                _remap(child, glyphs, colors, layer_offset)


def _append_colr(font, info, art=ART, filename='Poop-COLRv1.ttf', output_sources=None,
                 output_names=None, base_cp=0x1F4A9, part_prefix='DEImojiPoopPart'):
    mini = TTFont(art / filename, recalcBBoxes=False)
    if (font['COLR'].version != 1 or mini['COLR'].version != 1 or
            font['head'].unitsPerEm != mini['head'].unitsPerEm or
            len(font['CPAL'].palettes) != 1 or len(mini['CPAL'].palettes) != 1):
        raise ValueError('Incompatible supplemental COLRv1 artwork')
    if output_sources is None:
        outputs = _outputs(mini)
        if set(outputs) != {2, 3}:
            raise ValueError('Missing supplemental COLRv1 ligatures')
        output_sources = [outputs[2], outputs[3]]
    output_names = output_names or ['DEImojiPoop2', 'DEImojiPoop3']
    sources = list(output_sources) + [name for name in mini.getGlyphOrder()
               if name != '.notdef' and name not in output_sources]
    names = list(output_names) + [f'{part_prefix}{i}' for i in range(len(sources)-len(output_sources))]
    mapping = dict(zip(sources, names))
    mapping['.notdef'] = '.notdef'
    base = font.getBestCmap()[base_cp]
    vertical = font['vmtx'][base] if 'vmtx' in font else None
    # Decode loca/glyf against the original glyph count before appending IDs.
    glyf = font['glyf']
    _append_metrics(font, names, [mini['hmtx'][name] for name in sources], vertical)
    for source, name in zip(sources, names):
        glyph = deepcopy(mini['glyf'][source])
        if glyph.isComposite():
            for component in glyph.components:
                component.glyphName = mapping[component.glyphName]
        glyf.glyphs[name] = glyph
    for name in names:
        glyph = glyf[name]
        if glyph.numberOfContours:
            glyph.recalcBounds(glyf)
            for key, reduce in (('xMin', min), ('yMin', min), ('xMax', max), ('yMax', max)):
                setattr(font['head'], key, reduce(getattr(font['head'], key), getattr(glyph, key)))
            advance, bearing = font['hmtx'][name]
            width = glyph.xMax - glyph.xMin
            font['hhea'].minLeftSideBearing = min(font['hhea'].minLeftSideBearing, bearing)
            font['hhea'].minRightSideBearing = min(font['hhea'].minRightSideBearing, advance-bearing-width)
            font['hhea'].xMaxExtent = max(font['hhea'].xMaxExtent, bearing+width)
    palette = font['CPAL'].palettes[0]
    original_colors = len(palette)
    lookup = {tuple(color): i for i, color in enumerate(palette)}
    colors = {}
    for i, color in enumerate(mini['CPAL'].palettes[0]):
        key = tuple(color)
        if key not in lookup:
            lookup[key] = len(palette)
            palette.append(deepcopy(color))
            if font['CPAL'].version == 1 and font['CPAL'].paletteEntryLabels is not None:
                font['CPAL'].paletteEntryLabels.append(0xFFFF)
        colors[i] = lookup[key]
    font['CPAL'].numPaletteEntries = len(palette)
    table, extra = font['COLR'].table, mini['COLR'].table
    info['colr'] = dict(colors=original_colors, bases=len(table.BaseGlyphList.BaseGlyphPaintRecord),
                        layers=len(table.LayerList.Paint), had_clips=table.ClipList is not None)
    layer_offset = len(table.LayerList.Paint)
    layers = deepcopy(extra.LayerList.Paint)
    records = deepcopy(extra.BaseGlyphList.BaseGlyphPaintRecord)
    _remap(layers, mapping, colors, layer_offset)
    _remap(records, mapping, colors, layer_offset)
    table.LayerList.Paint.extend(layers)
    table.LayerList.LayerCount = len(table.LayerList.Paint)
    table.BaseGlyphList.BaseGlyphPaintRecord.extend(records)
    table.BaseGlyphList.BaseGlyphCount = len(table.BaseGlyphList.BaseGlyphPaintRecord)
    if extra.ClipList is not None:
        if table.ClipList is None:
            table.ClipList = ot.ClipList()
            table.ClipList.Format, table.ClipList.clips = 1, {}
        table.ClipList.clips.update({mapping[name]: deepcopy(box)
                                    for name, box in extra.ClipList.clips.items()})
    return names[:len(output_sources)]


def add_supplemental_artwork(font):
    if hasattr(font, '_deimoji_artwork'):
        return font._deimoji_artwork
    if ('GSUB' not in font or 0x1F4A9 not in font.getBestCmap() or
            not ('CBDT' in font or 'COLR' in font) or set(_outputs(font)) == {2, 3}):
        return None
    if any(record.FeatureTag == 'calt' for record in font['GSUB'].table.FeatureList.FeatureRecord):
        raise ValueError('Remove the published rule bundles before installing supplemental artwork')
    tables = _tables(font)
    if not tables:
        raise ValueError('Missing native emoji assembly table')
    info = dict(version=1, bundle=_verify_bundle(),
                style=json.loads((ART / 'manifest.json').read_text()).get('style', 'original'),
                original_glyph_count=len(font.getGlyphOrder()),
                advance_max=font['hhea'].advanceWidthMax,
                bounds={key: getattr(font['head'], key) for key in ('xMin', 'yMin', 'xMax', 'yMax')},
                horizontal={key: getattr(font['hhea'], key) for key in
                            ('minLeftSideBearing', 'minRightSideBearing', 'xMaxExtent')})
    if any(name.startswith('DEImojiPoop') for name in font.getGlyphOrder()):
        raise ValueError('Supplemental artwork must be installed on a clean baseline')
    outputs = _append_bitmaps(font, info) if 'CBDT' in font else _append_colr(font, info)
    base = font.getBestCmap()[0x1F4A9]
    for n, output in zip((2, 3), outputs):
        ligature = ot.Ligature()
        ligature.Component, ligature.CompCount, ligature.LigGlyph = [base] * (n-1), n, output
        tables[0].ligatures.setdefault(base, []).append(ligature)
    tables[0].ligatures[base].sort(key=lambda lig: -len(lig.Component))
    info['glyph_count'] = len(font.getGlyphOrder()) - info['original_glyph_count']
    from zombie_artwork import add_zombie_artwork, variant_mappings
    info['zombies'] = add_zombie_artwork(font)
    from fixed_cluster_artwork import add_fixed_cluster_artwork, OVERLAP
    info['clusters'] = add_fixed_cluster_artwork(font)
    variants = variant_mappings(font)
    # Native Noto has no GPOS. Keep any supplied positioning table untouched.
    # Family-specific kerning closes the measured gaps between visible silhouettes.
    if 'GPOS' not in font:
        from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
        families = []
        for cp in (0x1F9DF, 0x1F33B, 0x1F4A9, *OVERLAP):
            base = font.getBestCmap().get(cp)
            if base is None:
                continue
            names = [base]
            for table in _tables(font):
                names.extend(lig.LigGlyph for lig in table.ligatures.get(base, [])
                             if tuple(lig.Component) in ((base,), (base, base)))
            names.extend(alt for cluster in list(names[1:]) for alt in variants.get(cluster, []))
            if cp == 0x1F386:
                from fixed_cluster_artwork import firework_join_names
                names.extend(firework_join_names(font).values())
            if len(names) == 1:
                continue
            families.append((list(dict.fromkeys(names)),
                             {0x1F9DF: .22, 0x1F33B: .35, 0x1F4A9: .04, **OVERLAP}[cp]))
        lines = ['languagesystem DFLT dflt;']
        for i, (names, fraction) in enumerate(families):
            lines.append(f"@overlap{i} = [{' '.join(names)}];")
            lines.append(f"@clusters{i} = [{' '.join(names[1:])}];")
        lines.append('feature kern {')
        for i, (names, fraction) in enumerate(families):
            amount = round(font['head'].unitsPerEm * fraction)
            lines.append(f'pos @clusters{i} @overlap{i} -{amount};')
            lines.append(f'pos {names[0]} @clusters{i} -{amount};')
        lines.append('} kern;')
        addOpenTypeFeaturesFromString(font, '\n'.join(lines), tables=['GPOS'])
        info['overlap_gpos'] = True
    font._deimoji_artwork = info
    return info


def remove_supplemental_artwork(font, info):
    if not info:
        return
    if info.get('clusters'):
        from fixed_cluster_artwork import remove_fixed_cluster_artwork
        remove_fixed_cluster_artwork(font, info['clusters'])
    if info.get('zombies'):
        from zombie_artwork import remove_zombie_artwork
        remove_zombie_artwork(font, info['zombies'])
    order = font.getGlyphOrder()
    start = info['original_glyph_count']
    if info['version'] != 1 or len(order) != start + info['glyph_count']:
        raise ValueError('Unrecognized supplemental artwork metadata')
    if info.get('overlap_gpos'):
        del font['GPOS']
    added = set(order[start:])
    outputs = set(order[start:start+2])
    if added & set(font.getBestCmap().values()):
        raise ValueError('Supplemental glyphs must be unencoded')
    base = font.getBestCmap()[0x1F4A9]
    found = set()
    for table in _tables(font):
        for first, records in table.ligatures.items():
            for ligature in records:
                if ligature.LigGlyph in outputs:
                    if first != base or tuple(ligature.Component) not in ((base,), (base, base)):
                        raise ValueError('Unexpected supplemental glyph reference')
                    found.add(ligature.LigGlyph)
    if found != outputs:
        raise ValueError('Remove the cluster rules before removing supplemental artwork')
    for table in _tables(font):
        for base, records in list(table.ligatures.items()):
            table.ligatures[base] = [lig for lig in records if lig.LigGlyph not in outputs]
            if not table.ligatures[base]:
                del table.ligatures[base]
    _remove_artwork_tail(font, info, outputs)
    if hasattr(font, '_deimoji_artwork'):
        del font._deimoji_artwork


def _remove_artwork_tail(font, info, outputs):
    order = font.getGlyphOrder()
    start = info['original_glyph_count']
    if len(order) != start + info['glyph_count']:
        raise ValueError('Unrecognized supplemental glyph tail')
    added = set(order[start:])
    if 'bitmap' in info:
        strike = font['CBLC'].strikes[0]
        state = info['bitmap']
        if len(strike.indexSubTables) != state['subtables'] + 1 or set(strike.indexSubTables[-1].names) != outputs:
            raise ValueError('Unrecognized supplemental bitmap strike')
        del strike.indexSubTables[state['subtables']:]
        strike.bitmapSizeTable.endGlyphIndex = state['end']
        strike.bitmapSizeTable.hori.widthMax = state['width']
        for name in added:
            font['CBDT'].strikeData[0].pop(name, None)
    if 'colr' in info:
        table, state = font['COLR'].table, info['colr']
        if any(record.BaseGlyph not in added for record in table.BaseGlyphList.BaseGlyphPaintRecord[state['bases']:]):
            raise ValueError('Unrecognized supplemental COLRv1 records')
        del table.BaseGlyphList.BaseGlyphPaintRecord[state['bases']:]
        table.BaseGlyphList.BaseGlyphCount = state['bases']
        del table.LayerList.Paint[state['layers']:]
        table.LayerList.LayerCount = state['layers']
        if table.ClipList is not None:
            table.ClipList.clips = {name: box for name, box in table.ClipList.clips.items() if name not in added}
            if not state['had_clips']:
                table.ClipList = None
        del font['CPAL'].palettes[0][state['colors']:]
        font['CPAL'].numPaletteEntries = state['colors']
        if font['CPAL'].version == 1 and font['CPAL'].paletteEntryLabels is not None:
            del font['CPAL'].paletteEntryLabels[state['colors']:]
    for name in added:
        font['hmtx'].metrics.pop(name, None)
        if 'vmtx' in font:
            font['vmtx'].metrics.pop(name, None)
        if 'glyf' in font:
            font['glyf'].glyphs.pop(name, None)
    font.setGlyphOrder(order[:start])
    font['maxp'].numGlyphs = start
    font['hhea'].advanceWidthMax = info['advance_max']
    for key, value in info['bounds'].items():
        setattr(font['head'], key, value)
    for key, value in info['horizontal'].items():
        setattr(font['hhea'], key, value)

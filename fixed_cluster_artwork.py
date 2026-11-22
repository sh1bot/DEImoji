"""Install fixed pairs and trios, without diversity-generator variations."""
import hashlib
import json
from pathlib import Path
from fontTools.ttLib.tables import otTables as ot

ART = Path(__file__).resolve().parent/'ligatures/supplemental/clusters'
FAMILIES = {'headstone':0x1FAA6, 'fireworks':0x1F386, 'popper':0x1F389, 'fire':0x1F525, 'moneybags':0x1F4B0}
NAMES = tuple(f'{family}{size}' for family in FAMILIES for size in (2,3))
# Close the margins between silhouettes, leaving singleton-singleton untouched.
OVERLAP = {0x1FAA6:.28, 0x1F386:217/1024, 0x1F389:.02, 0x1F525:.22, 0x1F4B0:.18}


def verify_bundle():
    manifest=json.loads((ART/'manifest.json').read_text())
    if manifest['version'] != 5 or [e['name'] for e in manifest['entries']] != list(NAMES):
        raise ValueError('Unknown fixed-cluster artwork bundle')
    for name,expected in manifest['files'].items():
        if hashlib.sha256((ART/name).read_bytes()).hexdigest()!=expected:
            raise ValueError(f'Fixed-cluster checksum mismatch: {name}')
    return hashlib.sha256(json.dumps(manifest,sort_keys=True).encode()).hexdigest()


def add_fixed_cluster_artwork(font):
    from supplemental_artwork import _tables, _append_bitmaps, _append_colr
    cmap=font.getBestCmap()
    if not all(cp in cmap for cp in FAMILIES.values()):
        return None
    if any(g.startswith('DEImojiFixed') for g in font.getGlyphOrder()):
        raise ValueError('Fixed artwork requires a clean baseline')
    info=dict(version=5,bundle=verify_bundle(),style='noto-fixed-clusters-v5',
              original_glyph_count=len(font.getGlyphOrder()),
              advance_max=font['hhea'].advanceWidthMax,
              bounds={k:getattr(font['head'],k) for k in ('xMin','yMin','xMax','yMax')},
              horizontal={k:getattr(font['hhea'],k) for k in
                          ('minLeftSideBearing','minRightSideBearing','xMaxExtent')})
    names=['DEImojiFixed'+name.title() for name in NAMES]
    if 'CBDT' in font:
        outputs=_append_bitmaps(font,info,art=ART,assets=NAMES,output_names=names,base_cp=0x1F525,allow_split=True)
    else:
        outputs=_append_colr(font,info,art=ART,filename='Clusters-COLRv1.ttf',
                             output_sources=NAMES,output_names=names,base_cp=0x1F525,
                             part_prefix='DEImojiFixedPart')
    table=_tables(font)[0]
    entries=[]
    for (family,cp),pair in zip(FAMILIES.items(),zip(outputs[::2],outputs[1::2])):
        base=cmap[cp]
        for size,output in zip((2,3),pair):
            lig=ot.Ligature();lig.Component=[base]*(size-1);lig.CompCount=size;lig.LigGlyph=output
            table.ligatures.setdefault(base,[]).append(lig)
            entries.append(dict(name=f'{family}{size}',codepoint=cp,size=size,gid=font.getGlyphID(output)))
        table.ligatures[base].sort(key=lambda lig:-len(lig.Component))
    info['entries']=entries
    info['glyph_count']=len(font.getGlyphOrder())-info['original_glyph_count']
    return info


def remove_fixed_cluster_artwork(font,info):
    from supplemental_artwork import _tables, _remove_artwork_tail
    if info['version'] not in (1,2,3,4,5):
        raise ValueError('Unknown fixed-cluster metadata')
    order=font.getGlyphOrder()
    expected={order[e['gid']]:(font.getBestCmap()[e['codepoint']],e['size']) for e in info['entries']}
    expected_count=len(NAMES) if info['version']>=4 else 8
    if len(expected)!=expected_count or set(expected).intersection(font.getBestCmap().values()):
        raise ValueError('Unexpected fixed-cluster outputs')
    found=set()
    for table in _tables(font):
        for base,ligs in list(table.ligatures.items()):
            for lig in ligs:
                if lig.LigGlyph in expected:
                    source,size=expected[lig.LigGlyph]
                    if base!=source or lig.Component!=[base]*(size-1):
                        raise ValueError('Unexpected fixed-cluster reference')
                    found.add(lig.LigGlyph)
            table.ligatures[base]=[lig for lig in ligs if lig.LigGlyph not in expected]
            if not table.ligatures[base]:
                del table.ligatures[base]
    if found!=set(expected):
        raise ValueError('Remove contextual cluster rules before artwork')
    # Legacy v2 manifests need these IDs only when stripping a published font
    # back to its native cache. New bundles contain no background variants.
    outputs=set(expected)|{order[gid] for gid in info.get('joining_gids',{}).values()}
    outputs.update(order[gid] for parts in info.get('bitmap_expansions',{}).values() for gid in parts)
    _remove_artwork_tail(font,info,outputs)


def bitmap_expansions(font,info=None):
    if info is None:info=getattr(font,'_deimoji_artwork',{}).get('clusters',{})
    info=info or {};order=font.getGlyphOrder()
    return {order[int(head)]:[order[gid] for gid in parts]
            for head,parts in info.get('bitmap_expansions',{}).items()}


def bitmap_tile_source(font):
    expansions=bitmap_expansions(font)
    if not expansions:return '',[]
    lines=['lookup paintBitmapTiles {']
    lines += [f"sub {head} by {' '.join(parts)};" for head,parts in expansions.items()]
    lines.append('} paintBitmapTiles;')
    return '\n'.join(lines),['paintBitmapTiles']

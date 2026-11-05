"""Install fixed pairs and trios, without diversity-generator variations."""
import hashlib
import json
from pathlib import Path
from fontTools.ttLib.tables import otTables as ot

ART = Path(__file__).resolve().parent/'ligatures/supplemental/clusters'
FAMILIES = {'headstone':0x1FAA6, 'fireworks':0x1F386, 'popper':0x1F389, 'fire':0x1F525}
NAMES = tuple(f'{family}{size}' for family in FAMILIES for size in (2,3))
# Close the margins between silhouettes, leaving singleton-singleton untouched.
OVERLAP = {0x1FAA6:.28, 0x1F386:.025, 0x1F389:.08, 0x1F525:.22}


def verify_bundle():
    manifest=json.loads((ART/'manifest.json').read_text())
    if manifest['version'] != 1 or [e['name'] for e in manifest['entries']] != list(NAMES):
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
    info=dict(version=1,bundle=verify_bundle(),style='noto-fixed-clusters-v1',
              original_glyph_count=len(font.getGlyphOrder()),
              advance_max=font['hhea'].advanceWidthMax,
              bounds={k:getattr(font['head'],k) for k in ('xMin','yMin','xMax','yMax')},
              horizontal={k:getattr(font['hhea'],k) for k in
                          ('minLeftSideBearing','minRightSideBearing','xMaxExtent')})
    names=['DEImojiFixed'+name.title() for name in NAMES]
    if 'CBDT' in font:
        outputs=_append_bitmaps(font,info,art=ART,assets=NAMES,output_names=names,base_cp=0x1F525)
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
    if info['version']!=1:
        raise ValueError('Unknown fixed-cluster metadata')
    order=font.getGlyphOrder()
    expected={order[e['gid']]:(font.getBestCmap()[e['codepoint']],e['size']) for e in info['entries']}
    if len(expected)!=8 or set(expected).intersection(font.getBestCmap().values()):
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
    _remove_artwork_tail(font,info,set(expected))

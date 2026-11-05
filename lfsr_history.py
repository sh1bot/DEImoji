"""Shared input-buffer glyph partitions for current and future LFSRs.

Classify shaped glyphs, not COLR outline components that never enter the buffer.
Private output states override the default glyph-ID hash in their own base.
Reading a glyph in a history class never substitutes or exposes that glyph.
"""
from fontTools.ttLib.tables.otBase import BaseTable


def buffer_glyphs(font):
    names=set(font.getBestCmap().values())
    names.add(font.getGlyphOrder()[0])
    def visit(table):
        if isinstance(table,list):
            for item in table:visit(item)
        elif isinstance(table,BaseTable):
            for attr in ('mapping','alternates'):
                for output in getattr(table,attr,{}).values():
                    names.update([output] if isinstance(output,str) else output)
            for ligatures in getattr(table,'ligatures',{}).values():
                names.update(lig.LigGlyph for lig in ligatures)
            for value in vars(table).values():
                if isinstance(value,(list,BaseTable)):visit(value)
    if 'GSUB' in font:visit(font['GSUB'].table.LookupList.Lookup)
    return [g for g in font.getGlyphOrder() if g in names]


def partition(font,base,overrides=None):
    if base<2:raise ValueError('LFSR base must be at least two')
    overrides=overrides or {}
    names=set(buffer_glyphs(font))|set(overrides)
    groups=[[] for _ in range(base)]
    for gid,glyph in enumerate(font.getGlyphOrder()):
        if glyph in names:
            value=overrides.get(glyph,gid%base)
            if not 0<=value<base:raise ValueError('Invalid private LFSR state')
            groups[value].append(glyph)
    return groups


def marker_order(first_gid,groups):
    """Pack each clock's states into one base-sized run, with gid % base = state."""
    result=[]
    for markers in groups:
        base=len(markers)
        origin=first_gid+len(result)
        result.extend(markers[(origin+i)%base] for i in range(base))
    return result

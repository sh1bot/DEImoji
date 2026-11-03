"""Optional contextual pair/triple ligatures for plain zombies and sunflowers.

The previous three output clusters are a degree-three LFSR register. Pair=0,
triple=1, with next = oldest XOR newest and seed 111 (period seven).
"""
from copy import deepcopy

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.otBase import BaseTable


CLUSTER_CODEPOINTS = (0x1F9DF, 0x1F33B)
CLUSTER_SEQUENCES = frozenset(
    (cp,) * count for cp in CLUSTER_CODEPOINTS for count in (2, 3)
)
CLUSTER_NAMES = tuple(
    'emoji_u' + '_'.join(f'{cp:x}' for cp in sequence)
    for sequence in sorted(CLUSTER_SEQUENCES)
)


def feature_source(families):
    """families contains (base, pair, triple) glyph names, not Unicode strings."""
    lines = ['languagesystem DFLT dflt;']
    for i, (base, pair, triple) in enumerate(families):
        lines += [
            f'@history{i} = [{pair} {triple}];',
            f'lookup pair{i} {{ sub {base} {base} by {pair}; }} pair{i};',
            f'lookup triple{i} {{ sub {base} {base} {base} by {triple}; }} triple{i};',
        ]
    lines.append('lookup cluster_choices {')
    for i, (base, pair, triple) in enumerate(families):
        # Five remaining items permit either choice without a leftover single.
        # The four-item tail forces 2+2; three and two finish exactly.
        tail = ' '.join([base] * 4)
        for oldest in (0, 1):
            for newest in (0, 1):
                a, c = (pair, triple)[oldest], (pair, triple)[newest]
                choice = ('pair', 'triple')[oldest ^ newest]
                lines.append(
                    f"sub {a} @history{i} {c} {base}' lookup {choice}{i} {tail};"
                )
        lines += [
            f"sub {base}' lookup triple{i} {tail};",  # seed 1
            f"sub {base}' lookup pair{i} {base} {base} {base};",
            f"sub {base}' lookup triple{i} {base} {base};",
            f"sub {base}' lookup pair{i} {base};",
        ]
    lines += ['} cluster_choices;',
              'feature calt { lookup cluster_choices; } calt;']
    return '\n'.join(lines)


def _ligature_tables(lookup):
    for subtable in lookup.SubTable:
        if lookup.LookupType == 4:
            yield subtable
        elif lookup.LookupType == 7 and subtable.ExtensionLookupType == 4:
            yield subtable.ExtSubTable


def _offset_references(table, offset):
    if isinstance(table, list):
        for value in table:
            _offset_references(value, offset)
    elif isinstance(table, BaseTable):
        for key, value in vars(table).items():
            if key == 'LookupListIndex':
                setattr(table, key, value + offset)
            else:
                _offset_references(value, offset)


def add_cluster_ligatures(font):
    """Keep native GSUB; move just our four repeated sequences to default calt.

    Discover output names from native ligatures, so both add_glyphs and
    nanoemoji naming conventions work. Missing families are skipped, allowing
    subsets and upstream assets without the optional cluster artwork.
    Call after artwork embedding (the bitmap builder still needs the native
    ligatures to resolve sequence filenames). Repeated installation is a no-op.
    """
    if 'GSUB' not in font:
        return
    gsub = font['GSUB'].table
    cmap = font.getBestCmap()
    families, removals = [], []
    # Only consider top-level native features. Our nested pair/triple lookups
    # belong to calt and must not be harvested on a second invocation.
    native_indices = sorted({
        index for record in gsub.FeatureList.FeatureRecord
        if record.FeatureTag != 'calt'
        for index in record.Feature.LookupListIndex
    })
    for cp in CLUSTER_CODEPOINTS:
        base = cmap.get(cp)
        outputs, found = {}, []
        if base is None:
            continue
        for index in native_indices:
            lookup = gsub.LookupList.Lookup[index]
            for table in _ligature_tables(lookup):
                for ligature in table.ligatures.get(base, []):
                    n = len(ligature.Component) + 1
                    if n in (2, 3) and tuple(ligature.Component) == (base,) * (n - 1):
                        outputs[n] = ligature.LigGlyph
                        found.append((table, base, ligature))
        if outputs.keys() == {2, 3}:
            families.append((base, outputs[2], outputs[3]))
            removals.extend(found)
    if not families:
        return
    if getattr(gsub, 'FeatureVariations', None):
        raise ValueError('Cluster feature merging does not support FeatureVariations')

    temp = TTFont()
    temp.setGlyphOrder(font.getGlyphOrder())
    addOpenTypeFeaturesFromString(temp, feature_source(families), tables=['GSUB'])
    extra = temp['GSUB'].table
    offset = len(gsub.LookupList.Lookup)
    new_lookups = deepcopy(extra.LookupList.Lookup)
    for lookup in new_lookups:
        _offset_references(lookup, offset)
    # Do not leave greedy ccmp ligatures to consume the input before calt.
    for table, base, ligature in removals:
        table.ligatures[base].remove(ligature)
        if not table.ligatures[base]:
            del table.ligatures[base]
    gsub.LookupList.Lookup.extend(new_lookups)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    indices = [i + offset for i in extra.FeatureList.FeatureRecord[0].Feature.LookupListIndex]

    records = gsub.FeatureList.FeatureRecord
    # Existing calt records can be language-specific; append to each one.
    calts = [r for r in records if r.FeatureTag == 'calt']
    if not calts:
        record = ot.FeatureRecord()
        record.FeatureTag = 'calt'
        record.Feature = ot.Feature()
        record.Feature.FeatureParams = None
        record.Feature.LookupListIndex = []
        records.append(record)
        calts = [record]
    for record in calts:
        record.Feature.LookupListIndex.extend(indices)
        record.Feature.LookupCount = len(record.Feature.LookupListIndex)

    old_records = list(records)
    records.sort(key=lambda record: record.FeatureTag)
    remap = {old: next(i for i, r in enumerate(records) if r is record)
             for old, record in enumerate(old_records)}
    default_calt = next(i for i, r in enumerate(records) if r is calts[0])
    for script_record in gsub.ScriptList.ScriptRecord:
        script = script_record.Script
        languages = [r.LangSys for r in script.LangSysRecord]
        if script.DefaultLangSys is not None:
            languages.append(script.DefaultLangSys)
        for lang in languages:
            lang.FeatureIndex = [remap[i] for i in lang.FeatureIndex]
            if lang.ReqFeatureIndex != 0xFFFF:
                lang.ReqFeatureIndex = remap[lang.ReqFeatureIndex]
            if not any(records[i].FeatureTag == 'calt' for i in lang.FeatureIndex):
                lang.FeatureIndex.append(default_calt)
            lang.FeatureIndex.sort()
            lang.FeatureCount = len(lang.FeatureIndex)
    gsub.FeatureList.FeatureCount = len(records)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('font', help='Built emoji TTF to update in place')
    args = parser.parse_args()
    font = TTFont(args.font)
    add_cluster_ligatures(font)
    font.save(args.font)

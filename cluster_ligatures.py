"""Optional contextual pair/triple ligatures for plain zombies, sunflowers and poop.

The previous four output clusters are a degree-four LFSR register. Pair=0,
triple=1, with next = oldest XOR next-oldest and seed 1111 (period fifteen).
"""
from copy import deepcopy

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables import otTables as ot
from fontTools.ttLib.tables.otBase import BaseTable


NATIVE_CLUSTER_CODEPOINTS = (0x1F9DF, 0x1F33B)
CLUSTER_CODEPOINTS = (*NATIVE_CLUSTER_CODEPOINTS, 0x1F4A9)
CLUSTER_SEQUENCES = frozenset(
    (cp,) * count for cp in CLUSTER_CODEPOINTS for count in (2, 3)
)
CLUSTER_NAMES = tuple(
    'emoji_u' + '_'.join(f'{cp:x}' for cp in sequence)
    for sequence in sorted(CLUSTER_SEQUENCES)
)
NATIVE_CLUSTER_NAMES = tuple(name for name in CLUSTER_NAMES if '1f4a9' not in name)


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
            for next_oldest in (0, 1):
                a, b = (pair, triple)[oldest], (pair, triple)[next_oldest]
                choice = ('pair', 'triple')[oldest ^ next_oldest]
                lines.append(
                    f"sub {a} {b} @history{i} @history{i} {base}' lookup {choice}{i} {tail};"
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


def _add_cluster_ligatures(font):
    """Keep native GSUB; move our repeated sequences to default calt.

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


def add_cluster_ligatures(font):
    """Install the contextual clusters and independent modifier generators."""
    from supplemental_artwork import add_supplemental_artwork
    add_supplemental_artwork(font)
    _add_cluster_ligatures(font)
    from modifier_ligatures import add_modifier_ligatures
    return add_modifier_ligatures(font)


def remove_cluster_ligatures(font):
    """Recover the native GSUB for a build cache from our known full-font format.

    This deliberately refuses unknown/pre-existing calt features rather than
    removing arbitrary font behavior. Both the original two-family bundle and
    the three-family supplemental-artwork bundle can recover a native cache.
    """
    gsub = font['GSUB'].table
    records = gsub.FeatureList.FeatureRecord
    calts = [(i, record) for i, record in enumerate(records) if record.FeatureTag == 'calt']
    lookups = gsub.LookupList.Lookup
    references = set()
    def collect(value):
        if isinstance(value, list):
            for item in value:
                collect(item)
        elif isinstance(value, BaseTable):
            for key, item in vars(value).items():
                if key == 'LookupListIndex':
                    references.add(item)
                else:
                    collect(item)
    if lookups:
        collect(lookups[-1].SubTable)
    start = min(references) if references else -1
    root_types = [s.ExtensionLookupType if lookups[-1].LookupType == 7 else lookups[-1].LookupType
                  for s in lookups[-1].SubTable] if lookups else []
    if (len(calts) != 1 or start < 1 or not root_types or set(root_types) != {6}
            or references != set(range(start, len(lookups) - 1))
            or len(references) not in (4, 6)
            or calts[0][1].Feature.LookupListIndex != [len(lookups) - 1]):
        raise ValueError('Not a recognized DEImoji cluster feature bundle')
    if getattr(gsub, 'FeatureVariations', None):
        raise ValueError('Cannot recover a variable-feature cache')
    for record in records:
        if record is not calts[0][1] and any(i >= start for i in record.Feature.LookupListIndex):
            raise ValueError('Cluster lookup bundle is shared with another feature')
    restore = []
    known_bases = {font.getBestCmap()[cp] for cp in CLUSTER_CODEPOINTS if cp in font.getBestCmap()}
    seen_bases = set()
    for family in range(len(references) // 2):
        base = None
        for choice, count in enumerate((2, 3)):
            lookup = lookups[start + family * 2 + choice]
            tables = list(_ligature_tables(lookup))
            if len(tables) != 1 or len(tables[0].ligatures) != 1:
                raise ValueError('Unexpected cluster ligature lookup')
            candidate = next(iter(tables[0].ligatures))
            if candidate not in known_bases or (base is not None and base != candidate):
                raise ValueError('Unexpected cluster family')
            base = candidate
            ligatures = tables[0].ligatures[base]
            if len(ligatures) != 1 or tuple(ligatures[0].Component) != (base,) * (count - 1):
                raise ValueError('Unexpected cluster ligature components')
            restore.append((base, deepcopy(ligatures[0])))
        if base in seen_bases:
            raise ValueError('Duplicate cluster family')
        seen_bases.add(base)
    ccmps = [r for r in records if r.FeatureTag == 'ccmp']
    if len(ccmps) != 1:
        raise ValueError('Expected a single native ccmp feature')
    native_tables = [t for index in ccmps[0].Feature.LookupListIndex
                     for t in _ligature_tables(lookups[index])]
    if not native_tables:
        raise ValueError('No native emoji ligature table')
    for base, ligature in restore:
        native_tables[0].ligatures.setdefault(base, []).append(ligature)
        native_tables[0].ligatures[base].sort(key=lambda item: -len(item.Component))
    removed = calts[0][0]
    for script_record in gsub.ScriptList.ScriptRecord:
        script = script_record.Script
        languages = [r.LangSys for r in script.LangSysRecord]
        if script.DefaultLangSys is not None:
            languages.append(script.DefaultLangSys)
        for lang in languages:
            if lang.ReqFeatureIndex == removed:
                raise ValueError('Refusing to remove a required feature')
            lang.FeatureIndex = [i - (i > removed) for i in lang.FeatureIndex if i != removed]
            lang.FeatureCount = len(lang.FeatureIndex)
            if lang.ReqFeatureIndex != 0xFFFF:
                lang.ReqFeatureIndex -= lang.ReqFeatureIndex > removed
    records.pop(removed)
    gsub.FeatureList.FeatureCount = len(records)
    del lookups[start:]
    gsub.LookupList.LookupCount = len(lookups)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('font', help='Built emoji TTF to update in place')
    parser.add_argument('--native-cache', help='Save a native font before the custom GSUB patch')
    args = parser.parse_args()
    font = TTFont(args.font)
    if args.native_cache:
        from pathlib import Path
        target = Path(args.native_cache)
        target.parent.mkdir(parents=True, exist_ok=True)
        font.save(target)
    add_cluster_ligatures(font)
    font.save(args.font)

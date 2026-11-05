"""Deterministic, independent prime-base LFSRs for unmodified emoji.

Internal unencoded markers keep feedback separate from explicitly typed modifiers.
The native ccmp assembles explicit user sequences before private states exist.
Both generators finish before direct artwork folding and a separate cleanup sweep.
No generated Unicode tone, ZWJ, or gender-sign glyphs are emitted.
"""
from copy import deepcopy
from itertools import product
import unicodedata

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.otlLib.maxContextCalc import maxCtxFont
from fontTools.ttLib import TTFont

TONE_COEFFICIENTS = (0, 1, 1, 2)
GENDER_COEFFICIENTS = (0, 0, 1, 1)
# Example starting registers for cycle verification; actual startup is
# collected by the right-to-left suffix hashes.
TONE_SEED = (2, 2, 3, 1)
GENDER_SEED = (0, 2, 2, 1)
TONES = tuple('DEImojiTone' + str(i) for i in range(5))
GENDERS = tuple('DEImojiGender' + str(i) for i in range(3))
MARKERS = TONES + GENDERS


def feedback(base, coefficients, state):
    """Splice the missing zero register into one chosen maximal-cycle edge."""
    if tuple(state) == (0,) * len(coefficients):
        return coefficients[-1] % base
    if tuple(state) == (0,) * (len(coefficients) - 1) + (1,):
        return 0
    return sum(a * b for a, b in zip(coefficients, state)) % base


def stream(base, coefficients, seed, count):
    """Coefficients and seed are newest first; return the next count outputs."""
    state = list(seed)
    result = []
    for _ in range(count):
        value = feedback(base, coefficients, state)
        result.append(value)
        state = [value] + state[:-1]
    return result


def discover(font):
    from cluster_ligatures import _ligature_tables
    cmap = font.getBestCmap()
    if not all(cp in cmap for cp in (*range(0x1F3FB, 0x1F400), 0x200D, 0x2640, 0x2642)):
        return {}, {}, {}
    tones = [cmap[cp] for cp in range(0x1F3FB, 0x1F400)]
    tails = [(cmap[0x200D], cmap[cp]) for cp in (0x2640, 0x2642)]
    mappings = {}
    gsub = font['GSUB'].table
    indices = {i for r in gsub.FeatureList.FeatureRecord if r.FeatureTag != 'calt'
               for i in r.Feature.LookupListIndex}
    for index in sorted(indices):
        for table in _ligature_tables(gsub.LookupList.Lookup[index]):
            for first, ligatures in table.ligatures.items():
                for ligature in ligatures:
                    mappings[(first, *ligature.Component)] = ligature.LigGlyph
    encoded = set(cmap.values())
    tone_bases = {b: [mappings[b, t] for t in tones]
                  for b in encoded if all((b, t) in mappings for t in tones)}
    gender_bases = {b: [[mappings[b, t, *tail] for tail in tails] for t in tones]
                    for b in tone_bases
                    if all((b, t, *tail) in mappings for t in tones for tail in tails)}
    assembly = {seq: target for seq, target in mappings.items()
                if seq[0] in tone_bases and
                (len(seq) == 2 and seq[1] in tones or
                 seq[0] in gender_bases and len(seq) == 4 and seq[1] in tones
                 and seq[2:] in tails)}
    # Adult and older person use separate woman/man codepoints, rather than
    # native ZWJ gender ligatures. Fold generated states directly into those
    # existing toned glyphs; accept explicit font-level suffix aliases too.
    for codepoints in ((0x1F9D1, 0x1F469, 0x1F468), (0x1F9D3, 0x1F475, 0x1F474)):
        people = [cmap.get(cp) for cp in codepoints]
        if not all(base in tone_bases for base in people):
            continue
        person, woman, man = people
        gender_bases[person] = [list(pair) for pair in
                                zip(tone_bases[woman], tone_bases[man])]
        for target_base, tail in zip((woman, man), tails):
            assembly[(person, *tail)] = target_base
            for tone, neutral, target in zip(tones, tone_bases[person], tone_bases[target_base]):
                assembly[(person, tone, *tail)] = target
                assembly[(neutral, *tail)] = target
    # Explicit non-Unicode artwork families share the same five-state clock.
    from zombie_artwork import variant_mappings
    tone_bases.update(variant_mappings(font))
    return tone_bases, gender_bases, assembly


def source_glyphs(font):
    """All mapped glyphs and GSUB outputs that can carry input-buffer noise.

    COLRv1 outline components are not buffer glyphs. Excluding those avoids
    thousands of pointless expansion rules without excluding shaped text.
    """
    from lfsr_history import buffer_glyphs
    names = set(buffer_glyphs(font))
    # Touching .notdef would mark an unsupported variation selector as
    # substituted, preventing HarfBuzz from hiding that default-ignorable.
    protected = {font.getGlyphOrder()[0]}
    # Preserve shaper treatment of default-ignorables: GSUB substitution can
    # otherwise turn their normally hidden glyphs into visible output.
    invisible_ranges = ((0x115F, 0x1160), (0x17B4, 0x17B5), (0x180B, 0x180F),
                        (0xFE00, 0xFE0F), (0xFFF0, 0xFFF8),
                        (0x1BCA0, 0x1BCAF), (0x1D173, 0x1D17A), (0xE0000, 0xE0FFF))
    for cp, glyph in font.getBestCmap().items():
        if (unicodedata.category(chr(cp)) == 'Cf' or cp in (0x034F, 0x3164, 0xFFA0)
                or any(lo <= cp <= hi for lo, hi in invisible_ranges)):
            protected.add(glyph)
    return [name for name in font.getGlyphOrder()
            if name in names and name not in MARKERS and name not in protected]


def _reverse_hash(name, markers, buckets):
    """Collect suffix noise in base five before either forward generator runs."""
    base = len(markers)
    lines = [f'lookup {name} useExtension {{']
    for glyph_class, bucket in buckets:
        for future in range(base):
            value = (2 * future + bucket + 1) % base
            context = f"{glyph_class} @tone' @gender @source {markers[future]}"
            lines.append(f'rsub {context} by {markers[value]};')
    # The negated terminal bucket avoids the repeated-source fixed point.
    for glyph_class, bucket in buckets:
        lines.append(f"rsub {glyph_class} @tone' by {markers[(-bucket) % base]};")
    lines.append(f'}} {name};')
    return lines


def _gender_seed_from_tone(buckets):
    """Reuse the completed base-five hash without a second recursive sweep.

    Rebase relative to the repeated-source fixed point, then mix the bucket.
    Every four-cycle of a repeated source visits all three gender states.
    Across 25 (bucket,hash) combinations: 9 neutral, 8 female and 8 male.
    """
    lines = ['lookup seedGenderFromTone useExtension {']
    for glyph_class, bucket in buckets:
        for gender in range(3):
            markers = [marker for tone, marker in enumerate(TONES)
                       if (((tone + bucket + 1) % 5) + bucket + 2) % 3 == gender]
            # Group hash values with the same result: 15 rules for 25 pairs.
            hashes = '[' + ' '.join(markers) + ']'
            lines.append(f"rsub {glyph_class} {hashes} @gender' by {GENDERS[gender]};")
    lines.append('} seedGenderFromTone;')
    return lines


def _feedback(name, markers, coefficients):
    base, degree = len(markers), len(coefficients)
    marker_class = '@tone' if base == 5 else '@gender'
    current = ['@tonebase'] if base == 5 else ['@tonebase', '@tone']
    suffix = ['@gender'] if base == 5 else []
    lines = []
    for i, marker in enumerate(markers):
        lines.append(f'lookup {name}{i} {{ sub {marker_class} by {marker}; }} {name}{i};')
    lines.append(f'lookup {name}Feedback useExtension {{')

    def rule(register, result):
        context = []
        for value in register:
            state = marker_class if value is None else markers[value]
            context.extend(['@source', state, '@gender'] if base == 5 else
                           ['@source', '@tone', state])
        lines.append('sub ' + ' '.join(context + current) +
                     f" {marker_class}' lookup {name}{result} " + ' '.join(suffix) + ';')

    # Exact zero-state splice first; chronological register order.
    rule((1,) + (0,) * (degree - 1), 0)
    rule((0,) * degree, coefficients[-1] % base)
    taps = [i for i, coefficient in enumerate(coefficients) if coefficient]
    for values in product(range(base), repeat=len(taps)):
        history = {degree - 1 - i: v for i, v in zip(taps, values)}
        result = sum(coefficients[i] * v for i, v in zip(taps, values)) % base
        rule([history.get(n) for n in range(degree)], result)
    # No short-history fallback: retain this position's reverse-sweep hash.
    lines.append(f'}} {name}Feedback;')
    return lines


def feature_source(font, tone_bases, gender_bases, assembly):
    cmap = font.getBestCmap()
    actual_tones = [cmap[cp] for cp in range(0x1F3FB, 0x1F400)]
    sources = source_glyphs(font)
    lines = ['languagesystem DFLT dflt;',
             '@tonebase = [' + ' '.join(sorted(tone_bases)) + '];',
             '@tone = [' + ' '.join(TONES) + '];',
             '@gender = [' + ' '.join(GENDERS) + '];',
             '@source = [' + ' '.join(sources) + '];',
             '@explicit = [' + ' '.join(actual_tones + [cmap[0x200D]]) + '];']
    source_set = set(sources)
    buckets = []
    for bucket in range(5):
        members = [name for gid, name in enumerate(font.getGlyphOrder())
                   if name in source_set and gid % 5 == bucket]
        if members:
            glyph_class = f'@seed{bucket}'
            lines.append(glyph_class + ' = [' + ' '.join(members) + '];')
            buckets.append((glyph_class, bucket))
    # Noise-only glyphs carry hash state too; only eligible bases will fold.
    lines.append('lookup seedExpand useExtension {')
    lines += [f'sub {name} by {name} {TONES[0]} {GENDERS[0]};' for name in sources]
    lines.append('} seedExpand;')
    lines += _reverse_hash('seedToneRTL', TONES, buckets)
    lines += _gender_seed_from_tone(buckets)
    lines += _feedback('tone', TONES, TONE_COEFFICIENTS)
    lines += _feedback('gender', GENDERS, GENDER_COEFFICIENTS)
    lines.append('lookup foldStatePairs useExtension {')
    for b, variants in sorted(tone_bases.items()):
        for t, neutral in enumerate(variants):
            targets = [neutral] + (gender_bases[b][t] if b in gender_bases else [neutral, neutral])
            for g, target in enumerate(targets):
                lines.append(f'sub {b} {TONES[t]} {GENDERS[g]} by {target};')
    lines += ['} foldStatePairs;', 'lookup foldStates {',
              "ignore sub @tonebase' @tone @gender @explicit;",
              "sub @tonebase' lookup foldStatePairs;", '} foldStates;',
              'lookup sweepStates {', 'sub @tone by NULL;',
              'sub @gender by NULL;', '} sweepStates;']
    lines.append('lookup modifierAssembly useExtension {')
    for sequence, target in sorted(assembly.items(), key=lambda item: (-len(item[0]), item[0])):
        lines.append('sub ' + ' '.join(sequence) + f' by {target};')
    lines += ['} modifierAssembly;', 'feature calt {',
              'lookup seedExpand;', 'lookup seedToneRTL;', 'lookup seedGenderFromTone;',
              'lookup toneFeedback;', 'lookup genderFeedback;',
              'lookup foldStates;', 'lookup sweepStates;',
              'lookup modifierAssembly;', '} calt;']
    return '\n'.join(lines)


def _languages(gsub):
    for record in gsub.ScriptList.ScriptRecord:
        script = record.Script
        if script.DefaultLangSys is not None:
            yield script.DefaultLangSys
        for language in script.LangSysRecord:
            yield language.LangSys


def add_modifier_ligatures(font):
    from cluster_ligatures import _offset_references, BINARY_DEGREE, BINARY_PERIOD
    if 'GSUB' not in font:
        return None
    if any(name in font.getGlyphOrder() for name in MARKERS):
        if not hasattr(font, '_deimoji_modifiers'):
            raise ValueError('Install modifier rules only on a native baseline; remove the published bundle first')
        return font._deimoji_modifiers
    tone_bases, gender_bases, assembly = discover(font)
    if not tone_bases:
        return None
    gsub = font['GSUB'].table
    if getattr(gsub, 'FeatureVariations', None):
        raise ValueError('Modifier feature merging does not support FeatureVariations')
    original_order = font.getGlyphOrder()
    from lfsr_history import marker_order
    font.setGlyphOrder(original_order + marker_order(len(original_order),(GENDERS,TONES)))
    for name in MARKERS:
        if 'glyf' in font:
            font['glyf'].glyphs[name] = TTGlyphPen(None).glyph()
        for tag in ('hmtx', 'vmtx'):
            if tag in font:
                font[tag].metrics[name] = (0, 0)
    font['maxp'].numGlyphs = len(font.getGlyphOrder())
    temp = TTFont()
    temp.setGlyphOrder(font.getGlyphOrder())
    addOpenTypeFeaturesFromString(temp, feature_source(font, tone_bases, gender_bases, assembly), tables=['GSUB'])
    extra = temp['GSUB'].table
    offset = len(gsub.LookupList.Lookup)
    new_lookups = deepcopy(extra.LookupList.Lookup)
    for lookup in new_lookups:
        _offset_references(lookup, offset)
    roots = [offset + i for i in extra.FeatureList.FeatureRecord[0].Feature.LookupListIndex]
    calts = [r for r in gsub.FeatureList.FeatureRecord if r.FeatureTag == 'calt']
    created_calt = not calts
    if created_calt:
        record = deepcopy(extra.FeatureList.FeatureRecord[0])
        record.Feature.LookupListIndex = []
        record.Feature.LookupCount = 0
        records = gsub.FeatureList.FeatureRecord
        old = list(records)
        records.append(record)
        records.sort(key=lambda r: r.FeatureTag)
        remap = {i: records.index(r) for i, r in enumerate(old)}
        index = records.index(record)
        for language in _languages(gsub):
            language.FeatureIndex = sorted([remap[i] for i in language.FeatureIndex] + [index])
            language.FeatureCount = len(language.FeatureIndex)
            if language.ReqFeatureIndex != 0xFFFF:
                language.ReqFeatureIndex = remap[language.ReqFeatureIndex]
        gsub.FeatureList.FeatureCount = len(records)
        calts = [record]
    for record in calts:
        record.Feature.LookupListIndex.extend(roots)
        record.Feature.LookupCount = len(record.Feature.LookupListIndex)
    gsub.LookupList.Lookup.extend(new_lookups)
    gsub.LookupList.LookupCount = len(gsub.LookupList.Lookup)
    from zombie_artwork import variant_mappings
    custom_count = len(variant_mappings(font))
    info = dict(version=5, binary_degree=BINARY_DEGREE,binary_period=BINARY_PERIOD, history='all-source-private-states',
                marker_layout='residue-aligned',
                tone_marker_gids=[font.getGlyphID(g) for g in TONES],
                gender_marker_gids=[font.getGlyphID(g) for g in GENDERS],
                feedback_context='all-expanded-source-glyphs', gender_seeding="base5-hash-and-source-bucket", seeding="reverse-suffix-all-source-glyphs",
                seed_source_glyphs=len(source_glyphs(font)), created_calt=created_calt, original_lookup_count=offset, lookup_count=len(new_lookups),
                original_glyph_count=len(original_order), marker_count=len(MARKERS),
                calt_roots=roots, state_periods=[625, 81], combined_period=50625,
                tone_bases=len(tone_bases)-custom_count,
                custom_bases=custom_count,
                diversity_bases=len(tone_bases), gender_bases=len(gender_bases))
    if 'OS/2' in font:
        info['original_max_context'] = font['OS/2'].usMaxContext
        font['OS/2'].usMaxContext = maxCtxFont(font)
    font._deimoji_modifiers = info
    return info


def remove_modifier_ligatures(font, info):
    """Remove only the appended bundle identified by the published manifest."""
    if not info:
        return
    gsub = font['GSUB'].table
    start, glyph_start = info['original_lookup_count'], info['original_glyph_count']
    order = font.getGlyphOrder()
    if (info['version'] not in (1, 2, 3, 4, 5) or len(gsub.LookupList.Lookup) != start + info['lookup_count']
            or len(order) != glyph_start + info['marker_count'] or info['marker_count'] != 8):
        raise ValueError('Unrecognized modifier bundle metadata')
    marker_names = set(order[glyph_start:])
    if marker_names & set(font.getBestCmap().values()):
        raise ValueError('Modifier marker glyphs must be unencoded')
    for tag in ('hmtx', 'vmtx'):
        if tag in font and any(font[tag].metrics[name] != (0, 0) for name in marker_names):
            raise ValueError('Unexpected modifier marker metrics')
    roots = info['calt_roots']
    if not roots or any(i < start or i >= start + info['lookup_count'] for i in roots):
        raise ValueError('Invalid modifier root metadata')
    for record in gsub.FeatureList.FeatureRecord:
        indices = record.Feature.LookupListIndex
        if record.FeatureTag == 'calt' and indices[-len(roots):] == roots:
            del indices[-len(roots):]
            record.Feature.LookupCount = len(indices)
        elif any(i >= start for i in indices):
            raise ValueError('Modifier lookups are shared or metadata does not match')
    if info.get('created_calt'):
        records = gsub.FeatureList.FeatureRecord
        index = next(i for i, r in enumerate(records) if r.FeatureTag == 'calt')
        if records[index].Feature.LookupListIndex:
            raise ValueError('Created modifier feature has unexpected lookups')
        records.pop(index)
        gsub.FeatureList.FeatureCount = len(records)
        for language in _languages(gsub):
            language.FeatureIndex = [i - (i > index) for i in language.FeatureIndex if i != index]
            language.FeatureCount = len(language.FeatureIndex)
            if language.ReqFeatureIndex != 0xFFFF:
                language.ReqFeatureIndex -= language.ReqFeatureIndex > index
    del gsub.LookupList.Lookup[start:]
    gsub.LookupList.LookupCount = start
    for name in order[glyph_start:]:
        if 'glyf' in font:
            del font['glyf'].glyphs[name]
        for tag in ('hmtx', 'vmtx'):
            if tag in font:
                del font[tag].metrics[name]
    font.setGlyphOrder(order[:glyph_start])
    font['maxp'].numGlyphs = glyph_start
    if 'original_max_context' in info:
        font['OS/2'].usMaxContext = info['original_max_context']
    if hasattr(font, '_deimoji_modifiers'):
        del font._deimoji_modifiers

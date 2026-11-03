"""Deterministic, independent prime-base LFSRs for unmodified emoji.

Internal unencoded markers keep feedback separate from explicitly typed modifiers.
The native ccmp has already assembled user sequences; a restricted final assembly
lookup reuses native artwork after our markers have been resolved.
"""
from copy import deepcopy
from itertools import product

from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.otlLib.maxContextCalc import maxCtxFont
from fontTools.ttLib import TTFont

TONE_COEFFICIENTS = (0, 0, 0, 0, 0, 1, 1, 2)
GENDER_COEFFICIENTS = (0, 0, 0, 0, 1, 0, 2)
# Virtual initial registers chosen to reproduce the fallback cycles below.
# They keep the reference stream continuous when full feedback takes over.
TONE_SEED = (4, 2, 2, 4, 4, 4, 0, 3)
GENDER_SEED = (1, 1, 0, 1, 1, 0, 1)
TONE_STARTUP_STEP = 3
GENDER_STARTUP_STEP = 1
TONES = tuple('DEImojiTone' + str(i) for i in range(5))
GENDERS = tuple('DEImojiGender' + str(i) for i in range(3))
MARKERS = TONES + GENDERS


def stream(base, coefficients, seed, count):
    """Coefficients and seed are newest first; return the next count outputs."""
    state = list(seed)
    result = []
    for _ in range(count):
        value = sum(a * b for a, b in zip(coefficients, state)) % base
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
    # Person uses separate woman/man bases instead of native ZWJ gender forms.
    # Accept our generated suffixes and explicit suffixes already partly
    # assembled by ccmp, reusing the existing artwork in both cases.
    people = [cmap.get(cp) for cp in (0x1F9D1, 0x1F469, 0x1F468)]
    if all(base in tone_bases for base in people):
        person, woman, man = people
        gender_bases[person] = [list(pair) for pair in
                                zip(tone_bases[woman], tone_bases[man])]
        for target_base, tail in zip((woman, man), tails):
            assembly[(person, *tail)] = target_base
            for tone, neutral, target in zip(tones, tone_bases[person], tone_bases[target_base]):
                assembly[(person, tone, *tail)] = target
                assembly[(neutral, *tail)] = target
    return tone_bases, gender_bases, assembly


def _feedback(name, markers, coefficients, seed, stride, startup_step, lookahead=()):
    base, degree = len(markers), len(coefficients)
    marker_class = '@tone' if base == 5 else '@gender'
    unit = ['@tonebase', '@tone'] if stride == 2 else ['@genderbase', '@tone', '@gender']
    current = unit[:-1]
    lines = []
    for i, marker in enumerate(markers):
        lines.append(f'lookup {name}{i} {{ sub {markers[0]} by {marker}; }} {name}{i};')
    lines.append(f'lookup {name}Feedback useExtension {{')
    taps = [i for i, coefficient in enumerate(coefficients) if coefficient]
    for values in product(range(base), repeat=len(taps)):
        history = {degree - 1 - i: markers[v] for i, v in zip(taps, values)}
        context = []
        for n in range(degree):
            context.extend(unit[:-1] + [history.get(n, marker_class)])
        result = sum(coefficients[i] * v for i, v in zip(taps, values)) % base
        lines.append('sub ' + ' '.join(context + current) +
                     f" {markers[0]}' lookup {name}{result};")
    # Full feedback has priority. With insufficient history, advance from the
    # preceding output instead of repeatedly using the same default state.
    for previous in range(base):
        context = unit[:-1] + [markers[previous]] + current
        result = (previous + startup_step) % base
        lines.append('sub ' + ' '.join(context) +
                     f" {markers[0]}' lookup {name}{result};")
    # Only a new run reaches these rules: established feedback and startup
    # history above take priority over any future glyph's seed bucket.
    for glyph_class, result in lookahead:
        lines.append('sub ' + ' '.join(current) +
                     f" {markers[0]}' lookup {name}{result} {glyph_class};")
    first = stream(base, coefficients, seed, 1)[0]
    lines.append('sub ' + ' '.join(current) +
                 f" {markers[0]}' lookup {name}{first};")
    lines.append(f'}} {name}Feedback;')
    return lines


def feature_source(font, tone_bases, gender_bases, assembly):
    cmap = font.getBestCmap()
    actual_tones = [cmap[cp] for cp in range(0x1F3FB, 0x1F400)]
    lines = ['languagesystem DFLT dflt;',
             '@tonebase = [' + ' '.join(sorted(tone_bases)) + '];',
             '@tone = [' + ' '.join(TONES) + '];',
             '@explicit = [' + ' '.join(actual_tones + [cmap[0x200D]]) + '];']
    # Hash glyph identity at build time. Internal markers are unencoded and
    # excluded, so the lookahead samples the next character's mapped glyph.
    encoded = set(cmap.values())
    lookahead = []
    for bucket in range(5):
        members = [name for gid, name in enumerate(font.getGlyphOrder())
                   if name in encoded and gid % 5 == bucket]
        if members:
            glyph_class = f'@seed{bucket}'
            lines.append(glyph_class + ' = [' + ' '.join(members) + '];')
            lookahead.append((glyph_class, bucket))
    if gender_bases:
        lines += ['@genderbase = [' + ' '.join(sorted(gender_bases)) + '];',
                  '@gender = [' + ' '.join(GENDERS) + '];']
    lines.append('lookup toneAppend {')
    for b in sorted(tone_bases):
        lines.append(f"sub {b} by {b} {TONES[0]};")
    lines.append('} toneAppend;')
    lines.append('lookup toneExpand useExtension {')
    lines.append("ignore sub @tonebase' @explicit;")
    # Do not introduce a skin tone when neither seed context nor prior output
    # exists. The unmodified base keeps its original default artwork.
    lines.append("sub @tonebase @tone @tonebase' lookup toneAppend;")
    for glyph_class, _ in lookahead:
        lines.append(f"sub @tonebase' lookup toneAppend {glyph_class};")
    lines.append('} toneExpand;')
    lines += _feedback('tone', TONES, TONE_COEFFICIENTS, TONE_SEED, 2, TONE_STARTUP_STEP, lookahead)
    if gender_bases:
        lines.append('lookup genderAppend {')
        lines += [f'sub {t} by {t} {GENDERS[0]};' for t in TONES]
        lines += ['} genderAppend;', 'lookup genderExpand {',
                  "sub @genderbase @tone' lookup genderAppend;", '} genderExpand;']
        lines += _feedback('gender', GENDERS, GENDER_COEFFICIENTS, GENDER_SEED, 3, GENDER_STARTUP_STEP)
    lines.append('lookup resolveTone {')
    lines += [f'sub {t} by {a};' for t, a in zip(TONES, actual_tones)]
    lines.append('} resolveTone;')
    if gender_bases:
        lines += ['lookup resolveGender {', f'sub {GENDERS[0]} by NULL;']
        lines += [f'sub {g} by {cmap[0x200D]} {cmap[cp]};'
                  for g, cp in zip(GENDERS[1:], (0x2640, 0x2642))]
        lines.append('} resolveGender;')
    lines.append('lookup modifierAssembly useExtension {')
    for sequence, target in sorted(assembly.items(), key=lambda item: (-len(item[0]), item[0])):
        lines.append('sub ' + ' '.join(sequence) + f' by {target};')
    lines += ['} modifierAssembly;', 'feature calt {', 'lookup toneExpand;', 'lookup toneFeedback;']
    if gender_bases:
        lines += ['lookup genderExpand;', 'lookup genderFeedback;']
    lines.append('lookup resolveTone;')
    if gender_bases:
        lines.append('lookup resolveGender;')
    lines += ['lookup modifierAssembly;', '} calt;']
    return '\n'.join(lines)


def _languages(gsub):
    for record in gsub.ScriptList.ScriptRecord:
        script = record.Script
        if script.DefaultLangSys is not None:
            yield script.DefaultLangSys
        for language in script.LangSysRecord:
            yield language.LangSys


def add_modifier_ligatures(font):
    from cluster_ligatures import _offset_references
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
    font.setGlyphOrder(original_order + list(MARKERS))
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
    info = dict(version=1, created_calt=created_calt, original_lookup_count=offset, lookup_count=len(new_lookups),
                original_glyph_count=len(original_order), marker_count=len(MARKERS),
                calt_roots=roots, tone_bases=len(tone_bases), gender_bases=len(gender_bases))
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
    if (info['version'] != 1 or len(gsub.LookupList.Lookup) != start + info['lookup_count']
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

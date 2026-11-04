# Contextual tone and gender variation

The default `calt` feature varies compatible plain emoji without changing the
input text. Five private states select the five existing tone variants; three private
states select neutral, woman and man artwork. Neither generator emits Unicode
modifier glyphs or ZWJ sequences. Their state glyphs have no cmap entries and
therefore no Unicode or Private Use Area codepoints. Explicit native tone and gender sequences assemble in `ccmp` before
these rules run, so the user's choices are preserved. Turning `calt` off restores
plain input rendering and disables zombie/sunflower/poop clustering.

Eligibility comes from native GSUB direct ligatures, using glyph identities rather
than naming conventions. A tone base must have all five tone outputs. A gender
base must additionally have both ZWJ gender outputs for every tone. The current
full fonts provide 135 tone bases and 50 gender bases, including runners and
person. For person (🧑), additional assembly aliases map the woman/man suffixes
to the existing 👩/👨 artwork, preserving tone. They also handle explicitly typed
person gender suffixes, including a tone already assembled by native `ccmp`. This
also allows intrinsically gendered base characters, such as woman, to vary tone;
both generators continue through them, and their gender state is simply ignored
when selecting artwork. Unsupported glyphs and spaces interrupt both histories.
The two streams advance across adjacent eligible bases, even when the base emoji
changes.

## Recurrences

Coefficients and seeds below are **newest first**. For a register `s`, emit
`v = sum(coefficients[i] * s[i]) mod base`, then shift to `[v] + s[:-1]`.
The virtual initial registers below reproduce the short-history fallback
sequence with the default initial outputs: middle tone (2) and neutral gender (0).

| Stream | Base | Coefficients | Seed | Period |
| --- | --- | --- | --- | --- |
| Tone | 5 | `[0,1,1,2]` | `[2,2,3,1]` | 625 |
| Gender | 3 | `[0,0,1,1]` | `[0,2,2,1]` | 81 |

Two full-register exceptions precede the ordinary sparse feedback rules. In
chronological order, replace the edge `1,0,0,0 -> 0,0,0,c[-1]` with
`1,0,0,0 -> 0,0,0,0 -> 0,0,0,c[-1]`, where `c[-1]` is the oldest tap coefficient
(2 for base 5, 1 for base 3). This visits every four-digit register exactly once,
including zero. Every tone occurs 125 times per 625 outputs; every gender state
occurs 27 times per 81 outputs. The independent pair of registers has period
`lcm(625,81) = 50,625` on an uninterrupted run. Artwork mappings can collapse
several states, so visible repetitions may be shorter.

When full feedback cannot match, fallback rules use the preceding output:
tone advances by 3 modulo 5, and gender by 1 modulo 3. A new tone run hashes the
current and following mapped glyphs with `glyphID % 5`. The initial tone is
`(currentBucket + followingBucket) % 5`. Without classified lookahead, the
current glyph's bucket alone chooses its tone, so isolated bases can differ.
The current-glyph classes are intersections of the broad seed classes with
the tone-compatible base class. The middle (medium) tone remains the final
defensive default after those rules. Gender reuses exactly the same five broad
seed classes and tone intersections. Every tone-compatible base receives a
gender state, even if its artwork ignores that state. For a single glyph, buckets 1 and 2
select woman and man respectively; buckets 0, 3 and 4 select neutral. For pairs,
`(currentBucket + followingBucket + 2) % 3` gives nine neutral, eight woman and
eight man combinations. Neutral remains the defensive gender default.
Startup visits four distinct tones and all three genders before their
respective full feedback rules can match.
Full feedback has priority and takes over after four outputs in either stream.
Unsupported glyphs restart these fallbacks.

With default initial tone 2, outputs start `2,0,3,1,2,4,4,3,2,0,3,3,2,1,1,4`
(zero means U+1F3FB). Other initial tones rotate the first four fallback
outputs; the same full feedback then applies to the resulting register.
With neutral initial gender, outputs start `0,1,2,0,1,0,2,1,1,2,0,2,0,2,2,2`. These deterministic
streams provide pseudorandom visual variation. Tests enumerate
all possible register windows to verify both full periods and the combined period.

## Shaping and build cache

Tone expansion creates `BASE TONE_INTERNAL` units at stride two. Tone feedback
matches two zero-splice exceptions and 125 sparse tap combinations, followed by five previous-state fallbacks,
25 current/lookahead seed rules, five current-glyph seed rules, and an internal
first-output default. The five broad seed classes
are generated at build time from encoded glyph IDs, excluding internal markers.
GSUB stores their membership as coverage lists/ranges; it performs no bitwise
operation during shaping. No extra lookup or state glyph is needed.
Lookahead only sees glyphs in the same shaping run, and identical glyphs give
identical seeds. Glyph ordering can give the two font formats different seeds.
Gender expansion then creates
`BASE TONE_INTERNAL GENDER_INTERNAL` units at stride three. Gender feedback uses
two zero-splice exceptions and nine tap combinations, three previous-state fallbacks, 25 current/lookahead seed
rules, five current-glyph seed rules, and a first-output default. No extra
membership class or marker glyph is added for gender seeding.

Each root lookup completes its full scan before the next root runs:

1. Expand eligible bases to `BASE STATE5` and run base-5 feedback at stride two.
2. Append `STATE3` to **every** such unit and run base-3 feedback at stride three.
3. Fold `BASE STATE5 STATE3` directly into an existing artwork glyph. For bases
   without gender variants, all three gender states select the same toned glyph.
4. Sweep any remaining private state glyphs with GSUB multiple-substitution
   deletion rules (`sub ... by NULL`). A missing fold mapping leaves its base
   unchanged, without leaking state into later lookups.
5. Run restricted native assembly aliases, including explicitly typed person
   gender suffixes. These see no internal state glyphs.

Generation, folding and sweeping are separate top-level lookups. Cleanup cannot
run halfway through either feedback pass. Native `ccmp` has already assembled
explicit user modifiers **before** private states are inserted, so those native
rules never encounter the temporary glyphs either. A new variant family can
provide a different state-pair-to-artwork mapping without needing Unicode
modifier sequences or new feedback generators. This change adds no flower or
zombie variation artwork.

`OS/2.usMaxContext` is recalculated for the new contexts.

`add_cluster_ligatures` installs both bundles. Install on a native baseline; a
second call on the same in-memory font is a no-op. Serialized fonts must have
the previous modifier bundle removed using its manifest before applying fresh
rules. Metadata version 2 records the new pipeline and periods; recovery still
accepts version 1 published bundles. Marker names are not persistent metadata (post format 3 may rename them).

`web/cache_fonts.py apply` writes per-font bundle descriptions to
`build/modifiers.json`; packaging embeds them in the public `build.json`.
Bootstrap recovery first validates and removes the modifier lookups and marker
glyphs, restores the prior maximum context, and then removes the cluster bundle
and any supplemental artwork using the public `artwork` manifest.
The native artwork cache is never modified by rule application. No custom font
table or workflow/Makefile cache-key change is needed.
If the compiler fingerprint changes, recovery verifies that all native artwork
and build sources match the published commit before reusing its fonts. The
original fingerprint is retained as `native_origin_key` in `build.json`.

Validation lives in `tests/test_cluster_ligatures.py`, which the existing font
workflow already runs. The browser smoke check compares actual runner pixels
with `calt` enabled/disabled in each font format and checks that explicit
sequences render identically. HarfBuzz tests check glyph identities and neutral
marker removal rather than relying on equal-advance artwork widths.

Full-font validation covers uninterrupted and mixed-base streams, all explicit
runner tone/gender variants with and without VS16, `calt` disabled, marker
absence in shaped output, and serialized cache recovery. HarfBuzz tests also
stop immediately before folding to inspect both private state streams, then
remove artwork mappings deliberately to verify that the sweep leaves the
original bases and explicit user sequences intact.

Measured GSUB sizes after this refactor are 173,604 bytes (CBDT) and 155,668
bytes (COLRv1). The modifier bundle still adds 17 lookups and eight unencoded
state glyphs.

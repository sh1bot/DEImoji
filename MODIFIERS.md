# Contextual tone and gender variation

The default `calt` feature varies compatible plain emoji without changing the
input text. Five tone states map to U+1F3FB through U+1F3FF; gender states are
neutral, woman and man. Neutral gender removes its internal marker and adds no
ZWJ suffix. Explicit native tone and gender sequences assemble in `ccmp` before
these rules run, so the user's choices are preserved. Turning `calt` off restores
plain input rendering and disables the existing zombie/sunflower clustering.

Eligibility comes from native GSUB direct ligatures, using glyph identities rather
than naming conventions. A tone base must have all five tone outputs. A gender
base must additionally have both ZWJ gender outputs for every tone. The current
full fonts provide 135 tone bases and 50 gender bases, including runners and
person. For person (🧑), additional assembly aliases map the woman/man suffixes
to the existing 👩/👨 artwork, preserving tone. They also handle explicitly typed
person gender suffixes, including a tone already assembled by native `ccmp`. This
also allows intrinsically gendered base characters, such as woman, to vary tone;
they interrupt gender history. Unsupported glyphs and spaces interrupt history.
The two streams advance across adjacent eligible bases, even when the base emoji
changes.

## Recurrences

Coefficients and seeds below are **newest first**. For a register `s`, emit
`v = sum(coefficients[i] * s[i]) mod base`, then shift to `[v] + s[:-1]`.
The virtual initial registers below reproduce the short-history fallback
sequence when the initial output is zero.

| Stream | Base | Coefficients | Seed | Period |
| --- | --- | --- | --- | --- |
| Tone | 5 | `[0,0,0,0,0,1,1,2]` | `[4,2,2,4,4,4,0,3]` | 390624 |
| Gender | 3 | `[0,0,0,0,1,0,2]` | `[1,1,0,1,1,0,1]` | 2186 |

When full feedback cannot match, fallback rules use the preceding output:
tone advances by 3 modulo 5, and gender by 1 modulo 3. A new tone run hashes the
following mapped glyph with `glyphID % 5`: buckets 0 through 4 select all five
initial tones. With neither classified lookahead nor preceding generated tone,
the base is left unmodified, retaining its original default color. Gender starts
at zero. A seeded run gives all five tones in the first five positions and
all three genders in the first three, instead of a repeated startup default.
Full feedback has priority and takes over after eight tone outputs or seven
gender outputs. Unsupported glyphs restart these fallbacks.

With initial tone zero, outputs start `0,3,1,4,2,0,3,1,4,1,3,0,2,4,1,2`
(zero means U+1F3FB). Other initial tones rotate the first eight fallback
outputs; the same full feedback then applies to the resulting register.
Gender outputs start `0,1,2,0,1,2,0,2,2,2,2,2,0,2,0,0`. These deterministic
streams provide pseudorandom visual variation. Tests iterate each register until
its first return to the seed to verify the full maximal periods.

## Shaping and build cache

Tone expansion creates `BASE TONE_INTERNAL` units at stride two only when there
is seed context or a preceding generated unit. Otherwise the original glyph
passes through without any skin modifier, rather than defaulting to lightest.
Tone feedback
matches 125 sparse tap combinations, followed by five previous-state fallbacks,
five lookahead seed rules, and an internal first-output default. The five seed classes
are generated at build time from encoded glyph IDs, excluding internal markers.
GSUB stores their membership as coverage lists/ranges; it performs no bitwise
operation during shaping. No extra lookup or state glyph is needed.
Lookahead only sees glyphs in the same shaping run, and identical glyphs give
identical seeds. Glyph ordering can give the two font formats different seeds.
Gender expansion then creates
`BASE TONE_INTERNAL GENDER_INTERNAL` units at stride three. Gender feedback uses
nine tap combinations, three previous-state fallbacks, and a first-output
default. Only after feedback finishes
are the eight unencoded, zero-advance marker glyphs resolved into real Unicode
modifier glyphs and ZWJ gender sequences. A restricted clone of canonical native
ligatures assembles those sequences into existing artwork. No artwork is rebuilt.
`OS/2.usMaxContext` is recalculated for the new contexts.

`add_cluster_ligatures` installs both bundles. Install on a native baseline; a
second call on the same in-memory font is a no-op. Serialized fonts must have
the previous modifier bundle removed using its manifest before applying fresh
rules. Marker names are not persistent metadata (post format 3 may rename them).

`web/cache_fonts.py apply` writes per-font bundle descriptions to
`build/modifiers.json`; packaging embeds them in the public `build.json`.
Bootstrap recovery first validates and removes the modifier lookups and marker
glyphs, restores the prior maximum context, and then removes the cluster bundle.
The native artwork cache is never modified by rule application. No custom font
table or workflow/Makefile cache-key change is needed.

Validation lives in `tests/test_cluster_ligatures.py`, which the existing font
workflow already runs. The browser smoke check compares actual runner pixels
with `calt` enabled/disabled in each font format and checks that explicit
sequences render identically. HarfBuzz tests check glyph identities and neutral
marker removal rather than relying on equal-advance artwork widths.

Measured on the full native font pair, the installed GSUB is 123,756 bytes for
CBDT (+69,834 bytes including both custom bundles), and 105,582 bytes for COLRv1
(+74,156 bytes including both custom bundles). The modifier installer appends
17 lookups and eight glyphs. Full-font validation also checks 120-run glyph
identities, all explicit runner tone/gender variants with and without VS16,
`calt` disabled, mixed explicit/plain boundaries, and serialized cache recovery.

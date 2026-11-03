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
full fonts provide 135 tone bases and 49 gender bases, including runners. This
also allows intrinsically gendered base characters, such as woman, to vary tone;
they interrupt gender history. Unsupported glyphs and spaces interrupt history.
The two streams advance across adjacent eligible bases, even when the base emoji
changes.

## Recurrences

Coefficients and seeds below are **newest first**. For a register `s`, emit
`v = sum(coefficients[i] * s[i]) mod base`, then shift to `[v] + s[:-1]`.
The mixed nonzero seed supplies virtual history at the start of every run.

| Stream | Base | Coefficients | Seed | Period |
| --- | --- | --- | --- | --- |
| Tone | 5 | `[0,0,0,0,0,1,1,2]` | `[1,2,3,4,1,2,3,4]` | 390624 |
| Gender | 3 | `[0,0,0,0,1,0,2]` | `[1,2,1,2,1,2,1]` | 2186 |

Tone outputs start `3,4,4,4,3,4,3,4,4,1,0,0,3,0,4,3` (zero means U+1F3FB).
Gender outputs start `0,0,0,0,0,1,2,0,0,0,1,2,2,1,0,1`. A short prefix therefore
need not show every state. These deterministic streams provide pseudorandom
visual variation. Tests iterate each register until its first return
to the seed to verify the full maximal periods.

## Shaping and build cache

Tone expansion creates `BASE TONE_INTERNAL` units at stride two. Tone feedback
matches 125 sparse tap combinations; eight descending startup contexts handle
short history. Gender expansion then creates
`BASE TONE_INTERNAL GENDER_INTERNAL` units at stride three. Gender feedback uses
nine tap combinations and seven startup contexts. Only after feedback finishes
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

Measured on the full native font pair, the installed GSUB is 119,936 bytes for
CBDT (+66,014 bytes including both custom bundles), and 101,520 bytes for COLRv1
(+70,094 bytes including both custom bundles). The modifier installer appends
17 lookups and eight glyphs. Full-font validation also checks 120-run glyph
identities, all explicit runner tone/gender variants with and without VS16,
`calt` disabled, mixed explicit/plain boundaries, and serialized cache recovery.

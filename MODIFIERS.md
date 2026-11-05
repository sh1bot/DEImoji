# Contextual variation with private state

The default `calt` feature varies compatible plain emoji without changing input
text. Five private states select the existing tone variants; three private
states select neutral, woman and man artwork. They have no cmap entries, Unicode
assignments or Private Use Area codepoints. Both states fold directly into
artwork, without generating Unicode skin-tone or ZWJ gender sequences.

Native `ccmp` assembles explicit user sequences before private states exist.
Typed choices are preserved, including person gender aliases. Turning `calt`
off restores plain rendering and disables zombie/sunflower/poop clustering.

## Eligibility and noise

Artwork eligibility comes from native GSUB ligatures. A tone base must have all
five tone outputs. A gender base must also have both gender outputs for every
tone. The current full fonts supply 135 tone bases and 50 gender bases, including
person (whose gender choices reuse the separate woman/man artwork).

Seed collection is broader than artwork eligibility. It includes mapped input
glyphs and native/cluster GSUB output glyphs: ordinary mapped text, spaces,
punctuation, plain emoji and already assembled explicit emoji can all contribute.
Unreachable COLRv1 outline components are excluded; they never enter the text
buffer. Five classes partition source glyphs by `glyphID % 5` at build time.
The same classes serve both hashes; no runtime bitwise operation is involved.

The missing-glyph placeholder and glyphs mapped to default-ignorable controls
are protected. Substituting those glyphs can prevent HarfBuzz from hiding a
stray ZWJ or unsupported variation selector. They are left entirely untouched.
A source outside the available carrier set can end hash propagation.

Only glyphs in the same shaping run are visible. A font cannot recover original
characters that became the same missing glyph, or read another font's run.
The playground retains its normal-text spans, so ordinary surrounding text
rendered in the system font does not contribute there.

## Right-to-left seed collection

Every source glyph receives two zero-advance private slots:

```
SOURCE STATE5 STATE3  SOURCE STATE5 STATE3 ...
```

A reverse-chaining single-substitution lookup (GSUB type 8, with an extension
wrapper) accumulates the suffix right to left in base five:

```
here5 = (2 * hash5_to_the_right + source_bucket + 1) % 5
```

The terminal value is `(-source_bucket) % 5`. It covers all five singleton
tones and differs from the repeated-source recurrence's fixed point
`(-source_bucket - 1) % 5`, so repeated runs retain length variation. This uses
25 bucket/future-state rules plus five terminal rules, with no ladder of longer
lookaheads. Insertion has one entry per reachable source glyph.

The base-3 startup then borrows the **completed base-5 hash**, before forward
feedback changes either stream:

```
seed3 = (((here5 + source_bucket + 1) % 5) + source_bucket + 2) % 3
```

This is a local 25-entry remapping, compiled into 15 grouped rules using the
existing five source classes and no extra glyphs. It does not recursively read the next base-3 state. Across all
25 bucket/hash combinations it gives nine neutral, eight female and eight male
seeds. Four identical eligible bases expose all three gender seed states in
every source bucket. At a singleton, `here5 = -bucket`, so `seed3 = bucket % 3`.

The previous separate ternary hash used multiplier 2, which is -1 modulo 3.
It worked mechanically but reduced repeated input to an alternating sum: pairs
of identical sources cancelled, and homogeneous startup used only two states.
A direct `here5 % 3` mapping would also omit one gender for one of the five
repeated-source cycles. Rebasing around that cycle's fixed point avoids this.

Each of the first four eligible positions keeps its own suffix hash. There is
no previous-output startup cycle and no current/next-only seed fallback.
Full feedback takes priority once four previous eligible outputs are present.
Noneligible glyphs break forward feedback history, while their seed carriers
allow reverse hash collection through them. Consequently later text can affect
an earlier run's seed even across a noneligible glyph in the same shaping run.
These are deterministic hashes, not cryptographic randomness or new entropy.

## Full-period generators

Coefficients and register values below are newest first. Ordinary feedback emits
`v = sum(coefficients[i] * state[i]) % base`, then shifts to `[v] + state[:-1]`.

| Stream | Base | Coefficients | Period |
| --- | --- | --- | --- |
| Tone | 5 | `[0,1,1,2]` | 625 |
| Gender | 3 | `[0,0,1,1]` | 81 |

Two full-register exceptions precede sparse feedback. In chronological order,
replace `1,0,0,0 -> 0,0,0,c[-1]` with
`1,0,0,0 -> 0,0,0,0 -> 0,0,0,c[-1]`. This visits every four-digit register exactly
once, including zero. Every tone occurs 125 times per 625 outputs and every
gender state 27 times per 81 outputs. The independent register pair has period
`lcm(625,81) = 50,625` on an uninterrupted eligible run. Artwork mappings may
collapse states, so visible repetition can be shorter.

Both forward generators advance through every eligible base. A base without
gender variants ignores that state during artwork selection; it does not stop
the gender clock. Spaces and other ineligible glyphs reset forward history.

## Ordered folding and cleanup

Root lookups run in this order; each finishes its scan before the next starts:

1. Insert both private slots after source glyphs.
2. Complete the base-5 reverse suffix hash.
3. Remap the stored base-5 hash and source bucket into base-3 startup state.
4. Run base-5 feedback left to right, using the collected short-history seeds.
5. Run base-3 feedback left to right.
6. Fold `BASE STATE5 STATE3` directly into existing artwork. Ignore bases with
   explicit modifier suffixes that native assembly left unresolved.
7. Delete **all** remaining state glyphs, including noise-only carriers and
   unmatched artwork cases (`sub ... by NULL`).
8. Run restricted native assembly aliases, including typed person gender forms.

Cleanup is a separate root lookup and cannot erase history halfway through a
feedback scan. Native assembly runs before states exist; late aliases run after
states are swept. No flower or zombie variation artwork is added by this system.

## Build, recovery and verification

`add_cluster_ligatures` installs both bundles. Repeat in-memory installation is a
no-op. Serialized fonts must have their old bundle removed using its manifest
before installing fresh rules. State names are not persistent metadata: post
format 3 may rename them. All original glyph IDs and cmap entries are preserved.
`OS/2.usMaxContext` is recalculated.

Metadata version 4 records `seeding: reverse-suffix-all-source-glyphs`,
`gender_seeding: base5-hash-and-source-bucket`, carrier count, periods and lookup
roots. Recovery still accepts published bundles of versions 1, 2 and 3. `web/cache_fonts.py apply` writes descriptions to
`build/modifiers.json`; packaging embeds them in `build.json`. Recovery removes
modifier rules/states, cluster rules, and supplemental artwork in that order.
Native artwork is cached separately and never modified by rule application.

HarfBuzz tests inspect the private streams before folding, deliberately remove
artwork mappings to verify cleanup, change distant noneligible suffix glyphs,
check full periods and preserve explicit sequences/default-ignorables.
The packaged-font verification repeats feedback and distant-noise checks against
the actual downloadable TTFs and WOFF2, verifies their checksums and artwork, and
then runs Chromium checks. Successful builds publish a commit-matched
`checks.json` report linked from the test page.

For the current complete fonts, the modifier bundle still uses 17 lookups and
8 private glyphs. It has 4,013 source carriers in CBDT and 4,019 in COLRv1.
Most added storage is the one-entry-per-source insertion map.

## Custom zombie compositions

A private, normally inactive `DVAR` alternate feature records five choices for
each original zombie pair/trio glyph. The generic discovery step reads it as a
five-state artwork family without inventing skin-tone or hair Unicode sequences.
Binary grouping completes first; the two cluster-size glyphs then join the
eligible diversity class. Each cluster advances the shared base-5 clock once.
The base-3 clock also advances, but its value is ignored for zombie compositions.
Native tone eligibility remains 135 bases; two custom bases make 137 diversity
bases. The singleton and explicit native zombie forms are unchanged.

The zombie pack is nested in the public artwork manifest. Recovery removes
modifier rules and cluster rules first, then the zombie registry and glyph tail,
then the earlier poop pack. Native cache inputs and original glyph IDs stay
unchanged. Kerning covers the ten new outputs while preserving singleton pairs.

Packaged-font verification pauses the actual GSUB pipeline after seed mapping
and inspects the private gender slots for four repeated eligible glyphs in
all five source buckets, in both TTFs and WOFF2. The report records this coverage.

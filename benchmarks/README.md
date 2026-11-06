# Font loading and shaping benchmark

`web/benchmark_fonts.py` compares actual font files using FontTools and the system
HarfBuzz library. It times directory loading, layout-table decoding, cold first
shaping and warmed shaping separately. It does not render pixels. Each report
records exact SHA-256 hashes, library versions, input strings, feature settings
and output glyph counts. Results are local measurements, not browser guarantees.

The production upstream comparison is pinned to Noto Emoji commit
`99701e07d3d1fe1bdbcdb14964547f0fd592966f`, using its `2D/fonts/` directory.
The optional native-cache baseline has the same compilation pipeline as our
build, with the pre-existing zombie/sunflower assets and native assembly rules,
before current contextual rules and supplemental artwork. It is not a pristine
upstream release. File sizes and glyph counts expose those differences.

Download the two pinned upstream TTFs into `build/upstream-fonts/`, build DEImoji,
then run (fontTools is in the project dependencies; install system HarfBuzz):

```sh
python web/benchmark_fonts.py \
  --upstream-ref 99701e07d3d1fe1bdbcdb14964547f0fd592966f \
  --font upstream-cbdt=build/upstream-fonts/NotoColorEmoji.ttf \
  --font native-cbdt=build/native-fonts/NotoColorEmoji.ttf \
  --font deimoji-cbdt=build/site/fonts/DEImoji-CBDT.ttf \
  --font upstream-colr=build/upstream-fonts/Noto-COLRv1.ttf \
  --font native-colr=build/native-fonts/Noto-COLRv1.ttf \
  --font deimoji-colr=build/site/fonts/DEImoji-COLRv1.ttf \
  --output benchmarks/latest.json
```

Omit the two `native-*` arguments to compare just pristine upstream and DEImoji.
All strings are shaped as single-font buffers; the plain-text diagnostic records
unmapped characters rather than pretending system-font fallback was measured.
`calt` on/off measurements help separate the cost of contextual features from
ordinary shaping. Font directory/layout parsing is independent of that switch.

## Unaffected glyph checks

The added diagnostics use mapped emoji with no diversity or clustering rules:
36 and 3,200 glyphs from `🐈🚗🍎📚`, plus 3,200 repeated `🐈`. For each
unaffected case the runner requires zero missing codepoints and identical
glyph IDs and positions with `calt=0` and `calt=1`. It records cluster-map
equality too. These checks are outside the timed portions.

## Recorded run

See [`latest.json`](latest.json) for full precision, hashes and provenance. The
DEImoji inputs in this report are the published build `15efc48`, with the cross
behind in the pair. Times below are local medians in milliseconds. Python
eagerly decodes all layout tables; HarfBuzz loads tables on demand.

| Font | Python layout decode | HB cold first shape | 36 runners | 3,200 runners |
| --- | ---: | ---: | ---: | ---: |
| upstream-cbdt | 31.656 | 0.464 | 0.005 | 0.241 |
| native-cbdt | 30.636 | 2.107 | 0.005 | 0.253 |
| deimoji-cbdt | 234.116 | 2.166 | 0.206 | 19.114 |
| upstream-colr | 62.290 | 0.162 | 0.005 | 0.268 |
| native-colr | 83.394 | 0.212 | 0.005 | 0.367 |
| deimoji-colr | 469.432 | 0.973 | 0.322 | 23.753 |

Shaping columns above use `calt=1`. The unaffected cases isolate the overhead
when the visible result does not change:

| Font | 36 unaffected, off | 36 unaffected, on | 3,200 unaffected, off | 3,200 unaffected, on |
| --- | ---: | ---: | ---: | ---: |
| upstream-cbdt | 0.0037 | 0.0036 | 0.1023 | 0.1081 |
| deimoji-cbdt | 0.0038 | 0.1703 | 0.1255 | 16.7885 |
| upstream-colr | 0.0038 | 0.0037 | 0.1318 | 0.1414 |
| deimoji-colr | 0.0039 | 0.1776 | 0.1277 | 15.7855 |

All unaffected tests preserved glyphs, positions and cluster maps. The JSON
also records the native-cache baseline, repeated-cat runs, long cluster runs,
mixed runs, explicit modifiers and plain-text diagnostics. Native-cache bitmap
files retain unoptimized PNGs, so cold blob-copy cost differs from the compressed
upstream release. No PNG decoding or colour painting is timed.

## Browser layout and rendering

[`rendering.json`](rendering.json) records a separate Chromium experiment using
actual upstream and published DEImoji fonts, with upstream as the primary
baseline. All samples are unaffected emoji `🐈🚗🍎📚`. Font loading and initial
colour-glyph drawing are warmed before timing. Each trial uses a new DOM node
and a distinct text payload; paired `calt=0/1` screenshots must have identical
pixels.

The viewport is 1320×4200 at device scale 1, with 32 px text, 40 px line height,
a 1280 px text column and ordinary `word-break: normal`. Every glyph in each
wrapped sample, including all 3,200, is visible. The separate no-wrap diagnostic
measures layout of the whole run but only paints the visible viewport, so its
paint figures are not an all-glyph rendering comparison.

The traced columns below are medians in milliseconds with `calt=1`. Forced
layout includes DOM mutation, style resolution, text shaping and line breaking.
Paint recording is main-thread display-list work. Raster CPU sums worker time
and may overlap other work: **do not add it to layout as wall-clock time**.
Screenshot capture flushes raster work, but PNG encoding/readback/transport are
excluded from the selected trace metrics. Two-RAF latency is recorded as a
scheduling diagnostic, not used as a CPU rendering time.

| Font | 36 wrapped: layout | 3,200 wrapped: layout | 3,200: paint recording | 3,200: raster CPU |
| --- | ---: | ---: | ---: | ---: |
| upstream-colr | 0.700 | 1.600 | 0.183 | 4.607 |
| deimoji-colr | 1.100 | 909.100 | 0.186 | 6.390 |
| upstream-cbdt | 0.500 | 1.600 | 0.186 | 5.107 |
| deimoji-cbdt | 1.100 | 862.400 | 0.228 | 6.778 |

The additional controls repeat the same DOM layout operation with tracing
disabled, to check that the long-run result is not a tracing artifact:

| Font | 3,200 wrapped: untraced layout | 3,200 no-wrap: untraced layout |
| --- | ---: | ---: |
| upstream-colr | 1.200 | 1.400 |
| deimoji-colr | 835.900 | 18.100 |
| upstream-cbdt | 1.300 | 1.100 |
| deimoji-cbdt | 883.000 | 18.200 |

This was headless Chromium 154.0.8037.57 on Linux using
SwiftShader software graphics. It measures this repeated-emoji, warm-cache
workload, not physical display presentation or every application's rendering.
The trace localizes the dominant slowdown to Layout; it does not establish the
exact internal reason for repeated shaping during wrapping.

Reproduce with Playwright, Chromium, Pillow, fontTools and the same four TTFs:

```sh
python web/benchmark_rendering.py \
  --font upstream-colr=build/upstream-fonts/Noto-COLRv1.ttf \
  --font deimoji-colr=build/site/fonts/DEImoji-COLRv1.ttf \
  --font upstream-cbdt=build/upstream-fonts/NotoColorEmoji.ttf \
  --font deimoji-cbdt=build/site/fonts/DEImoji-CBDT.ttf \
  --chromium /usr/bin/chromium --trials 3 \
  --output benchmarks/rendering.json
```

## Pass ablation and seeding controls

`web/benchmark_passes.py` creates **diagnostic copies** of the exact published
fonts identified by `build.json`. Every original lookup remains in the base
copy; its nine root passes are exposed as private features instead of the normal
`calt` entry point. These copies are not release fonts. Generated TTFs stay under
`build/`, not in the published font downloads.

| Pass | Diagnostic feature |
| --- | --- |
| clustering | `DCLT` |
| expansion | `DEXP` |
| suffix_hash | `DHSH` |
| gender_seed | `DGSD` |
| tone_feedback | `DTFB` |
| gender_feedback | `DGFB` |
| folding | `DFLD` |
| sweep | `DSWP` |
| assembly | `DASM` |

The runner validates that enabling all nine features reproduces original glyphs,
positions and clusters on affected and unaffected strings. It measures original
on/off, actual upstream, all-off/all-on diagnostic controls, every leave-one-out
case, and minimal expansion+one-pass+sweep combinations. Chromium samples use
3,200 mapped unaffected emoji, at 32 px, with ordinary wrapping and all glyphs
visible. A separate no-wrap layout diagnostic is included. Pixel comparisons
against the original font with rules off must match for every diagnostic case.

Removing **expansion** makes marker-dependent rules inapplicable. Removing the
**RTL hash does not**: zero-valued tone/gender slots already exist. Both feedback
generators were checked directly with all seeders disabled: their fifth outputs
are tone 2 and gender 1, proving they still execute. The full private-state
sequences are recorded in `feedback_without_rtl` in the reports.

`without_sweep` is intentionally **not a valid final output**: it retains 6,400
private zero-advance glyphs even though the pixels match. Its timing is diagnostic
only. All other configurations keep valid cleanup.

### Leave-one-out results

[`passes.json`](passes.json), wrapped layout medians in milliseconds:

| Configuration | COLRv1 | CBDT |
| --- | ---: | ---: |
| upstream | 1.4 | 1.3 |
| original_off | 1.9 | 1.2 |
| original_on | 891.3 | 878.7 |
| diagnostic_off | 1.8 | 1.4 |
| full | 873.1 | 846.6 |
| without_clustering | 817.9 | 891.7 |
| without_expansion | 1.4 | 1.5 |
| without_suffix_hash | 22.5 | 16.8 |
| without_gender_seed | 979.7 | 873.1 |
| without_tone_feedback | 149.3 | 158.0 |
| without_gender_feedback | 875.2 | 812.0 |
| without_folding | 820.1 | 866.7 |
| without_sweep | 878.0 | 967.2 |
| without_assembly | 830.9 | 919.8 |
| expansion_sweep | 1.5 | 1.4 |
| clustering_only | 1.2 | 1.4 |
| expansion_suffix_hash_sweep | 68.9 | 62.0 |
| expansion_gender_seed_sweep | 1.8 | 2.2 |
| expansion_tone_feedback_sweep | 17.7 | 16.4 |
| expansion_gender_feedback_sweep | 3.2 | 3.3 |
| expansion_folding_sweep | 1.5 | 1.9 |
| expansion_assembly_sweep | 1.5 | 1.5 |

HarfBuzz also records glyph counts, remaining private markers and
`UNSAFE_TO_BREAK` flags. With the RTL hash, 3,199 of the 3,200 final glyphs carry
that flag. Removing that pass clears them and removes the large wrapping
amplification. Tone-feedback matching remains the largest standalone CPU cost
on this ineligible input (about 13 ms), despite making no visible substitution.
The measurements identify an interaction, rather than one additive paint cost.

### Replacement seeders

[`seeding.json`](seeding.json) tests two replacements at the original hash stage,
leaving the downstream pipeline intact:

* **LTR:** mirror the recurrence to depend on the prior source hash. It changes
  suffix-based seeding into prefix-based seeding, not identical seed values.
* **Local:** use the same negative glyph-ID bucket as a singleton terminal seed,
  with no adjacent-source dependency. It has less contextual variation.

Both preserve valid state slots. Independent expected-state calculations verify
their actual output sequences. These are policy experiments, not production
seeding changes.

| Configuration | COLRv1 wrapped layout | CBDT wrapped layout |
| --- | ---: | ---: |
| original_on | 883.0 | 908.2 |
| seed_ltr_full | 860.0 | 962.6 |
| seed_ltr_hash_only | 86.1 | 79.4 |
| seed_local_full | 17.9 | 19.1 |
| seed_local_hash_only | 1.9 | 2.7 |

The LTR hash still produces 3,199 unsafe-to-break glyphs. Local seeding produces
none. Direction alone is not the remedy; cross-source contextual dependencies
cause the break-safety issue. Full local seeding still pays tone-feedback
matching cost, while local seeding with just expansion/hash/sweep is near 2 ms.

Reproduce the recorded datasets (Playwright, Chromium, fontTools and Pillow):

```sh
python web/benchmark_passes.py --site build/site \
  --upstream build/upstream-fonts --work build/pass-ablation \
  --config-set ablation --chromium /usr/bin/chromium --trials 3 \
  --output benchmarks/passes.json
python web/benchmark_passes.py --site build/site \
  --upstream build/upstream-fonts --work build/pass-seeding \
  --config-set seeders --chromium /usr/bin/chromium --trials 3 \
  --output benchmarks/seeding.json
```

`--config-set all` runs both sets in one report. With a generated diagnostic
font, explicitly enable the desired four-letter tags through
`font-feature-settings`; keep `DSWP` enabled whenever `DEXP` is enabled, except
when deliberately reproducing the invalid-output cleanup experiment. Source
font hashes must match the accompanying build metadata.

### Buffer growth control

[`buffer.json`](buffer.json) compares fresh buffers, fresh buffers preallocated to
12,800 glyphs, and warmed reused buffers. Font setup and explicit preallocation
are outside the timer; shaping includes reset and UTF-8 insertion. Each result
is the median of 25 trials on 3,200 unaffected emoji, using the same partitioned
COLRv1 font. Fresh/preallocated trial order alternates.

| Enabled passes | Fresh | Preallocated | Reused |
| --- | ---: | ---: | ---: |
| none | 0.177 ms | 0.177 ms | 0.128 ms |
| expansion + sweep | 0.390 ms | 0.382 ms | 0.325 ms |
| expansion + RTL hash + sweep | 1.179 ms | 1.171 ms | 1.125 ms |
| full pipeline | 15.555 ms | 15.553 ms | 15.145 ms |

Preallocation does not materially reduce these times. This is a capacity control,
not an allocator-call trace. Source inspection of the measured HarfBuzz 10.2.0
also rules out a reallocation per insertion:

* [`enlarge`](https://github.com/harfbuzz/harfbuzz/blob/10.2.0/src/hb-buffer.cc#L158)
  increases capacity geometrically (`capacity += capacity / 2 + 32`).
* `make_room_for` switches to a separate output buffer when expansion would
  overwrite unread input, rather than shifting the entire suffix per insertion.
* `reset`/`clear` reset lengths and retain allocated capacity. The earlier warm
  shaping benchmarks already reuse buffers this way.

The recursive RTL hash itself is length-preserving single substitution; expansion
is a separate pass. Both LTR and local seeding experiments retain exactly that
same expansion. Their wrapped-layout difference therefore cannot be attributed
to a different number of inserted state glyphs. A moving entropy payload might
reduce temporary glyph count, but cannot in itself remove the semantic dependency
across a line boundary; it would need a separate break-safety measurement.

```sh
python web/benchmark_buffer.py --font build/pass-seeding/colr-diagnostic.ttf \
  --output benchmarks/buffer.json --trials 25
```

### Bounded lookahead seeding

[`bounded.json`](bounded.json) tests windows of 1, 2, 4 and 8 original source
glyphs, including the current source. Window 1 is the local control. Each stage
reads one original future source bucket, never that position's accumulated
state. The hash starts at `-current_bucket mod 5` and folds each available future
bucket with `h = (2*h + bucket + 1) mod 5`; short suffixes use what is available.
Stages execute at the original hash position, before downstream LFSR passes.

This keeps rule count linear in the window: 5 initialization rules plus 25 per
additional source, rather than enumerating every possible source combination.
It uses more hash lookups as the window grows, so the experiment measures this
implementation rather than a theoretical lower bound for bounded hashing.

| Seeding | COLRv1 wrapped | CBDT wrapped | Unsafe glyphs |
| --- | ---: | ---: | ---: |
| upstream | 1.5 ms | 1.4 ms | — |
| original recursive RTL | 819.6 ms | 882.3 ms | — |
| window 1, full pipeline | 17.5 ms | 17.8 ms | 0 |
| window 2, full pipeline | 811.5 ms | 892.6 ms | 3199 |
| window 4, full pipeline | 870.4 ms | 933.8 ms | 3199 |
| window 8, full pipeline | 1070.0 ms | 1106.1 ms | 3199 |

Even two-source lookahead leaves 3,199 unsafe glyphs and retains the wrapping
penalty. Bounded semantic dependence does not imply isolated safe line-break
boundaries: the contextual matches overlap across the input. This disproves the
hope that limiting the hash radius alone would fix this layout workload. It
does not trace the browser's individual reshape calls.

With only expansion/hash/sweep enabled, window 2 wraps in 64–67 ms, window 4
in 123 ms, and window 8 in 278–350 ms. With the full pipeline active, the tone
feedback cost amplifies the slowdown. All full-pipeline one-line cases remain
around 16–24 ms.

Every seeder matches an independent expected-state calculation, including short
suffixes. Each full pipeline also shapes 40 runners into 12–15 distinct glyphs
and removes every private state glyph. Unaffected glyph/position signatures
and browser pixels match rules-off output. These are diagnostic fonts only;
the published font and its seeding policy are unchanged.

```sh
python web/benchmark_passes.py --site build/rear-cross-live \
  --upstream build/upstream-fonts --work build/pass-bounded \
  --config-set bounded --chromium /usr/bin/chromium --trials 3 \
  --output benchmarks/bounded.json
```

### Prefix-anchored entropy and backward feedback

[`prefix.json`](prefix.json) implements one prefix entropy sweep. After expansion,
an `ignore sub @any @source @tone'` guard marks only the first source's state.
Longest-first rules choose an anchor at source 16, 8, 4, 2 or 1. A reverse pass
collects entropy back from that anchor using distinct temporary state glyphs;
a final pass converts them to normal tone states. Downstream gender seeding,
forward feedback, folding and cleanup remain enabled. No recursive entropy is
collected after the anchor. The endpoint reuses a state slot rather than adding
an extra slot. All temporary glyphs are removed before the existing pipeline.

The independent proof checks lengths 1, 2, 3, 4, 7, 8, 15, 16, 17 and 24, including
anchor selection, expected prefix states, zero states beyond the prefix and
absence of temporary glyphs. Forty runners produce more than five distinct final
glyphs, with all private markers removed. Unaffected glyphs, positions and clusters
match rules-off output for lengths through 3,200.

COLRv1, 3,200 emoji, median forced layout time across three warmed trials:

| Configuration | Unaffected wrapped | Runners wrapped | Runners one line |
| --- | ---: | ---: | ---: |
| upstream | 1.9 ms | 1.2 ms | 1.2 ms |
| original, calt off | 1.4 ms | 1.3 ms | 1.1 ms |
| original, calt on | 770.2 ms | 1,078.2 ms | 19.4 ms |
| local seeds, full pipeline | 16.9 ms | 1,031.1 ms | 18.6 ms |
| prefix seeds, full pipeline | 922.4 ms | 1,065.6 ms | 20.1 ms |
| prefix seeds, expansion/hash/sweep only | 143.8 ms | 174.6 ms | 4.2 ms |

Two separate problems remain. First, backward feedback rules match actual runners
and mark 3,199 glyphs unsafe even without recursive hashing. On unaffected input
the same feedback rules fail eligibility checks and produce no such flags; the
earlier unaffected benchmark was not evidence that matched feedback was cheap to
wrap. Direction does not exempt a successful contextual match from break safety.

Second, the start guard itself introduces matches across every source boundary.
[`prefix-guard.json`](prefix-guard.json) isolates just the guard plus resetting
its temporary start marker, with no anchor or entropy collection. With expansion
and sweep only, this already marks 3,199 glyphs unsafe and wraps in 44–46 ms.
With the full downstream pipeline it takes 863 ms on unaffected input and 995 ms
on runners. HarfBuzz marks a successful ignore-context match unsafe even though
it suppresses substitution. Prefix-only collection therefore does not restrict
all contextual dependencies to the prefix in this implementation.

HarfBuzz diagnostics use 3,200 plain runners. Browser trials move one explicitly
male runner near the beginning of an otherwise unmodified 3,200-runner paragraph
to avoid reusing identical paragraph text. Unaffected trials vary their first
few glyphs using the existing benchmark payload. These measurements concern
layout, not rasterization, and do not trace individual browser reshaping calls.
The prefix font is diagnostic only; published assets remain unchanged.

```sh
python web/benchmark_prefix.py --site build/rear-cross-live \
  --upstream build/upstream-fonts --output benchmarks/prefix.json
python web/benchmark_prefix.py --site build/rear-cross-live \
  --upstream build/upstream-fonts --guard-only \
  --output benchmarks/prefix-guard.json
```

### Separate entropy blocks; continuous forward LFSRs

[`blocks.json`](blocks.json) uses `benchmark_prefix.py --blocks`. It consumes a
whole block of 16 expanded source units as lookup input, replacing the last tone
slot with an anchor. Short tails use longest-first blocks of 8, 4, 2 and 1.
Anchors are excluded from ordinary tone matching. This uses no start guard and
no overlapping lookahead windows. Reverse collection stops at each still
unprocessed anchor, starts the preceding block there, and finally converts all
temporary states back to ordinary tone states. The existing forward LFSRs remain
continuous across these blocks; they are not restarted at anchors.

COLRv1, 3,200 source glyphs, three warmed browser layout trials:

| Configuration | Unaffected wrapped | Runners wrapped | Runners one line |
| --- | ---: | ---: | ---: |
| upstream | 1.4 ms | 1.4 ms | 1.0 ms |
| original, calt off | 1.7 ms | 1.4 ms | 1.0 ms |
| original, calt on | 863.3 ms | 984.7 ms | 19.8 ms |
| local seeds, full pipeline | 25.5 ms | 935.6 ms | 19.1 ms |
| block seeds, full pipeline | 18.1 ms | 1,012.8 ms | 21.3 ms |
| block seeds, expansion/hash/sweep only | 2.9 ms | 2.8 ms | 2.5 ms |

Block seeding leaves 200 safe starts in 3,200 output glyphs: the other 3,000 are
unsafe within their blocks. A separate 64-source check confirms the safe positions
are exactly 0, 16, 32 and 48. Thus the seeding pass now provides genuinely separate
regions and avoids the paragraph-wide wrapping cost on unaffected text. Runner
feedback still connects all 3,199 boundaries in the full pipeline; it remains
unchanged for this experiment.

Independent state checks cover singleton, short-tail and multiple-block strings
through length 97. All temporary glyphs are removed, full-pipeline runners vary,
and unaffected glyph/position/cluster signatures equal rules-off output through
length 3,200. Font hashes and all timing samples are in the report. Browser runner
trials use the same early explicit-runner variation as the prefix benchmark to
avoid identical-text caching; direct HarfBuzz diagnostics use plain runners.
This remains a diagnostic implementation; the published font is unchanged.

```sh
python web/benchmark_prefix.py --site build/rear-cross-live \
  --upstream build/upstream-fonts --blocks --work build/pass-blocks \
  --output benchmarks/blocks.json
```

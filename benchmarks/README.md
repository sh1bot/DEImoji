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

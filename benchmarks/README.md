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

## Recorded run

See [`latest.json`](latest.json) for full precision and provenance. Times below are
local medians in milliseconds. Python eagerly decodes all layout tables;
HarfBuzz loads tables on demand. The two measurements describe different work.

| Font | Python layout decode | HB cold first shape | 36 runners | 3,200 runners |
| --- | ---: | ---: | ---: | ---: |
| upstream-cbdt | 32.214 | 0.416 | 0.005 | 0.246 |
| native-cbdt | 33.313 | 1.285 | 0.005 | 0.270 |
| deimoji-cbdt | 269.139 | 1.602 | 0.237 | 19.166 |
| upstream-colr | 45.094 | 0.145 | 0.005 | 0.246 |
| native-colr | 64.784 | 0.145 | 0.005 | 0.347 |
| deimoji-colr | 391.193 | 0.258 | 0.202 | 19.465 |

Shaping columns use `calt=1`. The JSON also records `calt=0`, long cluster runs,
mixed runs, explicit modifiers and plain-text diagnostics. Native-cache bitmap
files retain unoptimized PNGs, so cold blob-copy cost differs from the compressed
upstream release. No PNG decoding or colour painting is timed.

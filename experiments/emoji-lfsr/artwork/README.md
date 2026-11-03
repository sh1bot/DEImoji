# Noto ligature artwork

Four self-contained SVG assets, derived from Google Noto Emoji artwork in
https://github.com/sh1bot/DEImoji/tree/main/2D/svg (Apache License 2.0; see LICENSE).
Original source SVGs are included unchanged. Modified compositions were created
by arranging, scaling, rotating and overlapping the original vector paths;
The zombie pair uses the original woman and man designs; the trio adds the
original neutral zombie at the front. The man's four skin greens are shifted
slightly toward muted olive, preserving the original shading structure and
number of colors per figure. These are artwork colors, not Unicode skin-tone
modifier support. Gendered original SVGs are also included unchanged.

| Sequence | SVG | Canvas |
| --- | --- | --- |
| 🧟🧟 | emoji_u1f9df_1f9df.svg | 184 × 128 |
| 🧟🧟🧟 | emoji_u1f9df_1f9df_1f9df.svg | 240 × 128 |
| 🌻🌻 | emoji_u1f33b_1f33b.svg | 192 × 128 |
| 🌻🌻🌻 | emoji_u1f33b_1f33b_1f33b.svg | 252 × 128 |

All have transparent backgrounds, inline vector paths and gradients, distinct
IDs per figure, and no external image dependencies. PNGs are review previews.
Run `python build_hordes.py` to recreate all four SVGs.

These are source artwork assets, not an installed font change. Their widths
are intentionally compact relative to two/three separate emoji. Integration
must preserve aspect ratio and assign matching advance widths in the font.
Put three-item ligatures before two-item ligatures when constructing GSUB.

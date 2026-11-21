# Fixed decorative clusters

Noto-derived pairs and trios for 🪦, 🎆, 🎉, 🔥 and 💰. Headstones mix arched, rounded and bevelled stones with a Celtic
cross (ring plus cross), behind in the pair and in front in the trio, with shuffled
inscriptions and a smaller rear row. Fireworks use five distinct explosions across the pair and trio: gold ignition,
pink full bloom, cyan opening, green willow trails and coral fading embers,
with different heights and ray layouts. Poppers vary paper colours/positions and
reverse the middle cone; each of the five poppers has a distinct permutation
of three streamer shapes across the same outward-facing slots. Cone stripes
and shading are unchanged. The middle flame also curls the opposite way. The native singleton is
unchanged. These families share binary history with every other cluster family, using
alternating startup and the period-31 binary LFSR to mix pairs and trios,
with one fixed artwork choice for each size. The diversity generators do not
select extra variants.

Moneybags use the original Noto gold bag and dollar sign, staggered and slightly
rotated into overlapping pairs/trios. The trio has a smaller raised rear bag.
Two bags face the other way, with readable unreflected dollar signs and neck/
side-fold shadows kept on the right under the same upper-left lighting.
They share the period-31 grouping history, with one artwork per size and no
additional diversity variants. Adjacent moneybag clusters use 18% em negative
kerning; singleton artwork and singleton–singleton spacing stay unchanged.

The source SVGs are pinned in `clusters/source/` (see `clusters/manifest.json` for the commit).
`clusters/svg/` contains editable compositions; `clusters/png/128/` and `clusters/Clusters-COLRv1.ttf`
are installed into cached native fonts. The mini font's output glyphs are
unencoded. `clusters/preview.png` shows all ten isolated compositions.

Fireworks use one rounded background for the pair and one for the trio.
Both have the same vertical sky gradient and no side tint. Their painted spark
bounds are cropped to the clear overlap strip, with a small antialiasing
allowance; burst positions are preserved relative to one another at 87.5% scale.
The 128px bitmap canvases are 180px and 255px wide, within the CBDT width limit.
GPOS tightens adjacent firework clusters by 217/1024 em (about 23.14 source
pixels). This hides the interior corner rounding while keeping every spark
outside the overlapping background region. Rasterizers may still differ in
antialiasing or bitmap-resampling edge pixels. Isolated clusters retain rounded
outer corners. Singleton artwork and singleton–singleton spacing are unchanged.

No start/middle/end glyphs or contextual background joining lookups are used.
The normal full-length RTL seed collection remains enabled; this artwork change
does not use experimental entropy anchors or LFSR fences.

Regenerate with Inkscape, nanoemoji and ninja installed:

```sh
python ligatures/supplemental/build_clusters.py
```

Noto artwork retains its upstream Apache 2.0 license. The clusters directory is outside
the native-artwork cache inputs, so editing these clusters does not recompile
the entire emoji collection.

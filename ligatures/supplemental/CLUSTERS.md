# Fixed decorative clusters

Noto-derived pairs and trios for 🪦, 🎆, 🎉 and 🔥. Headstones mix arched, rounded and bevelled stones with a Celtic
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

The source SVGs are pinned in `clusters/source/` (see `clusters/manifest.json` for the commit).
`clusters/svg/` contains editable compositions; `clusters/png/128/` and `clusters/Clusters-COLRv1.ttf`
are installed into cached native fonts. The mini font's output glyphs are
unencoded. `clusters/preview.png` shows all eight isolated compositions.

Fireworks additionally have start, middle and end backgrounds for each size.
Two contextual lookups run after modifier assembly: a left neighbour selects an
end, then a right neighbour selects a start or turns an end into a middle.
Only adjacent firework clusters join; isolated clusters and native singletons
keep their normal rendering. Interior edges are square and untinted; only outer
edges have rounded corners and edge tint. All versions share the same vertical
sky gradient. GPOS tightens firework cluster boundaries by 79/1024 em, overlapping
the matching sky slightly to cover raster edge antialiasing. Singleton–singleton
spacing is unchanged. Both CBDT and COLRv1 include these six additional glyphs.

The normal full-length RTL seed collection remains enabled. These joining rules
run after it and do not use the experimental entropy anchors or LFSR fences.

Regenerate with Inkscape, nanoemoji and ninja installed:

```sh
python ligatures/supplemental/build_clusters.py
```

Noto artwork retains its upstream Apache 2.0 license. The clusters directory is outside
the native-artwork cache inputs, so editing these clusters does not recompile
the entire emoji collection.

# Fixed decorative clusters

Noto-derived pairs and trios for 🪦, 🎆, 🎉 and 🔥. Headstones mix arched, rounded and bevelled stones with a foreground Celtic
cross (ring plus cross), with shuffled
inscriptions and a smaller rear row. Fireworks share one sky and show opening,
full-bloom and falling-spark stages. Poppers vary paper colours/positions and
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
unencoded. `clusters/preview.png` shows all eight compositions.

Regenerate with Inkscape, nanoemoji and ninja installed:

```sh
python ligatures/supplemental/build_clusters.py
```

Noto artwork retains its upstream Apache 2.0 license. The clusters directory is outside
the native-artwork cache inputs, so editing these clusters does not recompile
the entire emoji collection.

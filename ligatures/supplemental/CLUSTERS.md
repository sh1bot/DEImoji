# Fixed decorative clusters

Noto-derived pairs and trios for 🪦, 🎆, 🎉 and 🔥. Headstones mix three crown
profiles; fireworks use one shared panoramic sky. The native singleton is
unchanged. These families use fixed grouping rather than an LFSR.

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

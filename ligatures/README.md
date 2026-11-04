# Zombie hordes, sunflower clusters and poop heaps

Repeated plain 🧟, 🌻 or 💩 are grouped into two- and three-item artwork.
The original artwork is in `svg/`; the approved poop heaps and their sources
are in `supplemental/poop/`. The regular CBDT, Windows-compatible CBDT, and COLRv1 builds install
the contextual rules from `cluster_ligatures.py`. The poop artwork is appended
to compiled native fonts as a small vector/bitmap bundle. Gendered zombies and other modified
sequences are outside the matching policy for now.

## Grouping and feedback

The default-enabled `calt` feature advances left to right. Previous output
clusters carry the state: a pair is bit 0 and a triple is bit 1. The next bit
is the XOR of the oldest and next-oldest of the preceding four clusters.
The first four free choices seed with 1. Coefficients are `0,0,1,1`, newest first.
This gives a maximal period of fifteen **clusters**, consuming 38 input emoji
per complete cycle:

```
3 3 3 3 2 2 2 3 2 2 3 3 2 3 2 | ...
```

At least five remaining inputs allow either choice without leaving a singleton.
Four force 2+2; three force a triple; two force a pair. Therefore tail choices
can deviate from the cycle. A single emoji stays unchanged. A change of family
or another glyph breaks the feedback history, as does a shaping-run boundary.
The sequence is deterministic, not random on every redraw.

Native emoji assembly runs first in `ccmp`; the installer removes only the six
greedy repeated-base ligatures and installs their contextual replacements in
`calt`. The nested pair/triple lookups are called only by the contextual lookup.
Disabling `calt` leaves the individual emoji. Existing GSUB lookups, GPOS, GDEF,
and script/language feature references are preserved.

The bitmap installer runs **after** image embedding: the existing bitmap builder
needs the original unconditional ligatures to resolve image filenames. The
COLRv1 installer runs at the end of the normal post-processing stage.

## Build

Follow the repository's normal build setup, then build with `make` for CBDT.
The four baseline PNGs are 128px high and retain their full SVG widths;
the Makefile copies these without its ordinary 136px-wide crop. Only these
intentional custom sequences are excluded from the Unicode RGI filename
check; ordinary emoji sequences are still checked.

For COLRv1, run `python colrv1_generate_configs.py`, compile the generated
configs with nanoemoji, and run `python colrv1_postproc.py`, as described in
`BUILD.md`. Both the all-emoji and no-flags configs include these assets.
Build paths refer to the repository's current `2D/` source/font directories.

`supplemental_artwork.py` appends the two poop bitmaps directly to CBDT, and
merges the precompiled small COLRv1 bundle's outlines, paints and palette colors.
Existing glyph IDs and compressed native bitmaps are preserved. The pack stays
outside the native cache inputs, so adding or revising these heaps does not
recompile unrelated Noto artwork. The normal cluster installer invokes it.
Packaging records the restoration metadata in public `build.json`; cache recovery
removes modifier rules, cluster rules, and supplemental artwork in that order.
Both the previous two-family bundles and current three-family bundles can be
recovered, without storing a custom table in released fonts.

To revise the artwork:

```
python experiments/emoji-lfsr/artwork/build_hordes.py
python ligatures/build_assets.py  # requires Inkscape
```

To regenerate the poop pack from its approved transparent concept:

```
python ligatures/supplemental/build_poop.py
```

This development command requires Pillow, vtracer, Inkscape and nanoemoji on
the active environment's paths. It writes the SVGs, 128px PNGs, small compiled
COLRv1 font and checksummed manifest. Normal builds verify and install those
checked-in outputs using fontTools; they do not run image tracing. Both heaps
share a consistent artwork scale and baseline. The trio's center is raised
behind the outer faces and has the reversed swirl approved in the concept.

To test the grouping with actual HarfBuzz shaping:

```
python -m unittest discover -s tests -p test_cluster_ligatures.py -v
```

Requires fontTools and the system HarfBuzz shared library (`libharfbuzz0b` on
Ubuntu). Tests cover all three families, lengths 0–100 and 1000, run boundaries,
the period-fifteen prefix, modified zombie sequences, disabling `calt`, retained
positioning/ligatures, and a binary/TTX round trip.

Artwork derives from Google Noto Emoji under Apache-2.0; see `LICENSE` and
the source provenance embedded in each SVG. The original editable compositions
and preview PNGs remain under `experiments/emoji-lfsr/artwork/`.
The poop pack's original generated/approved concepts are checked in alongside
the derived assets under the same Apache-2.0 license. The unmodified Noto poop
SVG is retained as a build reference; its normal base glyph remains unchanged.

Adjacent singles, pairs and triples of the same family receive negative kerning
of 4% of an em. This gently overlaps their edges without changing spacing next
to text or other emoji. It is installed as a separate `kern` GPOS feature on
the native Noto fonts (which have no existing GPOS), and removed during cache
recovery. Existing positioning tables in other input fonts are retained.

The poop heaps were generated from the approved concepts, then vectorised;
they are not direct arrangements of the Noto singleton SVG. Their softer shading
and facial proportions therefore differ from the unchanged Noto singleton.

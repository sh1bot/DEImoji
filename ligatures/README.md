# Zombie hordes and sunflower clusters

Repeated plain 🧟 or 🌻 are grouped into the two- and three-item artwork in
`svg/`. The regular CBDT, Windows-compatible CBDT, and COLRv1 builds install
the contextual rules from `cluster_ligatures.py`. Existing compiled fonts must
be rebuilt to acquire the artwork. Gendered zombies and other modified
sequences are outside the matching policy for now.

## Grouping and feedback

The default-enabled `calt` feature advances left to right. Previous output
clusters carry the state: a pair is bit 0 and a triple is bit 1. The next bit
is the XOR of the oldest and newest of the preceding three clusters. The
first three free choices seed with 1. This gives a maximal period of seven
**clusters**, consuming 18 input emoji per complete cycle:

```
3 3 3 2 3 2 2 | 3 3 3 2 3 2 2 | ...
```

At least five remaining inputs allow either choice without leaving a singleton.
Four force 2+2; three force a triple; two force a pair. Therefore tail choices
can deviate from the cycle. A single emoji stays unchanged. A change of family
or another glyph breaks the feedback history, as does a shaping-run boundary.
The sequence is deterministic, not random on every redraw.

Native emoji assembly runs first in `ccmp`; the installer removes only the four
greedy repeated-base ligatures and installs their contextual replacements in
`calt`. The nested pair/triple lookups are called only by the contextual lookup.
Disabling `calt` leaves the individual emoji. Existing GSUB lookups, GPOS, GDEF,
and script/language feature references are preserved.

The bitmap installer runs **after** image embedding: the existing bitmap builder
needs the original unconditional ligatures to resolve image filenames. The
COLRv1 installer runs at the end of the normal post-processing stage.

## Build

Follow the repository's normal build setup, then build with `make` for CBDT.
The four checked-in PNGs are 128px high and retain their full SVG widths;
the Makefile copies these without its ordinary 136px-wide crop. Only these
four intentional custom sequences are excluded from the Unicode RGI filename
check; ordinary emoji sequences are still checked.

For COLRv1, run `python colrv1_generate_configs.py`, compile the generated
configs with nanoemoji, and run `python colrv1_postproc.py`, as described in
`BUILD.md`. Both the all-emoji and no-flags configs include these assets.
Build paths refer to the repository's current `2D/` source/font directories.

To revise the artwork:

```
python experiments/emoji-lfsr/artwork/build_hordes.py
python ligatures/build_assets.py  # requires Inkscape
```

To test the grouping with actual HarfBuzz shaping:

```
python -m unittest discover -s tests -p test_cluster_ligatures.py -v
```

Requires fontTools and the system HarfBuzz shared library (`libharfbuzz0b` on
Ubuntu). Tests cover both families, lengths 0–100 and 1000, run boundaries,
the period-seven prefix, modified zombie sequences, disabling `calt`, retained
positioning/ligatures, and a binary/TTX round trip.

Artwork derives from Google Noto Emoji under Apache-2.0; see `LICENSE` and
the source provenance embedded in each SVG. The original editable compositions
and preview PNGs remain under `experiments/emoji-lfsr/artwork/`.

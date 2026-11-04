# Five zombie pairs and five trios

These are direct SVG compositions of Google Noto Emoji artwork, Apache-2.0,
pinned at commit `30649a050403b9f4d05f8502d761ecb55c6838b9` in this fork.
The `source/` directory retains the zombie, hairstyle and occupation originals.
No image generation or bitmap tracing is used.

The ten compositions contain 25 distinct deterministic character recipes.
Exactly five characters wear hats: two of the ten pair members and three of
the fifteen trio members, so headwear stays at 20% for either group size.
The recipes mix:
neutral/woman/man zombie bases; original, ginger, white and curly hair; police,
construction, chef, graduation and firefighter headwear; five muted green/grey
skin palettes suggesting different decay; and varied shirt colours. Recipes
are stored in `manifest.json`. These are decorative custom variants, not new
Unicode modifier support. The single zombie and native explicit gender forms
remain unchanged.

`svg/zombie{2,3}_v{0..4}.svg` are editable vectors. Corresponding 128px-high
PNGs are 184px or 240px wide. `Zombies-COLRv1.ttf` contains the same ten unencoded
artwork glyphs plus shared outline components. No Private Use Area codepoint is
used, even in the mini font. `preview.png` shows the source artwork.

Regenerate with Inkscape, nanoemoji and ninja installed:

```
python ligatures/supplemental/build_zombies.py
```

The build script creates a temporary custom glyphmap module so nanoemoji leaves
the ten glyphs unencoded. The committed pack has checksums and needs no SVG
compiler during normal font builds.

`zombie_artwork.py` appends this pack after native artwork is loaded from cache.
It records each original cluster's five choices in the private, normally
inactive `DVAR` alternate feature. The ordinary `calt` installer reads those
choices into its generic five-state mapping. Binary grouping completes first;
then each output cluster advances the same base-5 generator used for other
eligible emoji. Base-3 state advances too, but is ignored for these compositions.
Cleanup removes all state glyphs before final assembly. Custom kerning includes
all ten outputs, while singleton-to-singleton spacing stays native.

The packaged-font tests check grouping and variation for 4,000 zombies in each
TTF and the WOFF2, compare all ten embedded bitmap PNGs with their source files,
and paint every private glyph in Chromium. The proof font used by the browser
test exists only in memory: its temporary ASCII cmap is never published. Only
`zombie-proof-colr.png` and `zombie-proof-cbdt.png` are published as galleries.
They show the actual final font artwork and are linked from the test page.

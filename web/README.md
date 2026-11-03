# Automated builds and browser playground

On a cold cache, `.github/workflows/build-fonts.yml` builds the regular and Windows-compatible
bitmap fonts, builds and post-processes both COLRv1 variants, and packages a
static test page with matching COLRv1 TTF/WOFF2 and CBDT TTF downloads.

- Runs on pushes to `main`, pull requests, or a manual **Run workflow**.
- Keeps the test page and fonts together as a downloadable Actions artifact
  named `DEImoji-<commit>`, retained for 30 days.
- Successful builds on `main` deploy the page and fonts to GitHub Pages.
- Pull requests build artifacts but do not deploy.
- Build metadata and font URL cache keys identify the exact commit being shown.

The browser build uses every available CPU core and `OPTIMIZE_PNGS=0` to
embed the source PNG pixels without PNGQuant/Zopfli optimization. This makes
the bitmap download larger but preserves the source artwork and gives quicker
preview builds. A normal local `make` retains the upstream compression defaults.

## Persistent compiled-artwork cache

The workflow caches the native CBDT and COLRv1 fonts **before** the custom GSUB
patch. The cache key covers artwork, native build scripts/options, and compiler
versions. Changes to `cluster_ligatures.py` or the web UI reuse those compiled
fonts; the current GSUB rules are reapplied, then packaging and browser tests
run normally. Changes to native artwork/build inputs trigger compilation.

GitHub Actions caches persist between runs but can be evicted. If a matching
build is still published on Pages, the workflow downloads its font pair and
recovers the native lookups to reseed the cache. Published font checksums and
the native input key prevent mixing builds. The first pre-cache preview has a
strict one-time migration path tied to its known source commit.

Cache files and checksums live in `build/native-fonts/`, separately from the
font downloads. No cache-only data is inserted into the release fonts. The
small `build.json` file on the test page identifies the build and its inputs.
The workflow's “Restore compiled artwork cache” and conditional build steps
show whether a run reused artwork or compiled it.

Runs on the same branch are serialized so a cold build can finish seeding its
cache. A completed older commit cannot replace the latest commit's Pages site.

## One-time hosting setup

In repository **Settings → Pages → Build and deployment**, choose **GitHub
Actions** as the source. No custom domain or application server is needed.
The expected public address is https://sh1bot.github.io/DEImoji/.
If Pages is not enabled, the build artifact is still uploaded before the
separate deployment job runs. Check the Actions run for errors and downloads.

The current published page remains available while a newer build is running;
the build identifier on the page distinguishes it from the latest source commit.
No prebuilt production font is committed by this workflow.

## Local preview

After building the fonts into `2D/fonts/`:

```
python -m pip install 'fonttools[woff]'
python web/package.py --output build/site
python -m http.server --directory build/site 8000
```

Open http://localhost:8000/. Use an HTTP server rather than opening the HTML
directly: the page fetches its build metadata and loads font files.
The controls change the sample family, run length, size, font format, or custom
input. Both output panels use the built font, differing only in `calt` settings.
Failed font loads hide the output rather than silently displaying system emoji.

The build also runs `web/check_browser.py` with Chromium against the packaged
fonts: both families and formats must render differently with `calt` enabled,
controls must update the input, mobile layout must stay within the viewport,
and failed font loads must be reported. To run locally, install Playwright and
Chromium and run `python web/check_browser.py build/site`.

The packaged font license is at `fonts/LICENSE.txt`.

"""Smoke-test the packaged page against its actual fonts in Chromium.

Run: python web/check_browser.py build/site [--chromium /usr/bin/chromium]
Requires playwright and its Chromium browser (playwright install chromium).
"""
import argparse
import json
from datetime import datetime, timezone

from check_font_package import check_font_package, zombie_proof_font
from io import BytesIO
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright
from PIL import Image


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('site', type=Path)
    parser.add_argument('--chromium', default=None)
    args = parser.parse_args()
    report = check_font_package(args.site)
    server = ThreadingHTTPServer(('127.0.0.1', 0),
                                partial(QuietHandler, directory=str(args.site.resolve())))
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=args.chromium, headless=True)
            page = browser.new_page(viewport={'width': 1200, 'height': 1000})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(f'http://127.0.0.1:{server.server_port}/', wait_until='networkidle')
            loaded = "document.getElementById('status').textContent.startsWith('Built font loaded')"
            page.wait_for_function(loaded)
            assert 'white-smile artwork' in page.locator('#build-details').inner_text()
            assert 'reverse sweep' in page.locator('#build-details').inner_text()
            for family in ('🧟', '🌻', '💩'):
                page.locator('#text').fill(family * 4)
                for fmt in ('colr', 'cbdt'):
                    page.select_option('#format', fmt)
                    page.wait_for_function(loaded)
                    on, off = page.evaluate('''() => ['clustered', 'individual'].map(id => {
                        const range = document.createRange();
                        range.selectNodeContents(document.getElementById(id));
                        return range.getBoundingClientRect().width;
                    })''')
                    assert on < off, (family, fmt, on, off)
                    single_delta = page.locator('#individual .emoji-run').evaluate("""node => {
                        const before = node.getBoundingClientRect().width;
                        const original = node.style.fontFeatureSettings;
                        node.style.fontFeatureSettings = "'calt' 0, 'kern' 0";
                        const after = node.getBoundingClientRect().width;
                        node.style.fontFeatureSettings = original;
                        return after - before;
                    }""")
                    assert abs(single_delta) < .01, (family, fmt, single_delta)
                    overlap = page.locator('#clustered .emoji-run').evaluate("""node => {
                        const before = node.getBoundingClientRect().width;
                        const original = node.style.fontFeatureSettings;
                        node.style.fontFeatureSettings = "'calt' 1, 'kern' 0";
                        const after = node.getBoundingClientRect().width;
                        node.style.fontFeatureSettings = original;
                        return [after - before, parseFloat(getComputedStyle(node).fontSize)];
                    }""")
                    # Chromium versions differ in fractional glyph-advance rounding.
                    assert abs(overlap[0] - overlap[1] * {'🧟': .22, '🌻': .35, '💩': .04}[family]) < .6, (family, fmt, overlap)
                    if family == '💩':
                        for n in (2, 3):
                            page.locator('#text').fill('💩' * n)
                            assert page.locator('#clustered .emoji-run').count() == 1
                            pixels = Image.open(BytesIO(page.locator(
                                '#clustered .emoji-run').screenshot())).convert('RGB')
                            brown = sum(40 < r < 220 and 15 < g < 180 and b < 150
                                        and r > g * 1.25 and g > b * 1.15
                                        for r, g, b in pixels.getdata())
                            assert brown > 100, ('missing poop artwork', fmt, n, brown)
                            pink = sum(r > 120 and r > g * 1.25 and b > g * 1.05 and b > 60
                                       for r, g, b in pixels.getdata())
                            assert pink < 2, ('old pink-tongue poop artwork', fmt, n, pink)
                        page.locator('#text').fill(family * 4)
            # Paint all private crowd glyphs, not just whichever the demo's
            # current seed happens to select. Probe cmaps exist only in memory.
            for fmt in ('colr', 'cbdt'):
                proof = zombie_proof_font(args.site, fmt)
                page.evaluate("""async ({url, fmt}) => {
                    const face = new FontFace('ZombieProof'+fmt, `url("${url}")`);
                    await face.load();document.fonts.add(face);
                    const box = document.createElement('div');box.id='zombie-proof';
                    Object.assign(box.style, {position:'absolute',left:'0',top:'0',
                        display:'grid',gridTemplateColumns:'repeat(5, max-content)',
                        gap:'10px',background:'white',padding:'12px',zIndex:'1000',
                        fontFamily:'ZombieProof'+fmt,fontSize:'96px',lineHeight:'1.5'});
                    for(let i=0;i<10;i++) {
                        const span=document.createElement('span');span.textContent=String.fromCharCode(65+i);
                        box.append(span);
                    }
                    document.body.append(box);
                }""", dict(url=proof,fmt=fmt))
                pictures=[]
                for span in page.locator('#zombie-proof span').all():
                    data=span.screenshot();pictures.append(data)
                    pixels=Image.open(BytesIO(data)).convert('RGB')
                    green=sum(g>r*1.02 and g>b*1.1 for r,g,b in pixels.getdata())
                    assert green>100, ('missing zombie artwork',fmt,green)
                assert len(set(pictures[:5]))==5 and len(set(pictures[5:]))==5, ('duplicate zombie art',fmt)
                page.locator('#zombie-proof').screenshot(path=str(args.site/f'zombie-proof-{fmt}.png'))
                page.locator('#zombie-proof').evaluate('node => node.remove()')
            page.select_option('#preset', 'poop')
            assert page.locator('#text').input_value() == '💩' * 36
            page.select_option('#preset', 'old')
            assert page.locator('#text').input_value() == '🧓' * 36
            page.select_option('#preset', 'runners')
            assert page.locator('#text').input_value() == '🏃' * 36
            for fmt in ('colr', 'cbdt'):
                page.select_option('#format', fmt)
                page.wait_for_function(loaded)
                for text, should_differ in (('🏃' * 8, True), ('🧑' * 8, True),
                                            ('🏃', True), ('🧑', True), ('🧓' * 8, True),
                                            ('👵🏻👴🏿', False),
                                            ('🏃🏽‍♀️🏃🏻‍♂️🏃🏿', False)):
                    page.locator('#text').fill(text)
                    # Capture the same element at the same position/background;
                    # width cannot establish whether tone/gender artwork changed.
                    sample = page.locator('#clustered .emoji-run')
                    on = sample.screenshot()
                    page.locator('#clustered').evaluate(
                        "node => node.style.fontFeatureSettings = \"'calt' 0\"")
                    off = sample.screenshot()
                    page.locator('#clustered').evaluate(
                        "node => node.style.fontFeatureSettings = ''")
                    assert (on != off) == should_differ, (fmt, text)
            page.select_option('#preset', 'flowers')
            assert page.locator('#text').input_value() == '🌻' * 36
            page.locator('#count').fill('18')
            page.locator('#count').dispatch_event('input')
            assert page.locator('#text').input_value() == '🌻' * 18
            page.locator('#text').fill('hello 🧟🧟🧟 world 123 #️⃣')
            assert page.locator('#clustered').inner_text() == 'hello 🧟🧟🧟 world 123 #️⃣'
            assert 'system-ui' in page.locator('#clustered').evaluate(
                'node => getComputedStyle(node).fontFamily')
            page.locator('#text').fill('🧟' * 36)
            assert page.locator('#clustered .emoji-run').count() == 1
            page.locator('#text').fill('abc 🧟\u200d♀\ufe0f xyz')
            debug = page.locator('#codepoints').inner_text()
            assert '"abc "' in debug and '" xyz"' in debug
            assert '200D(ZWJ)' in debug and 'FE0F(VS16 (emoji))' in debug
            assert '0061(' not in debug
            page.set_viewport_size({'width': 390, 'height': 844})
            assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
            # Force an uncached font load failure and ensure it is visible.
            page.route('**/fonts/*', lambda route: route.abort())
            page.evaluate("metadata.commit = 'missing-font-test'")
            page.select_option('#format', 'colr')
            page.wait_for_function("document.getElementById('status').classList.contains('error')")
            assert page.locator('#clustered').evaluate(
                "node => getComputedStyle(node).visibility") == 'hidden'
            assert not errors, errors
            browser.close()
        report.update(browser='Chromium', browser_checks='passed',
                      poop_white_smile_artwork='passed',
                      zombie_artwork_glyphs_painted_per_format=10,
                      checked_at=datetime.now(timezone.utc).isoformat())
        (args.site / 'checks.json').write_text(json.dumps(report, indent=2) + '\n')
        print('PASS: clusters and runner pixels in both formats, calt on/off, controls, mobile, font errors')
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()

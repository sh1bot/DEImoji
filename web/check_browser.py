"""Smoke-test the packaged page against its actual fonts in Chromium.

Run: python web/check_browser.py build/site [--chromium /usr/bin/chromium]
Requires playwright and its Chromium browser (playwright install chromium).
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from playwright.sync_api import sync_playwright


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('site', type=Path)
    parser.add_argument('--chromium', default=None)
    args = parser.parse_args()
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
            for family in ('🧟', '🌻'):
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
            page.select_option('#preset', 'runners')
            assert page.locator('#text').input_value() == '🏃' * 36
            for fmt in ('colr', 'cbdt'):
                page.select_option('#format', fmt)
                page.wait_for_function(loaded)
                for text, should_differ in (('🏃' * 8, True), ('🏃🏽‍♀️🏃🏻‍♂️🏃🏿', False)):
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
            assert 'U+200D (ZWJ)' in debug and 'U+FE0F (VS16 (emoji))' in debug
            assert 'U+0061' not in debug
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
        print('PASS: clusters and runner pixels in both formats, calt on/off, controls, mobile, font errors')
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()

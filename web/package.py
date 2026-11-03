"""Package a static test page with the fonts from the same build."""
import argparse
import hashlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil

from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]


def package(output, source):
    output.mkdir(parents=True, exist_ok=True)
    fonts = output / 'fonts'
    fonts.mkdir(exist_ok=True)
    for name in ('index.html', 'style.css', 'app.js'):
        shutil.copyfile(ROOT / 'web' / name, output / name)
    for src, dest in [('Noto-COLRv1.ttf', 'DEImoji-COLRv1.ttf'),
                      ('NotoColorEmoji.ttf', 'DEImoji-CBDT.ttf')]:
        shutil.copyfile(source / src, fonts / dest)
    shutil.copyfile(ROOT / '2D/fonts/LICENSE', fonts / 'LICENSE.txt')
    # Webfont and TTF contain the same glyphs and OpenType lookups.
    font = TTFont(source / 'Noto-COLRv1.ttf')
    font.flavor = 'woff2'
    font.save(fonts / 'DEImoji-COLRv1.woff2')
    metadata = {
        'commit': os.environ.get('GITHUB_SHA', 'local'),
        'repository': os.environ.get('GITHUB_REPOSITORY', 'sh1bot/DEImoji'),
        'built_at': datetime.now(timezone.utc).isoformat(),
        'native_key': os.environ.get('DEIMOJI_NATIVE_KEY'),
        'modifiers': json.loads((ROOT / 'build/modifiers.json').read_text())
                     if (ROOT / 'build/modifiers.json').exists() else {},
        'font_hashes': {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in fonts.glob('*') if p.suffix in ('.ttf', '.woff2')},
    }
    (output / 'build.json').write_text(json.dumps(metadata, indent=2) + '\n')
    (output / '.nojekyll').touch()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'build/site')
    parser.add_argument('--fonts', type=Path, default=ROOT / '2D/fonts')
    args = parser.parse_args()
    package(args.output, args.fonts)

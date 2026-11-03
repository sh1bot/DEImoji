"""Cache native artwork fonts separately from the editable cluster GSUB rules."""
import argparse
import ctypes
import ctypes.util
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cluster_ligatures import add_cluster_ligatures, remove_cluster_ligatures
from modifier_ligatures import remove_modifier_ligatures
from fontTools.ttLib import TTFont, TTLibError

CACHE = ROOT / 'build/native-fonts'
FONTS = {'NotoColorEmoji.ttf': 'DEImoji-CBDT.ttf',
         'Noto-COLRv1.ttf': 'DEImoji-COLRv1.ttf'}
# cluster_ligatures.py and web/UI code are intentionally excluded. The cached
# fonts precede that GSUB patch, so those edits do not require new artwork.
INPUTS = ['2D/svg', '2D/png/128', 'third_party', 'ligatures/svg', 'ligatures/png',
          'Makefile', 'requirements.txt', 'NotoColorEmoji.tmpl.ttx.tmpl',
          'add_glyphs.py', 'add_emoji_gsub.py', 'add_aliases.py', 'emoji_aliases.txt',
          'unknown_flag_aliases.txt', 'map_pua_emoji.py', 'flag_glyph_name.py',
          'flag_info.py', 'waveflag.c', 'colrv1_generate_configs.py',
          'colrv1_postproc.py', 'colrv1_add_soft_light_to_flags.py',
          '.github/workflows/build-fonts.yml']
LEGACY_PREVIEW = '5abd9437c08a6f53b4fc8990039c8b7d821974c7'


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True)


def compiler_info():
    versions = {name: version(name) for name in (
        'fonttools', 'nanoemoji', 'notofonttools', 'picosvg', 'ufo2ft',
        'ufoLib2', 'fontmath', 'skia-pathops')}
    cairo = ctypes.CDLL(ctypes.util.find_library('cairo') or 'libcairo.so.2')
    cairo.cairo_version_string.restype = ctypes.c_char_p
    return {
        'compilers': versions,
        'python': sys.version.split()[0],
        'cairo': cairo.cairo_version_string().decode(),
        'imagemagick': subprocess.check_output(['convert', '-version'], text=True).splitlines()[0],
    }


def cache_key():
    payload = {
        'schema': 'native-font-v1-direct-png',
        'tree': git('ls-tree', '-r', 'HEAD', '--', *INPUTS),
        'environment': compiler_info(),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    return 'deimoji-native-v1-' + digest


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stamp(key):
    for name in FONTS:
        font = TTFont(CACHE / name)
        expected = 'CBDT' if name == 'NotoColorEmoji.ttf' else 'COLR'
        if expected not in font:
            raise ValueError(f'{name} is missing {expected}')
        if any(r.FeatureTag == 'calt' for r in font['GSUB'].table.FeatureList.FeatureRecord):
            raise ValueError('Native cache must precede the custom calt feature')
    metadata = {'key': key, 'hashes': {name: digest(CACHE / name) for name in FONTS}}
    (CACHE / 'cache.json').write_text(json.dumps(metadata, indent=2) + '\n')


def verify(key):
    try:
        metadata = json.loads((CACHE / 'cache.json').read_text())
        return metadata['key'] == key and all(
            digest(CACHE / name) == metadata['hashes'][name] for name in FONTS)
    except (OSError, ValueError, KeyError):
        return False


def fetch(url):
    request = urllib.request.Request(url, headers={'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


def bootstrap(key):
    """Reseed an evicted Actions cache from the matching published font pair."""
    repository = os.environ.get('GITHUB_REPOSITORY', 'sh1bot/DEImoji')
    owner, repo = repository.split('/')
    base = f'https://{owner}.github.io/{repo}/'
    try:
        metadata = json.loads(fetch(base + 'build.json'))
        commit = metadata['commit']
        if metadata.get('native_key') != key:
            # One-time migration of the first preview, which predates the cache
            # manifest. Only the reviewed cache/export wrappers may differ.
            if commit != LEGACY_PREVIEW or metadata.get('native_key'):
                raise ValueError('Published font uses different native build inputs')
            subprocess.run(['git', 'fetch', '--depth=1', 'origin', commit], cwd=ROOT, check=True,
                           stdout=sys.stderr, stderr=sys.stderr)
            changed = set(git('diff', '--name-only', commit, 'HEAD', '--', *INPUTS).splitlines())
            allowed = {'Makefile', 'colrv1_postproc.py', '.github/workflows/build-fonts.yml'}
            if changed - allowed:
                raise ValueError('Published preview artwork/build sources differ')
        CACHE.mkdir(parents=True, exist_ok=True)
        for native, published in FONTS.items():
            data = fetch(base + f'fonts/{published}?build={commit}')
            expected = metadata.get('font_hashes', {}).get(published)
            if expected and hashlib.sha256(data).hexdigest() != expected:
                raise ValueError('Published deployment changed during download')
            target = CACHE / native
            target.write_bytes(data)
            font = TTFont(target)
            remove_modifier_ligatures(font, metadata.get('modifiers', {}).get(published))
            remove_cluster_ligatures(font)
            font.save(target)
        stamp(key)
        print('Recovered native fonts from the matching published build', file=sys.stderr)
        return True
    except OSError as error:
        print(f'Published font pair is not available yet: {error}', file=sys.stderr)
        return None
    except (ValueError, KeyError, TTLibError, subprocess.CalledProcessError) as error:
        print(f'No reusable published font cache: {error}', file=sys.stderr)
        return False


def ready(key, wait=0):
    if verify(key):
        return True
    deadline = time.monotonic() + max(0, wait)
    while True:
        result = bootstrap(key)
        if result is not None:
            return result
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        print('Waiting briefly for a matching published font pair before rebuilding', file=sys.stderr)
        time.sleep(min(30, remaining))


def apply(key):
    if not verify(key):
        raise ValueError('Native cache key or font checksums do not match')
    output = ROOT / '2D/fonts'
    output.mkdir(parents=True, exist_ok=True)
    modifiers = {}
    for name, published in FONTS.items():
        font = TTFont(CACHE / name)
        modifiers[published] = add_cluster_ligatures(font)
        font.save(output / name)
    manifest = ROOT / 'build/modifiers.json'
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(modifiers, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('key', 'ready', 'stamp', 'apply'))
    parser.add_argument('--key')
    parser.add_argument('--wait-for-published', type=int, default=0)
    args = parser.parse_args()
    if args.operation == 'key':
        print(cache_key())
    elif not args.key:
        parser.error('--key is required')
    elif args.operation == 'ready':
        print('ready=' + str(ready(args.key, args.wait_for_published)).lower())
    elif args.operation == 'stamp':
        stamp(args.key)
    else:
        apply(args.key)

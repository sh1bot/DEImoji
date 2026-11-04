"""Copy approved experimental SVGs and rasterize 128px-high bitmap sources.

Run from any directory: python ligatures/build_assets.py
Requires Inkscape on PATH. Does not change ordinary Noto artwork.
"""
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from cluster_ligatures import NATIVE_CLUSTER_NAMES


def main():
    svg_dir = ROOT / 'ligatures/svg'
    png_dir = ROOT / 'ligatures/png/128'
    svg_dir.mkdir(parents=True, exist_ok=True)
    png_dir.mkdir(parents=True, exist_ok=True)
    for name in NATIVE_CLUSTER_NAMES:
        svg = svg_dir / (name + '.svg')
        png = png_dir / (name + '.png')
        shutil.copyfile(ROOT / 'experiments/emoji-lfsr/artwork' / svg.name, svg)
        subprocess.run(['inkscape', str(svg), '--export-type=png',
                        '--export-height=128', f'--export-filename={png}'], check=True)
        width, height = struct.unpack('>II', png.read_bytes()[16:24])
        if height != 128 or width > 255:
            raise ValueError(f'{png}: {width}x{height} exceeds CBDT small metrics')


if __name__ == '__main__':
    main()

"""Convert the approved transparent concept to the two vector/bitmap font assets.

Development dependencies: Pillow, vtracer, Inkscape, nanoemoji. The resulting
bundle is checked in, so normal builds only need fontTools to install it.
"""
from pathlib import Path
import shutil
import subprocess
import hashlib
import json
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / 'ligatures/supplemental/poop'
SVG_NS = 'http://www.w3.org/2000/svg'


def main():
    from PIL import Image, ImageDraw
    import vtracer
    source = Image.open(ART / 'approved-transparent.png').convert('RGBA')
    # Extraction bounds from the approved two-cluster sheet. Use one scale
    # for both heaps so the individual characters retain their relative sizes.
    crops = [source.crop((0, 0, 810, source.height)),
             source.crop((810, 0, source.width, source.height))]
    cleaned = []
    for image in crops:
        mask = image.getchannel('A').point(lambda a: 255 if a > 128 else 0)
        ImageDraw.floodfill(mask, (image.width // 2, image.height * 3 // 4), 128, border=0)
        mask = mask.point(lambda a: 255 if a == 128 else 0)
        image.putalpha(mask)
        image = image.crop(mask.getbbox())
        image = image.quantize(colors=32, method=Image.Quantize.FASTOCTREE,
                               dither=Image.Dither.NONE).convert('RGBA')
        cleaned.append(image)
    crops = cleaned
    scale = min(251 / crops[1].width, 120 / max(im.height for im in crops))
    ET.register_namespace('', SVG_NS)
    work = ROOT / 'build/poop-artwork'
    work.mkdir(parents=True, exist_ok=True)
    for count, image in zip((2, 3), crops):
        name = 'emoji_u' + '_'.join(['1f4a9'] * count)
        png = work / (name + '.png')
        traced = work / (name + '.svg')
        image.save(png)
        vtracer.convert_image_to_svg_py(str(png), str(traced), colormode='color',
            hierarchical='stacked', mode='spline', filter_speckle=12,
            color_precision=8, layer_difference=1, corner_threshold=60,
            length_threshold=4, max_iterations=10, splice_threshold=45, path_precision=2)
        original = ET.parse(traced).getroot()
        width = min(255, round(image.width * scale) + 4)
        root = ET.Element(f'{{{SVG_NS}}}svg', width=str(width), height='128',
                          viewBox=f'0 0 {width} 128')
        ET.SubElement(root, f'{{{SVG_NS}}}desc').text = (
            'DEImoji original artwork, Apache-2.0. Vector conversion of the approved '
            'generated concept. Trio: raised rear center with reversed spiral.')
        group = ET.SubElement(root, f'{{{SVG_NS}}}g', transform=(
            f'translate(2 {120-image.height*scale:.5f}) scale({scale:.8f})'))
        group.extend(list(original))
        dest = ART / 'svg' / (name + '.svg')
        ET.ElementTree(root).write(dest, encoding='utf-8', xml_declaration=True)
        subprocess.run(['inkscape', str(dest), '--export-type=png', '--export-height=128',
                        '--export-filename=' + str(ART / 'png/128' / (name + '.png'))], check=True)
        print(name, width, 'x 128, paths:', len(list(group)))
    config = work / 'poop.toml'
    sources = [ART / 'source/emoji_u1f4a9.svg'] + sorted((ART / 'svg').glob('*.svg'))
    config.write_text('''family = "DEImoji Supplemental Poop"
output_file = "Poop-COLRv1.ttf"
color_format = "glyf_colr_1"
upem = 1024
width = 1275
ascender = 950
descender = -250
linegap = 0
clip_to_viewbox = true
ignore_reuse_error = true
[axis.wght]
name = "Weight"
default = 400
[master.regular]
style_name = "Regular"
srcs = ''' + json.dumps([str(p) for p in sources]) + '''
[master.regular.position]
wght = 400
''')
    subprocess.run([sys.executable, '-m', 'nanoemoji.nanoemoji', '--build_dir',
                    str(work / 'colr'), str(config)], check=True)
    shutil.copyfile(work / 'colr/Poop-COLRv1.ttf', ART / 'Poop-COLRv1.ttf')
    files = [p for p in ART.rglob('*') if p.is_file() and p.name != 'manifest.json']
    manifest = {'version': 1, 'files': {str(p.relative_to(ART)):
                hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}}
    (ART / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')


if __name__ == '__main__':
    main()

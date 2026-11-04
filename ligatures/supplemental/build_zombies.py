"""Compose ten Noto-derived zombie crowds; compile unencoded COLRv1 artwork.

Development-only: Inkscape, nanoemoji and ninja. No raster tracing or generated
illustration: all faces, hair and decorations come from the pinned Noto SVGs.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import random
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / 'ligatures/supplemental/zombies'
NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
TAG = lambda name: f'{{{NS}}}{name}'
ORIGIN = '30649a050403b9f4d05f8502d761ecb55c6838b9'
BASES = ('1f9df', '1f9df_200d_2640', '1f9df_200d_2642')
HAIR = {'ginger': ('1f9d1_200d_1f9b0', (0,), (9,)),
        'white': ('1f9d1_200d_1f9b3', (0,), (9,)),
        'curly': ('1f9d1_200d_1f9b1', (0,), (4, 5, 6))}
HATS = {'hardhat': ('1f477', 'helmet_2_', 'translate(11.5 -6) scale(.82)'),
        'police': ('1f46e', 'police_x5F_hat', 'translate(10 -4) scale(.84)'),
        'chef': ('1f9d1_200d_1f373', 10, 'translate(10 0) scale(.9)'),
        'graduate': ('1f9d1_200d_1f393', 'hat', 'translate(11 -2) scale(.82)'),
        'firefighter': ('1f9d1_200d_1f692', 'helmet', 'translate(11 -6) scale(.82)')}
# Subtle greens/greys, rather than human Unicode skin tones.
PALETTES = (('#8AB64C', '#6E9639', '#4B6E2B'),
            ('#9BAA76', '#7E9060', '#596C45'),
            ('#7F9A64', '#647C4E', '#455C37'),
            ('#A3AC8A', '#858E70', '#606C50'),
            ('#819B51', '#657E3C', '#465D2B'))
SHIRTS = (('#41677B', '#315365'), ('#D9A441', '#B68432'),
          ('#9E5358', '#7E4148'), ('#687E8C', '#526672'), ('#438E8C', '#33726F'))


def source(stem):
    return ET.parse(ART / 'source' / f'emoji_u{stem}.svg').getroot()


def renamed(element, prefix, colors=None):
    element = deepcopy(element)
    for node in element.iter():
        for key, value in list(node.attrib.items()):
            if key == 'id':
                value = prefix + value
            elif key.endswith('href') and value.startswith('#'):
                value = '#' + prefix + value[1:]
            else:
                value = value.replace('url(#', 'url(#' + prefix)
                if colors:
                    for old, new in colors.items():
                        value = value.replace(old, new)
            node.set(key, value)
    return element


def character(spec, prefix):
    gender, hair, hat, palette, shirt = spec
    root = source(BASES[gender])
    discard = ({0, 1, 12, 13}, {0, 12, 13, 14}, {5})[gender] if hair != 'original' else set()
    skin, shade, dark = PALETTES[palette]
    colors = {'#82CC2B': skin, '#709921': shade, '#4E6B17': dark, '#597718': dark}
    for old in ('#651FFF', '#00BFA5', '#F78C1F'):
        colors[old] = SHIRTS[shirt][0]
    for old in ('#530EEB', '#009E89', '#ED6D23'):
        colors[old] = SHIRTS[shirt][1]
    group = ET.Element(TAG('g'))
    if hair != 'original':
        stem, back, front = HAIR[hair]
        donor = source(stem)
        for i in back:
            group.append(renamed(donor[i], prefix + 'hair_'))
    for i, node in enumerate(root):
        if i not in discard:
            group.append(renamed(node, prefix + 'body_', colors))
    if hair != 'original':
        for i in front:
            group.append(renamed(donor[i], prefix + 'hair_'))
    if hat != 'none':
        stem, identifier, transform = HATS[hat]
        donor = source(stem)
        decoration = donor[identifier] if isinstance(identifier, int) else next(
            node for node in donor.iter() if node.get('id') == identifier)
        overlay = ET.SubElement(group, TAG('g'), transform=transform)
        overlay.append(renamed(decoration, prefix + 'hat_'))
    return group


def recipes():
    rng = random.Random(0xDE1)
    genders = list(range(3)) * 9
    hairs = ['original', 'ginger', 'white', 'curly'] * 7
    hats = ['none', 'hardhat', 'none', 'chef', 'none', 'police', 'none', 'graduate', 'none', 'firefighter'] * 3
    rng.shuffle(genders); rng.shuffle(hairs); rng.shuffle(hats)
    specs = []
    for i in range(25):
        shirt = (i*3) % 5
        spec = (genders[i], hairs[i], hats[i], i % 5, shirt)
        while spec in specs:
            shirt = (shirt+1) % 5
            spec = (genders[i], hairs[i], hats[i], i % 5, shirt)
        specs.append(spec)
    assert len(set(specs)) == 25
    return specs


def main():
    for folder in ('svg', 'png/128'):
        (ART / folder).mkdir(parents=True, exist_ok=True)
    work = ROOT / 'build/zombie-variants'
    work.mkdir(parents=True, exist_ok=True)
    specs = recipes()
    entries = []
    offset = 0
    for count in (2, 3):
        width = 184 if count == 2 else 240
        for variant in range(5):
            name = f'zombie{count}_v{variant}'
            root = ET.Element(TAG('svg'), width=str(width), height='128', viewBox=f'0 0 {width} 128')
            ET.SubElement(root, TAG('title')).text = f'{count}-zombie crowd, variant {variant+1}'
            ET.SubElement(root, TAG('desc')).text = ('Composed from Google Noto Emoji SVGs, Apache-2.0; pinned source ' + ORIGIN + '. Mixed gender, hairstyle, headwear and decay colours. Singleton artwork unchanged.')
            members = specs[offset:offset+count]
            offset += count
            positions = (('translate(0 2) scale(.9) rotate(-4 64 70)',
                          'translate(57 0) scale(1) rotate(2 64 70)') if count == 2 else
                         ('translate(59 0) scale(.92) rotate(-1 64 70)',
                          'translate(0 7) scale(.88) rotate(-4 64 70)',
                          'translate(122 6) scale(.91) rotate(4 64 70)'))
            for i, (spec, transform) in enumerate(zip(members, positions)):
                group = character(spec, name + f'_p{i}_')
                group.set('transform', transform)
                root.append(group)
            svg = ART / 'svg' / (name + '.svg')
            ET.ElementTree(root).write(svg, encoding='utf-8', xml_declaration=True)
            subprocess.run(['inkscape', str(svg), '--export-type=png', '--export-height=128',
                            '--export-filename=' + str(ART / 'png/128' / (name + '.png'))],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            entries.append(dict(name=name, size=count, variant=variant, characters=members))
    # A gallery made from the actual vector assets, for review at readable scale.
    sheet = ET.Element(TAG('svg'), width='1320', height='384', viewBox='0 0 1320 384')
    ET.SubElement(sheet, TAG('rect'), width='1320', height='384', fill='#fafafa')
    for entry in entries:
        row, col = (0 if entry['size'] == 2 else 1), entry['variant']
        svg = ET.parse(ART / 'svg' / (entry['name']+'.svg')).getroot()
        svg.set('x', str(col*264+(264-int(svg.get('width')))/2)); svg.set('y', str(row*192+12))
        sheet.append(svg)
        label = ET.SubElement(sheet, TAG('text'), x=str(col*264+12), y=str(row*192+164),
                              style='font:14px sans-serif;fill:#333')
        label.text = f"{entry['size']} zombies · variant {col+1}"
    ET.ElementTree(sheet).write(work/'gallery.svg')
    subprocess.run(['inkscape', str(work/'gallery.svg'), '--export-filename='+str(ART/'preview.png')], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Custom glyphmap leaves EVERY variant unencoded, even in this mini font.
    (work/'zombie_glyphmap.py').write_text('''import argparse
from pathlib import Path
from nanoemoji import util
from nanoemoji.glyphmap import GlyphMapping
p=argparse.ArgumentParser();p.add_argument('-v');p.add_argument('--output_file');p.add_argument('files',nargs='*')
a=p.parse_args()
with open(a.output_file,'w') as out:
 for f in util.expand_ninja_response_files(a.files):
  out.write(GlyphMapping(Path(f),None,(),Path(f).stem).csv_line()+'\\n')
''')
    config = work/'zombies.toml'
    config.write_text('''family = "DEImoji Zombie Variants"
output_file = "Zombies-COLRv1.ttf"
color_format = "glyf_colr_1"
keep_glyph_names = true
glyphmap_generator = "zombie_glyphmap"
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
srcs = ''' + json.dumps([str(ART/'svg'/(e['name']+'.svg')) for e in entries]) + '''
[master.regular.position]
wght = 400
''')
    env = os.environ.copy()
    env['PYTHONPATH'] = str(work) + os.pathsep + env.get('PYTHONPATH','')
    subprocess.run([sys.executable,'-m','nanoemoji.nanoemoji','--build_dir',str(work/'colr'),str(config)],check=True,env=env)
    shutil.copyfile(work/'colr/Zombies-COLRv1.ttf', ART/'Zombies-COLRv1.ttf')
    files = [p for p in ART.rglob('*') if p.is_file() and p.name != 'manifest.json']
    manifest = dict(version=1, style='noto-zombie-crowds-v1', source_commit=ORIGIN,
                    variants=entries, files={str(p.relative_to(ART)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)})
    (ART/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


if __name__ == '__main__':
    main()

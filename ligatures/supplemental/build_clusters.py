"""Compose fixed Noto pairs/trios and compile their unencoded color artwork.

Development only: Inkscape, nanoemoji, ninja. The checked-in pack is installed
on cached fonts without re-rendering the native emoji collection.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / 'ligatures/supplemental/clusters'
NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
T = lambda tag: f'{{{NS}}}{tag}'
ORIGIN = '585853a395a28317139d571038985d1e97388450'
FAMILIES = {'headstone':0x1FAA6, 'fireworks':0x1F386, 'popper':0x1F389, 'fire':0x1F525}


def copy_art(root, prefix, transform, skip=()):
    group = ET.Element(T('g'), transform=transform)
    for i, child in enumerate(root):
        if i in skip:
            continue
        node = deepcopy(child)
        for part in node.iter():
            for key, value in list(part.attrib.items()):
                if key == 'id':
                    value = prefix + value
                elif key.endswith('href') and value.startswith('#'):
                    value = '#' + prefix + value[1:]
                else:
                    value = value.replace('url(#', 'url(#'+prefix)
                part.set(key,value)
        group.append(node)
    return group


def stone_shape(source, shape):
    """Keep Noto materials, inscriptions and plinth; change only the crown."""
    result=deepcopy(source)
    if shape == 'arched':
        return result
    body=result[0][0]
    for node in list(body)[6:]:
        body.remove(node)
    if shape == 'round':
        front='M37.67 114.07 V42 C37.67 -2 105.95 -2 105.95 42 V114.07 Z'
        back='M21.8 114.07 V42 C21.8 15 36 8 55.8 8 H71.8 V114.07 Z'
        edge='M21.8 42 C21.8 15 36 8 55.8 8 H71.8 C48 8 37.67 24 37.67 42 Z'
    else:
        front='M37.67 114.07 V24 L49.67 12 H93.95 L105.95 24 V114.07 Z'
        back='M21.8 114.07 V24 L33.8 12 H77.95 L89.95 24 V114.07 Z'
        edge='M21.8 24 L33.8 12 H49.67 L37.67 24 Z'
    body[1].set('d',back);body[3].set('d',edge);body[5].set('d',front)
    return result


def compose(family, count):
    source = ET.parse(ART/'source'/f'emoji_u{FAMILIES[family]:x}.svg').getroot()
    width = {('headstone',2):180, ('headstone',3):238,
             ('fireworks',2):188, ('fireworks',3):250,
             ('popper',2):184, ('popper',3):244,
             ('fire',2):174, ('fire',3):230}[family,count]
    root = ET.Element(T('svg'),width=str(width),height='128',viewBox=f'0 0 {width} 128')
    if family == 'headstone':
        # Rear stone first: staggered crowns and bases, shared ground level.
        placements = (('translate(53 1) scale(.94)', 'translate(-9 9) scale(.94)') if count==2 else
                      ('translate(55 -3) scale(.98)', 'translate(-10 10) scale(.94)',
                       'translate(116 7) scale(.96)'))
    elif family == 'fireworks':
        # Stretch only the background. Bursts retain circular proportions.
        root.append(copy_art(source,f'{family}{count}_sky_',f'scale({width/128} 1)',range(2,len(source))))
        placements = (('translate(-2 9) scale(.90)', 'translate(77 -3) scale(.88)') if count==2 else
                      ('translate(63 -3) scale(.94)', 'translate(-6 18) scale(.86)',
                       'translate(143 14) scale(.87)'))
    elif family == 'popper':
        placements = (('translate(59 -1) scale(.96) rotate(8 64 64)',
                       'translate(-1 8) scale(.94) rotate(-5 64 64)') if count==2 else
                      ('translate(63 -5) scale(.96) rotate(3 64 64)',
                       'translate(0 9) scale(.94) rotate(-6 64 64)',
                       'translate(124 8) scale(.94) rotate(9 64 64)'))
    else:
        # Overlap at the bases, with a taller flame behind two lower flames.
        placements = (('translate(49 -2) scale(.99)', 'translate(-6 21) scale(.83)') if count==2 else
                      ('translate(56 -3) scale(1)', 'translate(-5 23) scale(.82)',
                       'translate(121 14) scale(.90)'))
    for i, transform in enumerate(placements):
        member = stone_shape(source, ('round','bevel')[i] if count==2 else ('arched','round','bevel')[i]) if family=='headstone' else source
        root.append(copy_art(member,f'{family}{count}_p{i}_',transform, (0,1) if family=='fireworks' else ()))
    return root


def main():
    work = ROOT/'build/fixed-clusters'
    work.mkdir(parents=True,exist_ok=True)
    for folder in ('svg','png/128'):
        (ART/folder).mkdir(parents=True,exist_ok=True)
    entries=[]
    gallery=ET.Element(T('svg'),width='760',height='640',viewBox='0 0 760 640')
    ET.SubElement(gallery,T('rect'),width='760',height='640',fill='#fafafa')
    for row,(family,cp) in enumerate(FAMILIES.items()):
        for count in (2,3):
            name=f'{family}{count}'
            svg=compose(family,count)
            path=ART/'svg'/f'{name}.svg'
            ET.ElementTree(svg).write(path,encoding='utf-8',xml_declaration=True)
            subprocess.run(['inkscape',str(path),'--export-height=128',
                            '--export-filename='+str(ART/'png/128'/f'{name}.png')],check=True,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            svg.set('x',str(40+(count-2)*350));svg.set('y',str(row*160+4))
            gallery.append(svg)
            label=ET.SubElement(gallery,T('text'),x=str(40+(count-2)*350),y=str(row*160+150),
                                style='font:14px sans-serif;fill:#333')
            label.text=f'{family} × {count}'
            entries.append(dict(name=name,codepoint=cp,size=count))
    ET.ElementTree(gallery).write(work/'gallery.svg')
    subprocess.run(['inkscape',str(work/'gallery.svg'),'--export-filename='+str(ART/'preview.png')],check=True,
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    (work/'cluster_glyphmap.py').write_text('''import argparse
from pathlib import Path
from nanoemoji import util
from nanoemoji.glyphmap import GlyphMapping
p=argparse.ArgumentParser();p.add_argument('-v');p.add_argument('--output_file');p.add_argument('files',nargs='*')
a=p.parse_args()
with open(a.output_file,'w') as out:
 for f in util.expand_ninja_response_files(a.files):
  out.write(GlyphMapping(Path(f),None,(),Path(f).stem).csv_line()+'\\n')
''')
    config=work/'clusters.toml'
    config.write_text('''family = "DEImoji Fixed Clusters"
output_file = "Clusters-COLRv1.ttf"
color_format = "glyf_colr_1"
keep_glyph_names = true
glyphmap_generator = "cluster_glyphmap"
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
srcs = '''+json.dumps([str(ART/'svg'/(e['name']+'.svg')) for e in entries])+'''
[master.regular.position]
wght = 400
''')
    env=os.environ.copy();env['PYTHONPATH']=str(work)+os.pathsep+env.get('PYTHONPATH','')
    subprocess.run([sys.executable,'-m','nanoemoji.nanoemoji','--build_dir',str(work/'colr'),str(config)],check=True,env=env)
    shutil.copyfile(work/'colr/Clusters-COLRv1.ttf',ART/'Clusters-COLRv1.ttf')
    files=sorted(p for p in ART.rglob('*') if p.is_file() and p.name!='manifest.json')
    manifest=dict(version=1,style='noto-fixed-clusters-v1',source_commit=ORIGIN,entries=entries,
                  files={str(p.relative_to(ART)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (ART/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    main()

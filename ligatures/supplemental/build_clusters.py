"""Compose fixed Noto pairs/trios and compile their unencoded color artwork.

Development only: Inkscape, nanoemoji, ninja. The checked-in pack is installed
on cached fonts without re-rendering the native emoji collection.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

from picosvg.svg_types import SVGPath, SVGCircle
from picosvg.svg_pathops import difference, union
from picosvg.svg_transform import Affine2D

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
    elif shape == 'cross':
        # Celtic ring and cross are a single stone silhouette, with four open
        # quadrants. Keep the extrusion shallow enough that the holes stay open.
        outer=SVGCircle(cx=72,cy=38,r=28).as_path()
        inner=SVGCircle(cx=72,cy=38,r=21).as_path()
        ring=SVGPath().update_path(difference([outer.as_cmd_seq(),inner.as_cmd_seq()],['nonzero','nonzero']))
        cross=SVGPath(d='M63 8 H81 V30 H108 V46 H81 V67 L87 114.07 H57 L63 67 V46 H36 V30 H63 Z')
        face=SVGPath().update_path(union([ring.as_cmd_seq(),cross.as_cmd_seq()],['nonzero','nonzero']))
        front=face.d
        back=face.apply_transform(Affine2D(1,0,0,1,-6,0)).d
        edge=''
    else:
        front='M37.67 114.07 V24 L49.67 12 H93.95 L105.95 24 V114.07 Z'
        back='M21.8 114.07 V24 L33.8 12 H77.95 L89.95 24 V114.07 Z'
        edge='M21.8 24 L33.8 12 H49.67 L37.67 24 Z'
    body[1].set('d',back);body[3].set('d',edge);body[5].set('d',front)
    return result


def inscription(source, variant, cross=False):
    result=deepcopy(source)
    # Move complete engraved strokes, including their Noto bevel highlights.
    targets=((38,64,51),(64,38,51),(51,64,38))[variant%3]
    if cross:
        targets=(70,94,82)
    for group in result[0][1:5]:
        for path in group.iter(T('path')):
            box=SVGPath(d=path.get('d')).bounding_box()
            row=min(range(3),key=lambda i:abs(box.y-(35.4,48.6,61.5)[i]))
            dy=targets[row]-(38,51,64)[row]
            path.set('transform',f'translate(42 {dy}) scale(.40 1)' if cross else f'translate(0 {dy})')
    return result


def party(source, variant):
    result=deepcopy(source)
    # Native groups 7–9 are the three airborne streamers. The direct paths
    # before them are cone stripes/cavity: leave those untouched.
    body=result[0][0][0]
    streamers=list(body)[7:10]
    assert [g[0].get('style') for g in streamers] == [
        'fill:#03A9F4;', 'fill:#F44336;', 'fill:#F48FB1;']
    anchors=((55,84),(43,72),(59,75))
    directions=(-6,-81,-47)
    # Each recipe lists which SHAPE occupies right, upright and diagonal slots.
    # Pair and trio together use five different permutations, not one shared edit.
    permutations=((2,0,1),(1,2,0),(0,2,1),(2,1,0),(1,0,2))
    palettes=(('#F48FB1','#03A9F4','#F44336'),
              ('#03A9F4','#AB47BC','#F48FB1'),
              ('#FF7043','#F48FB1','#26A69A'),
              ('#AB47BC','#03A9F4','#FF7043'),
              ('#03A9F4','#F44336','#AB47BC'))
    curl=result[0][0][-1]
    result[0][0].remove(curl)
    streamers[1].append(curl)  # Its inner fold travels with the red native shape.
    for group in streamers:
        body.remove(group)
    for slot,shape in enumerate(permutations[variant]):
        group=streamers[shape]
        x,y=anchors[slot];sx,sy=anchors[shape]
        angle=directions[slot]-directions[shape]
        # The longest native streamer needs shortening when sent straight up.
        scale=.78 if shape==2 and slot==1 else .94 if shape!=slot else 1
        group.set('transform',f'translate({x} {y}) rotate({angle}) scale({scale}) translate({-sx} {-sy})')
        color=palettes[variant][slot]
        group[0].set('style','fill:'+color+';')
        if shape==1:
            rgb=[int(color[i:i+2],16) for i in (1,3,5)]
            curl.set('style','fill:#'+''.join(f'{round(c*.68):02X}' for c in rgb)+';')
        body.append(group)
    colors=('#FFC107','#03A9F4','#F48FB1','#F44336','#FB8C00')
    for j,node in enumerate(list(result[0])[1:]):
        wrapper=ET.Element(T('g'),transform=f'translate({((j*7+variant*5)%15)-7} {((j*11+variant*7)%17)-8}) rotate({(j*17+variant*29)%51-25} 64 64)')
        for part in node.iter():
            if 'fill:' in part.get('style',''):
                part.set('style','fill:'+colors[(j+variant*2)%len(colors)]+';')
        result[0].remove(node);wrapper.append(node);result[0].append(wrapper)
    return result


def burst(variant,cx,cy):
    """Five different launches: ignition, bloom, opening, willow, fading embers."""
    group=ET.Element(T('g'))
    palettes=(('#FFF59D','#FFD54F','#FFB300'),('#FFB3DE','#F062C0','#CE48A0'),
              ('#C5F6FF','#4FC3F7','#039BE5'),('#DCE775','#AED581','#66BB6A'),
              ('#FFCCBC','#FF8A65','#EF5350'))
    colors=palettes[variant]
    def path(d,color,width):
        ET.SubElement(group,T('path'),d=d,fill='none',stroke=color,
                      attrib={'stroke-width':str(width),'stroke-linecap':'round'})
    count=(12,24,18,20,13)[variant]
    for i in range(count):
        a=2*math.pi*i/count+variant*.21
        x,y=math.cos(a),math.sin(a)
        r=(15,29,22,29,31)[variant]+(i%3)*2
        if variant==0:
            path(f'M{cx+x*4:.2f} {cy+y*4:.2f} L{cx+x*r:.2f} {cy+y*r:.2f}',colors[i%3],2.8)
        elif variant in (1,2):
            start=6 if variant==1 else 10
            path(f'M{cx+x*start:.2f} {cy+y*start:.2f} Q{cx+x*r*.7-y*3:.2f} {cy+y*r*.7+x*3:.2f} {cx+x*r:.2f} {cy+y*r:.2f}',colors[i%3],3 if variant==1 else 2.5)
            ET.SubElement(group,T('circle'),cx=f'{cx+x*(r+5):.2f}',cy=f'{cy+y*(r+5):.2f}',r='1.4',fill=colors[0])
        elif variant==3:
            path(f'M{cx+x*7:.2f} {cy+y*7:.2f} Q{cx+x*r:.2f} {cy+y*r-7:.2f} {cx+x*r*1.05:.2f} {cy+y*r+22:.2f}',colors[i%3],2.5)
            ET.SubElement(group,T('circle'),cx=f'{cx+x*r*1.05:.2f}',cy=f'{cy+y*r+27:.2f}',r='1.1',fill=colors[0])
        else:
            path(f'M{cx+x*r:.2f} {cy+y*r:.2f} q{x*4:.2f} {y*4+3:.2f} {x*6:.2f} {y*6+9:.2f}',colors[i%3],2.3)
            ET.SubElement(group,T('circle'),cx=f'{cx+x*(r+7):.2f}',cy=f'{cy+y*(r+7)+15:.2f}',r='1.5',fill=colors[(i+1)%3])
    if variant in (0,1,2):
        ET.SubElement(group,T('circle'),cx=str(cx),cy=str(cy),r=str((4,2,3)[variant]),fill=colors[0])
    if variant in (0,2):path(f'M{cx} {cy+25} Q{cx-5} {cy+43} {cx-2} {cy+58}',colors[1],1.7)
    return group


def fireworks(count,position='isolated'):
    width={2:188,3:250}[count]
    root=ET.Element(T('svg'),width=str(width),height='128',viewBox=f'0 0 {width} 128')
    defs=ET.SubElement(root,T('defs'))
    gradient=ET.SubElement(defs,T('linearGradient'),id='sky',x1='0',y1='0',x2='0',y2='128',gradientUnits='userSpaceOnUse')
    for offset,color in (('0','#171728'),('.46','#064D90'),('1','#102137')):
        ET.SubElement(gradient,T('stop'),offset=offset,attrib={'stop-color':color})
    left=position in ('isolated','start');right=position in ('isolated','end')
    x0,x1,y0,y1,r=(3.8 if left else 0),(width-3.8 if right else width),3.87,124.22,7.52
    d=f'M{x0+r if left else x0} {y0} H{x1-r if right else x1} '
    d+=f'Q{x1} {y0} {x1} {y0+r} V{y1-r} Q{x1} {y1} {x1-r} {y1} ' if right else f'V{y1} '
    d+=f'H{x0+r if left else x0} '
    d+=f'Q{x0} {y1} {x0} {y1-r} V{y0+r} Q{x0} {y0} {x0+r} {y0} Z' if left else f'V{y0} Z'
    ET.SubElement(root,T('path'),d=d,fill='url(#sky)')
    clip=ET.SubElement(defs,T('clipPath'),id='skyclip');ET.SubElement(clip,T('path'),d=d)
    for side,enabled in (('left',left),('right',right)):
        if not enabled:continue
        grad=ET.SubElement(defs,T('linearGradient'),id=side,x1='0' if side=='left' else '1',y1='0',x2='1' if side=='left' else '0',y2='0')
        ET.SubElement(grad,T('stop'),offset='0',attrib={'stop-color':'#171728','stop-opacity':'.65'})
        ET.SubElement(grad,T('stop'),offset='1',attrib={'stop-color':'#171728','stop-opacity':'0'})
        ET.SubElement(root,T('rect'),x=str(x0 if side=='left' else x1-22),y=str(y0),width='22',height=str(y1-y0),fill=f'url(#{side})',attrib={'clip-path':'url(#skyclip)'})
    for variant,cx,cy in (((0,45,42),(1,141,71)) if count==2 else ((2,43,44),(3,124,58),(4,207,48))):
        root.append(burst(variant,cx,cy))
    return root


def compose(family, count):
    source = ET.parse(ART/'source'/f'emoji_u{FAMILIES[family]:x}.svg').getroot()
    width = {('headstone',2):180, ('headstone',3):238,
             ('fireworks',2):188, ('fireworks',3):250,
             ('popper',2):184, ('popper',3):244,
             ('fire',2):174, ('fire',3):230}[family,count]
    root = ET.Element(T('svg'),width=str(width),height='128',viewBox=f'0 0 {width} 128')
    if family == 'headstone':
        # Rear stone first: staggered crowns and bases, shared ground level.
        placements = (('translate(78 0) scale(.72)', 'translate(-9 9) scale(.94)') if count==2 else
                      ('translate(72 0) scale(.72)', 'translate(-10 10) scale(.94)',
                       'translate(116 7) scale(.96)'))
    elif family == 'fireworks':
        return fireworks(count)
    elif family == 'popper':
        placements = (('translate(59 -1) scale(.96) rotate(8 64 64)',
                       'translate(-1 8) scale(.94) rotate(-5 64 64)') if count==2 else
                      ('translate(45 -5) scale(.96) rotate(3 64 64)',
                       'translate(0 9) scale(.94) rotate(-6 64 64)',
                       'translate(124 8) scale(.94) rotate(9 64 64)'))
    else:
        # Overlap at the bases, with a taller flame behind two lower flames.
        placements = (('translate(49 -2) scale(.99)', 'translate(-6 21) scale(.83)') if count==2 else
                      ('translate(56 -3) scale(1)', 'translate(-5 23) scale(.82)',
                       'translate(121 14) scale(.90)'))
    for i, transform in enumerate(placements):
        member=source
        if family=='headstone':
            shape=('cross','round')[i] if count==2 else ('arched','cross','bevel')[i]
            member=inscription(stone_shape(source,shape),i,cross=shape=='cross')
        elif family=='popper':
            member=party(source,i if count==2 else i+2)
            if i==0:
                transform+=' translate(128 0) scale(-1 1)'
        elif family=='fire' and i==0:
            transform+=' translate(128 0) scale(-1 1)'
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
    for count in (2,3):
        for position in ('start','middle','end'):
            name=f'fireworks{count}_{position}'
            svg=fireworks(count,position);path=ART/'svg'/f'{name}.svg'
            ET.ElementTree(svg).write(path,encoding='utf-8',xml_declaration=True)
            subprocess.run(['inkscape',str(path),'--export-height=128','--export-filename='+str(ART/'png/128'/f'{name}.png')],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            entries.append(dict(name=name,codepoint=0x1F386,size=count,position=position))
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
    manifest=dict(version=2,style='noto-fixed-clusters-v2',source_commit=ORIGIN,entries=entries,
                  files={str(p.relative_to(ART)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (ART/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    main()

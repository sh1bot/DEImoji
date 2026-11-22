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
from picosvg.svg import SVG
from picosvg.svg_pathops import difference, union
from picosvg.svg_transform import Affine2D

ROOT = Path(__file__).resolve().parents[2]
ART = ROOT / 'ligatures/supplemental/clusters'
NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
T = lambda tag: f'{{{NS}}}{tag}'
ORIGIN = '585853a395a28317139d571038985d1e97388450'
FAMILIES = {'headstone':0x1FAA6, 'fireworks':0x1F386, 'popper':0x1F389, 'fire':0x1F525, 'moneybags':0x1F4B0}


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
    # Keep floating confetti within the native vertical range. This changes
    # position only: cones, streamers and paper retain their original scale.
    for wrapper in list(result[0])[1:]:
        probe=ET.Element(T('svg'),viewBox='-100 -100 328 328')
        probe.append(deepcopy(wrapper))
        box=SVG.fromstring(ET.tostring(probe)).topicosvg().bounding_box()
        if box is None:continue
        dy=max(2-box.y,min(0,124-(box.y+box.h)))
        if dy:
            parent=ET.Element(T('g'),transform=f'translate(0 {dy})')
            result[0].remove(wrapper);parent.append(wrapper);result[0].append(parent)
    return result




def moneybag(source,mirrored=False):
    if not mirrored:return source
    result=ET.Element(T('svg'),viewBox='0 0 128 128')
    visible=deepcopy(source[1]);main=visible[0]
    # Currency is a printed mark, not part of the reflected silhouette.
    currency=[main[3],main[4]]
    for node in currency:main.remove(node)
    side_shadow=visible[-1];visible.remove(side_shadow)
    flap=main[2][0]
    # The broad native right-hand shadow would move onto the lit left side.
    # Replace it on the opposite side of the fabric. The small inner crease
    # remains attached to its fold, now on the right of the mirrored opening.
    flap.remove(flap[1])
    ET.SubElement(flap,T('path'),fill='#E2A610',d='M68.3 8.59 C63.5 12.4 64.7 30.9 69.5 36.9 C71.9 39.9 76.3 41.2 81.1 40.8 L82.4 36.8 C74.6 33.7 69.1 20.2 68.3 8.59 Z')
    mirror=ET.SubElement(result,T('g'),transform='translate(128 0) scale(-1 1)')
    mirror.append(visible)
    lettering=ET.SubElement(result,T('g'),transform='rotate(-28 64 80)')
    lettering.extend(currency)
    # Keep the shallow side-fold shadow on the viewer's right, where the
    # original upper-left lighting places it, rather than reflecting it left.
    side_shadow.set('transform','translate(4 0)');result.append(side_shadow)
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


def fireworks(count):
    # Measured painted bounds include stroke caps and the outermost sparks.
    # Keep the original relative burst positions, crop unused sky, and reserve
    # only the clear strip needed for overlapping two rounded backgrounds.
    scale=.875
    spark_x,spark_width={2:(27.15,153.2),3:(10.68,239.48)}[count]
    margin,radius,edge_allowance,spark_allowance=3.8,7.52,.5,3.25
    guard=margin+2*radius+edge_allowance+spark_allowance
    width=math.ceil(spark_width*scale+2*guard)
    assert width<=255  # CBDT width field at the native 128px strike.
    root=ET.Element(T('svg'),width=str(width),height='128',viewBox=f'0 0 {width} 128')
    defs=ET.SubElement(root,T('defs'))
    gradient=ET.SubElement(defs,T('linearGradient'),id='sky',x1='0',y1='0',x2='0',y2='128',gradientUnits='userSpaceOnUse')
    for offset,color in (('0','#171728'),('.46','#064D90'),('1','#102137')):
        ET.SubElement(gradient,T('stop'),offset=offset,attrib={'stop-color':color})
    ET.SubElement(root,T('rect'),x=str(margin),y='3.87',width=str(width-2*margin),height='120.35',rx=str(radius),fill='url(#sky)')
    group=ET.SubElement(root,T('g'),id='sparks',transform=f'translate({guard-spark_x*scale} {64*(1-scale)}) scale({scale})')
    for variant,cx,cy in (((0,45,42),(1,141,71)) if count==2 else ((2,43,44),(3,124,58),(4,207,48))):
        group.append(burst(variant,cx,cy))
    return root


def compose(family, count):
    source = ET.parse(ART/'source'/f'emoji_u{FAMILIES[family]:x}.svg').getroot()
    width = {('headstone',2):180, ('headstone',3):238,
             ('fireworks',2):188, ('fireworks',3):250,
             ('popper',2):224, ('popper',3):330,
             ('fire',2):174, ('fire',3):230,
             ('moneybags',2):180, ('moneybags',3):206}[family,count]
    root = ET.Element(T('svg'),width=str(width),height='128',viewBox=f'0 0 {width} 128')
    if family == 'headstone':
        # Rear stone first: staggered crowns and bases, shared ground level.
        placements = (('translate(78 0) scale(.72)', 'translate(-9 9) scale(.94)') if count==2 else
                      ('translate(72 0) scale(.72)', 'translate(-10 10) scale(.94)',
                       'translate(116 7) scale(.96)'))
    elif family == 'fireworks':
        return fireworks(count)
    elif family == 'moneybags':
        # Keep the dollar signs readable. The rear bag is
        # smaller and higher; the front bags overlap into one connected pile.
        placements=(('translate(66 3) scale(.87) rotate(7 64 64)',
                     'translate(-3 13) scale(.89) rotate(-6 64 64)') if count==2 else
                    ('translate(48 -2) scale(.77) rotate(6 64 64)',
                     'translate(-3 15) scale(.88) rotate(-6 64 64)',
                     'translate(83 13) scale(.90) rotate(5 64 64)'))
    elif family == 'popper':
        placements = (('translate(108 7) scale(.86)',
                       'translate(6 12) scale(.86)') if count==2 else
                      ('translate(106 5) scale(.86)',
                       'translate(6 12) scale(.86)',
                       'translate(217 9) scale(.86)'))
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
        elif family=='moneybags':
            member=moneybag(source,(count==2 and i==0) or (count==3 and i==2))
        elif family=='fire' and i==0:
            transform+=' translate(128 0) scale(-1 1)'
        root.append(copy_art(member,f'{family}{count}_p{i}_',transform, (0,1) if family=='fireworks' else ()))
    if family=='moneybags':
        # Crop the unused side space, retaining a narrow clear edge for GPOS.
        crop={2:(3,174),3:(3,194)}[count]
        group=ET.Element(T('g'),transform=f'translate({-crop[0]} 0)')
        for child in list(root):root.remove(child);group.append(child)
        root.append(group);root.set('width',str(crop[1]));root.set('viewBox',f'0 0 {crop[1]} 128')
    return root


def main():
    work = ROOT/'build/fixed-clusters'
    work.mkdir(parents=True,exist_ok=True)
    for folder in ('svg','png/128'):
        (ART/folder).mkdir(parents=True,exist_ok=True)
    entries=[]
    height=160*len(FAMILIES)
    gallery=ET.Element(T('svg'),width='880',height=str(height),viewBox=f'0 0 880 {height}')
    ET.SubElement(gallery,T('rect'),width='880',height=str(height),fill='#fafafa')
    for row,(family,cp) in enumerate(FAMILIES.items()):
        for count in (2,3):
            name=f'{family}{count}'
            svg=compose(family,count)
            path=ART/'svg'/f'{name}.svg'
            ET.ElementTree(svg).write(path,encoding='utf-8',xml_declaration=True)
            subprocess.run(['inkscape',str(path),'--export-height=128',
                            '--export-filename='+str(ART/'png/128'/f'{name}.png')],check=True,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            svg.set('x',str(40+(count-2)*420));svg.set('y',str(row*160+4))
            gallery.append(svg)
            label=ET.SubElement(gallery,T('text'),x=str(40+(count-2)*420),y=str(row*160+150),
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
    manifest=dict(version=5,style='noto-fixed-clusters-v5',source_commit=ORIGIN,entries=entries,
                  files={str(p.relative_to(ART)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
    (ART/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')

if __name__=='__main__':
    main()

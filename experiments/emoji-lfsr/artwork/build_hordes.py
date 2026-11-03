"""Compose self-contained vector ligature artwork from Noto's zombie SVG."""
from copy import deepcopy
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parent
NS = 'http://www.w3.org/2000/svg'
ET.register_namespace('', NS)
source = ET.parse(ROOT / 'noto-zombie-original.svg').getroot()


def make(name, width, figures, species='zombie', codepoint='1f9df', variants=None):
    svg = ET.Element(f'{{{NS}}}svg', {
        'version': '1.1', 'viewBox': f'0 0 {width} 128',
        'width': str(width), 'height': '128',
        'role': 'img', 'aria-labelledby': 'title description',
    })
    ET.SubElement(svg, f'{{{NS}}}title', {'id': 'title'}).text = (
        f'{len(figures)}-{species} ' + ('horde' if species == 'zombie' else 'cluster'))
    ET.SubElement(svg, f'{{{NS}}}desc', {'id': 'description'}).text = (
        f'Overlapping, staggered Noto {species} figures on a transparent background. '
        f'Derived from Google Noto Emoji emoji_u{codepoint}.svg, Apache-2.0. '
        f'Source: https://github.com/sh1bot/DEImoji/blob/main/2D/svg/emoji_u{codepoint}.svg')
    if variants:
        svg.find(f'{{{NS}}}desc').text += (
            ' Also uses emoji_u1f9df_200d_2640.svg (woman) and '
            'emoji_u1f9df_200d_2642.svg (man) from the same source directory. '
            'The man has a subtle olive-green palette variation.')
    for i, (x, y, scale, angle, shirt) in enumerate(figures):
        group = ET.SubElement(svg, f'{{{NS}}}g', {
            'id': f'{species}-{i + 1}',
            'transform': f'translate({x} {y}) scale({scale}) rotate({angle} 64 70)',
        })
        figure_source, skin = (variants[i] if variants else (source, {}))
        children = [deepcopy(child) for child in figure_source]
        ids = {el.attrib['id']: f'z{i}_{el.attrib["id"]}'
               for child in children for el in child.iter() if 'id' in el.attrib}
        for child in children:
            for el in child.iter():
                for key, value in list(el.attrib.items()):
                    if key == 'id':
                        el.set(key, ids[value])
                    else:
                        for old, new in ids.items():
                            value = value.replace(f'url(#{old})', f'url(#{new})')
                        # Distinguish the rear figures without changing their faces.
                        value = value.replace('#F78C1F', shirt[0]).replace('#ED6D23', shirt[1])
                        for old, new in skin.items():
                            value = value.replace(old, new)
                        el.set(key, value)
            group.append(child)
    ET.indent(svg)
    ET.ElementTree(svg).write(ROOT / name, encoding='utf-8', xml_declaration=True)


woman = ET.parse(ROOT / 'noto-zombie-woman-original.svg').getroot()
man = ET.parse(ROOT / 'noto-zombie-man-original.svg').getroot()
# A coordinated, slightly quieter olive green, preserving the shading steps.
olive = {'#82CC2B': '#87C238', '#709921': '#76932B',
         '#597718': '#5E7222', '#4E6B17': '#53661F'}
make('emoji_u1f9df_1f9df.svg', 184, [
    (0, 2, .90, -4, ('#DA7D31', '#BA5829')),
    (57, 0, 1, 2, ('#F78C1F', '#ED6D23')),
], variants=[(woman, {}), (man, olive)])
make('emoji_u1f9df_1f9df_1f9df.svg', 240, [
    (0, 2, .88, -4, ('#DA7D31', '#BA5829')),
    (122, 1, .91, 4, ('#EF9C39', '#D57727')),
    (59, 0, 1, -1, ('#F78C1F', '#ED6D23')),
], variants=[(woman, {}), (man, olive), (source, {})])

source = ET.parse(ROOT / 'noto-sunflower-original.svg').getroot()
make('emoji_u1f33b_1f33b.svg', 192, [
    (0, 6, .92, -7, ('#F78C1F', '#ED6D23')),
    (65, 0, 1, 5, ('#F78C1F', '#ED6D23')),
], 'sunflower', '1f33b')
make('emoji_u1f33b_1f33b_1f33b.svg', 252, [
    (0, 5, .92, -8, ('#F78C1F', '#ED6D23')),
    (130, 5, .92, 9, ('#F78C1F', '#ED6D23')),
    (65, 0, 1, -2, ('#F78C1F', '#ED6D23')),
], 'sunflower', '1f33b')

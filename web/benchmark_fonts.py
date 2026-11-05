"""Compare in-memory font loading and HarfBuzz shaping, without rasterization.

Example: python web/benchmark_fonts.py --font upstream=upstream.ttf \
  --font deimoji=build/site/fonts/DEImoji-COLRv1.ttf --output benchmark.json
Requires fontTools and the system HarfBuzz library. Reads fonts, never edits them.
"""
import argparse
import ctypes as C
import ctypes.util
from io import BytesIO
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import time

import fontTools
from fontTools.ttLib import TTFont

CASES = {
    'short_clusters': ('🪦🪦🪦🎉🎉🔥🔥🔥🌻🌻💩💩💩', 1),
    'cluster_run': ('💩'*80+'🌻'*80+'🎉'*80+'🔥'*80, 10),
    'short_diversity': ('🏃', 36),
    'diversity_run': ('🏃', 3200),
    'mixed_run': ('🏃🌻💩🧟🪦🎉🔥🧑🧓👍 ', 200),
    'explicit_sequences': ('🏃🏽\u200d♀️👍🏿🧑🏻\u200d♂️👵🏿 ', 120),
    'plain_text': ('Lorem ipsum dolor sit amet. ', 100),
}


class Feature(C.Structure):
    _fields_=[(k,C.c_uint32) for k in ('tag','value','start','end')]


class HarfBuzz:
    def __init__(self):
        name=ctypes.util.find_library('harfbuzz')
        if not name:raise RuntimeError('Install the system HarfBuzz library')
        self.lib=C.CDLL(name)
        ptr=C.c_void_p
        declarations=[
            ('hb_version_string',C.c_char_p,[]),
            ('hb_blob_create',ptr,[C.c_char_p,C.c_uint,C.c_int,ptr,ptr]),
            ('hb_face_create',ptr,[ptr,C.c_uint]),('hb_font_create',ptr,[ptr]),
            ('hb_ot_font_set_funcs',None,[ptr]),('hb_buffer_create',ptr,[]),
            ('hb_buffer_reset',None,[ptr]),
            ('hb_buffer_add_utf8',None,[ptr,C.c_char_p,C.c_int,C.c_uint,C.c_int]),
            ('hb_buffer_guess_segment_properties',None,[ptr]),
            ('hb_shape',None,[ptr,ptr,C.POINTER(Feature),C.c_uint]),
            ('hb_buffer_get_length',C.c_uint,[ptr]),
        ]
        declarations += [('hb_'+kind+'_destroy',None,[ptr]) for kind in ('buffer','font','face','blob')]
        for name,result,args in declarations:
            fn=getattr(self.lib,name);fn.restype=result;fn.argtypes=args

    def open(self,data):
        return Shaper(self.lib,data)


class Shaper:
    def __init__(self,hb,data):
        self.hb=hb
        # DUPLICATE mode: copying the already-resident font is included in setup.
        self.blob=hb.hb_blob_create(data,len(data),0,None,None)
        self.face=hb.hb_face_create(self.blob,0)
        self.font=hb.hb_font_create(self.face)
        hb.hb_ot_font_set_funcs(self.font)
        self.buffer=hb.hb_buffer_create()

    def shape(self,data,calt):
        hb=self.hb
        hb.hb_buffer_reset(self.buffer)
        hb.hb_buffer_add_utf8(self.buffer,data,len(data),0,len(data))
        hb.hb_buffer_guess_segment_properties(self.buffer)
        feature=Feature(int.from_bytes(b'calt','big'),int(calt),0,0xFFFFFFFF)
        hb.hb_shape(self.font,self.buffer,C.byref(feature),1)
        return hb.hb_buffer_get_length(self.buffer)

    def close(self):
        for kind in ('buffer','font','face','blob'):
            getattr(self.hb,'hb_'+kind+'_destroy')(getattr(self,kind))


def timing(fn,batches=5,iterations=1):
    samples=[]
    for _ in range(batches):
        start=time.perf_counter()
        for _ in range(iterations):fn()
        samples.append((time.perf_counter()-start)*1000/iterations)
    return dict(median_ms=round(statistics.median(samples),4),
                min_batch_ms=round(min(samples),4),max_batch_ms=round(max(samples),4))


def measure(label,path,hb,batches,iterations):
    data=path.read_bytes()  # Disk/network reads are outside all timed sections.
    with TTFont(BytesIO(data),lazy=True) as font:
        cmap=font.getBestCmap()
        tags=set(font.keys())
        info=dict(label=label,path=str(path),sha256=hashlib.sha256(data).hexdigest(),
                  file_bytes=len(data),format='CBDT' if 'CBDT' in tags else 'COLRv1' if 'COLR' in tags else 'other',
                  glyphs=font['maxp'].numGlyphs,mapped_codepoints=len(cmap),
                  gsub_bytes=font.reader.tables['GSUB'].length if 'GSUB' in tags else 0,
                  version=font['name'].getDebugName(5) if 'name' in tags else None)
    def directory():
        with TTFont(BytesIO(data),lazy=True):pass
    def layout():
        with TTFont(BytesIO(data),lazy=True) as font:
            font.getBestCmap()
            for tag in ('GSUB','GPOS'):
                if tag in font:font[tag].table.ensureDecompiled(recurse=True)
            if 'hmtx' in font:font['hmtx'].metrics
    def setup():
        font=hb.open(data);font.close()
    first=(CASES['short_clusters'][0]*CASES['short_clusters'][1]).encode()
    def cold():
        font=hb.open(data)
        try:font.shape(first,True)
        finally:font.close()
    info['fonttools_directory_open']=timing(directory,batches)
    info['fonttools_layout_decode']=timing(layout,batches)
    info['harfbuzz_setup']=timing(setup,batches)
    info['harfbuzz_cold_first_shape']=timing(cold,batches)
    info['shaping']={}
    font=hb.open(data)
    try:
        for name,(unit,repeats) in CASES.items():
            text=unit*repeats;utf8=text.encode()
            result=dict(codepoints=len(text),utf8_bytes=len(utf8),
                        unmapped_unique_codepoints=[f'{ord(c):04X}' for c in sorted(set(text)) if ord(c) not in cmap])
            for calt in (False,True):
                for _ in range(3):font.shape(utf8,calt)
                result['calt_on' if calt else 'calt_off']={
                    **timing(lambda:font.shape(utf8,calt),batches,iterations),
                    'output_glyphs':font.shape(utf8,calt)}
            info['shaping'][name]=result
    finally:font.close()
    return info


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--font',action='append',required=True,metavar='LABEL=PATH')
    p.add_argument('--batches',type=int,default=5)
    p.add_argument('--iterations',type=int,default=3)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--upstream-ref',help='Optional pinned upstream commit for provenance')
    a=p.parse_args()
    if min(a.batches,a.iterations)<1:p.error('Counts must be positive')
    hb=HarfBuzz();fonts=[];labels=set()
    for item in a.font:
        if '=' not in item:p.error('Each font needs LABEL=PATH')
        label,path=item.split('=',1)
        if label in labels:p.error('Font labels must be unique')
        labels.add(label)
        print('Benchmarking '+label,file=sys.stderr,flush=True)
        fonts.append(measure(label,Path(path),hb,a.batches,a.iterations))
    report=dict(schema=1,upstream_ref=a.upstream_ref,
                environment=dict(python=platform.python_version(),platform=platform.platform(),
                                 machine=platform.machine(),fonttools=fontTools.__version__,
                                 harfbuzz=hb.lib.hb_version_string().decode()),
                method=dict(batches=a.batches,iterations_per_warm_batch=a.iterations,warmups=3,
                            font_bytes='resident in memory; disk/network I/O excluded',
                            fonttools_layout='new font: cmap, GSUB, GPOS and hmtx decoding; includes directory open',
                            cold_shape='new HarfBuzz blob/face/font/buffer plus short_clusters, calt on; includes blob copy',
                            warm_shape='reuse font/shape plans; buffer reset, UTF-8 input, guessing segment properties and hb_shape',
                            limits='No rasterization, browser font fallback or screen painting. Native-cache fonts include existing zombie/sunflower assembly; output counts show differing behavior.'),
                cases={name:dict(unit=unit,repeat=n) for name,(unit,n) in CASES.items()},fonts=fonts)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    a.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(str(a.output))


if __name__=='__main__':main()

"""Trace Chromium layout, paint recording and raster work for unaffected emoji.

Fonts are loaded before timing. Wrapped 3,200-glyph samples fit entirely in the
viewport; no-wrap cases isolate layout and intentionally paint only the viewport.
Requires Playwright, Chromium, fontTools and Pillow. No fonts are modified.
"""
import argparse
from collections import defaultdict
from functools import partial
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import platform
import statistics
from threading import Thread
from urllib.parse import urlsplit

from fontTools.ttLib import TTFont
from PIL import Image
from playwright.sync_api import sync_playwright

HTML=b'''<!doctype html><meta charset="utf-8"><style>
html,body{margin:0;background:white}body{padding:16px}
.sample{font-size:32px;line-height:40px;width:1280px;word-break:normal}
</style><main id="host"></main>'''


LAYOUT_JS = '''async ({text,family,calt,wrapped,settings}) => {
        performance.clearMarks();performance.mark('render.begin');
        const t=performance.now();
        const node=document.createElement('div');node.className='sample';
        node.style.fontFamily=family;node.style.fontFeatureSettings=settings ?? `"calt" ${calt}`;
        if(!wrapped)node.style.whiteSpace='nowrap';
        node.textContent=text;document.getElementById('host').replaceChildren(node);
        const box=node.getBoundingClientRect();const layout=performance.now()-t;
        const allVisible=box.bottom<=innerHeight && node.scrollWidth<=1280;
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        return {forced_layout_ms:layout,two_raf_latency_ms:performance.now()-t,
                height:box.height,scroll_width:node.scrollWidth,all_visible:allVisible};
    }'''


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass
    def do_GET(self):
        path=urlsplit(self.path).path
        if path=='/':data=HTML;kind='text/html; charset=utf-8'
        elif path in self.server.fonts:
            data=self.server.fonts[path].read_bytes();kind='font/ttf'
        else:self.send_error(404);return
        self.send_response(200);self.send_header('Content-Type',kind)
        self.send_header('Content-Length',str(len(data)));self.end_headers();self.wfile.write(data)


def union_ms(intervals):
    end=None;total=0
    for start,stop in sorted(intervals):
        if end is None or start>end:total+=stop-start
        elif stop>end:total+=stop-end
        end=stop if end is None else max(end,stop)
    return total/1000


def trace_metrics(events):
    start=next(e for e in events if e.get('name')=='render.begin')
    finish=next(e for e in events if e.get('name')=='render.end')
    lo,hi=start['ts'],finish['ts'];main=(start['pid'],start['tid'])
    groups=defaultdict(lambda:defaultdict(list))
    selected={'Layout':'layout_trace_ms','UpdateLayoutTree':'style_trace_ms',
              'PrePaint':'prepaint_trace_ms','Paint':'paint_record_ms','RasterTask':'raster_cpu_ms'}
    for event in events:
        if event.get('ph')!='X' or event.get('name') not in selected:continue
        a=max(lo,event['ts']);b=min(hi,event['ts']+event.get('dur',0))
        thread=(event['pid'],event['tid'])
        if b<=a or (event['name']!='RasterTask' and thread!=main):continue
        groups[selected[event['name']]][thread].append((a,b))
    return {name:round(sum(union_ms(v) for v in groups[name].values()),4) for name in selected.values()}


def payload(count,nonce):
    glyphs='🐈🚗🍎📚';text=list((glyphs*((count+3)//4))[:count])
    # Unique text per trial prevents reuse of an identical whole-paragraph result.
    for i in range(min(6,count)):
        text[i]=glyphs[nonce%4];nonce//=4
    return ''.join(text)


def one_trial(page,cdp,text,family,calt,wrapped):
    complete=[]
    def done(event):complete.append(event)
    cdp.on('Tracing.tracingComplete',done)
    cdp.send('Tracing.start',dict(categories='devtools.timeline,blink.user_timing,disabled-by-default-devtools.timeline,disabled-by-default-devtools.timeline.frame',transferMode='ReturnAsStream'))
    result=page.evaluate(LAYOUT_JS,dict(text=text,family=family,calt=int(calt),wrapped=wrapped))
    pixels=page.screenshot(animations='disabled')
    page.evaluate("performance.mark('render.end')")
    cdp.send('Tracing.end')
    for _ in range(1000):
        if complete:break
        page.wait_for_timeout(10)
    if not complete:raise RuntimeError('Chromium tracing did not finish')
    handle=complete[0]['stream'];chunks=[]
    while True:
        part=cdp.send('IO.read',dict(handle=handle));chunks.append(part['data'])
        if part.get('eof'):break
    cdp.send('IO.close',dict(handle=handle));cdp.remove_listener('Tracing.tracingComplete',done)
    result.update(trace_metrics(json.loads(''.join(chunks))['traceEvents']))
    result['pixel_sha256']=sha256(Image.open(BytesIO(pixels)).convert('RGBA').tobytes()).hexdigest()
    if wrapped and not result['all_visible']:raise AssertionError('Wrapped sample is not entirely visible')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font',action='append',required=True,metavar='LABEL=PATH')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--chromium')
    parser.add_argument('--trials',type=int,default=3)
    args=parser.parse_args()
    if args.trials<1:parser.error('--trials must be positive')
    fonts=[]
    for item in args.font:
        label,path=item.split('=',1);path=Path(path).resolve();data=path.read_bytes()
        with TTFont(BytesIO(data),lazy=True) as font:
            assert set(map(ord,'🐈🚗🍎📚'))<=font.getBestCmap().keys(),label
        fonts.append(dict(label=label,path=str(path),sha256=sha256(data).hexdigest(),family=f'Bench{len(fonts)}'))
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    server.fonts={f'/font/{i}.ttf':Path(f['path']) for i,f in enumerate(fonts)}
    Thread(target=server.serve_forever,daemon=True).start()
    report=dict(schema=1,environment=dict(platform=platform.platform()),
                method=dict(font_size_px=32,line_height_px=40,text_width_px=1280,word_break='normal',
                            viewport=dict(width=1320,height=4200),device_scale_factor=1,
                            trials=args.trials,unit='🐈🚗🍎📚',counts=[36,3200],
                            baseline='Compare upstream and DEImoji; calt off is an additional within-font diagnostic',
                            warmup='Font loading and initial glyph drawing excluded; identical fonts reused, unique text per trial',
                            timing='Forced DOM layout plus separately traced main-thread paint recording and raster-worker CPU',
                            raster='Raster CPU sums worker time and can overlap main-thread work; do not add columns as wall time',
                            flush='Screenshot ensures raster completion; PNG encoding, readback and transport are excluded from selected trace metrics',
                            nowrap='Layout-only diagnostic: overflowing glyphs outside the viewport are not painted',
                            control='Additional 3200-glyph calt-on layout samples without tracing, in both wrapping modes',
                            limits='Headless Chromium in this environment, not a physical display or universal browser result'),fonts=[])
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=args.chromium,headless=True)
            page=browser.new_page(viewport={'width':1320,'height':4200},device_scale_factor=1)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            report['environment']['chromium']=browser.version
            gpu=browser.new_browser_cdp_session().send('SystemInfo.getInfo')['gpu']
            report['environment']['gpu_devices']=gpu.get('devices',[])
            page.evaluate('''async fonts => {
                for(let i=0;i<fonts.length;i++) {
                    const face=new FontFace(fonts[i].family,`url("/font/${i}.ttf")`);
                    await face.load();document.fonts.add(face);
                }
                await document.fonts.ready;
            }''',fonts)
            cdp=page.context.new_cdp_session(page)
            for font in fonts:
                print('Rendering '+font['label'],flush=True)
                # Prime both feature settings and the four colour-glyph caches.
                for mode in (0,1):
                    page.evaluate('''({family,mode}) => {
                        const e=document.createElement('div');e.className='sample';e.style.fontFamily=family;
                        e.style.fontFeatureSettings=`"calt" ${mode}`;e.textContent='🐈🚗🍎📚';
                        document.getElementById('host').replaceChildren(e);e.getBoundingClientRect();
                    }''',dict(family=font['family'],mode=mode))
                    page.screenshot()
                cases=[]
                for count in (36,3200):
                    for wrapped in (True,False):
                        samples={False:[],True:[]}
                        for trial in range(args.trials):
                            nonce=trial+1+(0 if wrapped else 64)
                            text=payload(count,nonce)
                            # Reverse order on alternate trials to reduce order bias.
                            for mode in ((False,True) if trial%2==0 else (True,False)):
                                sample=one_trial(page,cdp,text,font['family'],mode,wrapped)
                                sample.update(nonce=nonce,text_sha256=sha256(text.encode()).hexdigest())
                                samples[mode].append(sample)
                            if samples[False][-1]['pixel_sha256']!=samples[True][-1]['pixel_sha256']:
                                raise AssertionError(f"{font['label']}: calt changed unaffected pixels")
                        case=dict(count=count,wrapped=wrapped,pixels_identical=True)
                        for mode in (False,True):
                            medians={key:round(statistics.median(s[key] for s in samples[mode]),4)
                                     for key in samples[mode][0] if key.endswith('_ms')}
                            case['calt_on' if mode else 'calt_off']=dict(median=medians,samples=samples[mode])
                        cases.append(case)
                controls={}
                for wrapped in (True,False):
                    values=[]
                    for trial in range(args.trials):
                        nonce=trial+129+(0 if wrapped else 64)
                        result=page.evaluate(LAYOUT_JS,dict(text=payload(3200,nonce),family=font['family'],calt=1,wrapped=wrapped))
                        page.screenshot()  # Flush paint, outside the timed layout section.
                        values.append(result)
                    controls['wrapped' if wrapped else 'nowrap']=dict(
                        median_layout_ms=round(statistics.median(v['forced_layout_ms'] for v in values),4),samples=values)
                report['fonts'].append({**font,'cases':cases,'untraced_layout_control':controls})
            browser.close()
    finally:server.shutdown()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(args.output)


if __name__=='__main__':main()

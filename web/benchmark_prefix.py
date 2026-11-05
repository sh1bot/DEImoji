"""Prefix-anchored RTL entropy followed by the existing forward LFSRs.

Diagnostic fonts only. Source and pipeline metadata come from a published build.
"""
import argparse
from copy import deepcopy
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import statistics
from threading import Thread

from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.otBase import BaseTable
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen
from playwright.sync_api import sync_playwright
import benchmark_fonts as hbbench
import benchmark_rendering as render
from benchmark_passes import partition,settings,TAGS,offset_references,hb_diagnostics,seed_variant,css


def build_prefix(source,info,markers,target):
    font=TTFont(source,recalcBBoxes=False,recalcTimestamp=False)
    order=list(font.getGlyphOrder());tones=[order[i] for i in markers['tone_marker_gids']]
    genders=[order[i] for i in markers['gender_marker_gids']]
    names=['deimojiPrefixStart','deimojiPrefixAnchor']+[f'deimojiPrefix{i}' for i in range(5)]
    assert not set(names)&set(order)
    for name in names:
        font['hmtx'].metrics[name]=(0,0)
        if 'vmtx' in font:font['vmtx'].metrics[name]=(0,0)
        if 'glyf' in font:font['glyf'][name]=TTGlyphPen(None).glyph()
    font.setGlyphOrder(order+names);font['maxp'].numGlyphs=len(order)+len(names)
    start,anchor,*active=names
    table=font['GSUB'].table;lookups=table.LookupList.Lookup
    sources={g for t in lookups[info['roots']['expansion']['lookup']].SubTable for g in getattr(t,'ExtSubTable',t).mapping}
    lines=['languagesystem DFLT dflt;', '@any = ['+' '.join(order+names)+'];',
           '@source = ['+' '.join(g for g in order if g in sources)+'];',
           '@tone = ['+' '.join(tones)+'];','@gender = ['+' '.join(genders)+'];']
    for bucket in range(5):lines.append(f'@b{bucket} = ['+' '.join(g for g in order if g in sources and font.getGlyphID(g)%5==bucket)+'];')
    lines+=['lookup markStart {', 'ignore sub @any @source @tone\';',f"sub @source @tone' by {start};",'} markStart;',
            f'lookup dropAnchor {{ sub @tone by {anchor}; sub {start} by {anchor}; }} dropAnchor;',
            'lookup chooseAnchor useExtension {']
    for count in (16,8,4,2):
        tokens=[start,'@gender']+['@source','@tone','@gender']*(count-2)+['@source','@tone']
        lines.append('sub '+' '.join(token+"'" for token in tokens)+' lookup dropAnchor;')
    lines += [f"sub {start}' lookup dropAnchor;",'} chooseAnchor;',
              f'lookup resetStart {{ sub {start} by {tones[0]}; }} resetStart;',
              'lookup collectRTL useExtension {']
    for bucket in range(5):lines.append(f"rsub @b{bucket} {anchor}' by {active[-bucket%5]};")
    for bucket in range(5):
        for future in range(5):
            value=(2*future+bucket+1)%5
            lines.append(f"rsub @b{bucket} @tone' @gender @source {active[future]} by {active[value]};")
    lines+=['} collectRTL;','lookup finishPrefix {']
    for a,t in zip(active,tones):lines.append(f'sub {a} by {t};')
    lines+=['} finishPrefix;','feature ZZZZ { lookup markStart; lookup chooseAnchor; lookup resetStart; lookup collectRTL; lookup finishPrefix; } ZZZZ;']
    temp=TTFont();temp.setGlyphOrder(order+names)
    addOpenTypeFeaturesFromString(temp,'\n'.join(lines),tables=['GSUB'])
    extra=deepcopy(temp['GSUB'].table.LookupList.Lookup)
    stages=temp['GSUB'].table.FeatureList.FeatureRecord[0].Feature.LookupListIndex
    root=info['roots']['suffix_hash']['lookup'];delta=len(extra)-1
    def remap(value):
        if isinstance(value,list):
            for child in value:remap(child)
        elif isinstance(value,BaseTable):
            for key,child in vars(value).items():
                if key=='LookupListIndex':
                    assert child!=root
                    setattr(value,key,child+delta if child>root else child)
                else:remap(child)
    for lookup in lookups:remap(lookup)
    for record in table.FeatureList.FeatureRecord:
        indices=[]
        for index in record.Feature.LookupListIndex:indices.extend([root+s for s in stages] if index==root else [index+delta if index>root else index])
        record.Feature.LookupListIndex=indices;record.Feature.LookupCount=len(indices)
    for lookup in extra:offset_references(lookup,root)
    lookups[root:root+1]=extra;table.LookupList.LookupCount=len(lookups)
    font.save(target)
    return dict(path=str(target),sha256=sha256(target.read_bytes()).hexdigest(),temporary_gids=[font.getGlyphID(n) for n in names],hash_stage_indices=[root+s for s in stages])


def proof(hb,path,markers,temporary):
    text='🐈🚗🍎📚💡🐟🏠🚀'*3;checks=[]
    font=TTFont(path);cmap=font.getBestCmap();tone_ids=markers['tone_marker_gids'];values={g:i for i,g in enumerate(tone_ids)}
    shaper=hb.open(path.read_bytes())
    try:
        for length in (1,2,3,4,7,8,15,16,17,24):
            sample=text[:length];buckets=[font.getGlyphID(cmap[ord(c)])%5 for c in sample]
            reach=max(n for n in (1,2,4,8,16) if n<=length)
            expected=[0]*length;expected[reach-1]=-buckets[reach-1]%5
            for i in range(reach-2,-1,-1):expected[i]=(2*expected[i+1]+buckets[i]+1)%5
            glyphs,_=shaper.signature(sample.encode(),False,settings({'expansion','suffix_hash'}))
            actual=[values[g[0]] for g in glyphs if g[0] in values]
            assert actual==expected,(length,actual,expected)
            assert not any(g[0] in temporary for g in glyphs)
            checks.append(dict(length=length,anchor_source=reach,states=actual))
        glyphs,_=shaper.signature(('🏃'*40).encode(),False,settings(TAGS))
        assert not any(g[0] in set(temporary+tone_ids+markers['gender_marker_gids']) for g in glyphs)
        assert len({g[0] for g in glyphs})>5
    finally:shaper.close();font.close()
    return checks


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--site',type=Path,required=True);p.add_argument('--upstream',type=Path,required=True)
    p.add_argument('--work',type=Path,default=Path('build/pass-prefix'));p.add_argument('--output',type=Path,required=True);p.add_argument('--chromium',default='/usr/bin/chromium');p.add_argument('--trials',type=int,default=3)
    p.add_argument('--guard-only',action='store_true',help='Isolate the start-detection guard, without entropy collection')
    args=p.parse_args();args.work.mkdir(parents=True,exist_ok=True)
    meta=json.loads((args.site/'build.json').read_text());pub='DEImoji-COLRv1.ttf';markers=meta['modifiers'][pub];hb=hbbench.HarfBuzz()
    original=args.site/'fonts'/pub;diagnostic=args.work/'diagnostic.ttf';info=partition(original,meta,pub,diagnostic)
    prefix=args.work/'prefix.ttf';details=build_prefix(diagnostic,info,markers,prefix);checks=proof(hb,prefix,markers,details['temporary_gids'])
    local=args.work/'local.ttf';seed_variant(diagnostic,info,markers,'local',local)
    guard=args.work/'guard.ttf';f=TTFont(prefix,recalcBBoxes=False,recalcTimestamp=False)
    feature=next(r.Feature for r in f['GSUB'].table.FeatureList.FeatureRecord if r.FeatureTag=='DHSH')
    feature.LookupListIndex=[details['hash_stage_indices'][i] for i in (0,2)];feature.LookupCount=2
    f.save(guard);f.close()
    paths=[args.upstream/'Noto-COLRv1.ttf',original,local,prefix,guard]
    configs=[('upstream',0,{'calt':1}),('original_off',1,{'calt':0}),('original_on',1,{'calt':1}),('local_full',2,settings(TAGS)),('prefix_full',3,settings(TAGS)),('prefix_hash_only',3,settings({'expansion','suffix_hash','sweep'}))]
    if args.guard_only:configs=[('guard_full',4,settings(TAGS)),('guard_hash_only',4,settings({'expansion','suffix_hash','sweep'}))]
    report=dict(guard_only=args.guard_only,source_commit=meta['commit'],harfbuzz=hb.lib.hb_version_string().decode(),trials=args.trials,format='COLRv1',prefix=details,proof=checks,
                method='3200 glyphs, warmed fonts; layout excludes painting. Fresh text per trial prevents paragraph-cache reuse. Prefix anchor at longest available 16/8/4/2/1 source count; no entropy collection beyond anchor.',font_inputs=[dict(path=str(path),sha256=sha256(path.read_bytes()).hexdigest()) for path in paths],cases=[])
    ids=set(markers['tone_marker_gids']+markers['gender_marker_gids']+details['temporary_gids'])
    server=ThreadingHTTPServer(('127.0.0.1',0),render.Handler);server.fonts={f'/font/{i}.ttf':path for i,path in enumerate(paths)}
    Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=args.chromium,headless=True);report['chromium']=browser.version
            page=browser.new_page(viewport={'width':1320,'height':7000},device_scale_factor=1)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.evaluate('''async count=>{for(let i=0;i<count;i++){let f=new FontFace(`Bench${i}`,`url(/font/${i}.ttf)`);try{await f.load();}catch(e){throw new Error(`font ${i}: ${e}`);}document.fonts.add(f);}}''',len(paths))
            for kind in ('unaffected','runners'):
                for name,index,features in configs:
                    text=render.payload(3200,1) if kind=='unaffected' else '🏃'*3200
                    result,_=hb_diagnostics(hb,paths[index].read_bytes(),text,features,ids if index in (3,4) else ids-set(details['temporary_gids']))
                    assert result['private_markers_remaining']==0
                    entry=dict(input=kind,configuration=name,features=features,harfbuzz=result)
                    for wrapped in (True,False):
                        samples=[]
                        for trial in range(args.trials+1):
                            text=render.payload(3200,trial+1) if kind=='unaffected' else '🏃'*(trial+1)+'🏃\u200d♂️'+'🏃'*(3198-trial)
                            sample=page.evaluate(render.LAYOUT_JS,dict(text=text,family=f'Bench{index}',calt=0,wrapped=wrapped,settings=css(features)))
                            if wrapped:assert sample['all_visible']
                            if trial:samples.append(sample)
                        entry['wrapped' if wrapped else 'nowrap']=dict(median_layout_ms=statistics.median(s['forced_layout_ms'] for s in samples),samples=samples)
                    report['cases'].append(entry);print(kind,name,round(entry['wrapped']['median_layout_ms'],2),round(entry['nowrap']['median_layout_ms'],2),result['unsafe_to_break_glyphs'],flush=True)
            browser.close()
    finally:server.shutdown()
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')


if __name__=='__main__':main()

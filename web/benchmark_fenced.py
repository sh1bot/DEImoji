"""Keep entropy-block fences through both LFSRs; sweep before folding."""
import argparse,ctypes as C,json,statistics
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from threading import Thread
from http.server import ThreadingHTTPServer
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables.otBase import BaseTable
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.pens.ttGlyphPen import TTGlyphPen
from playwright.sync_api import sync_playwright
import benchmark_fonts as hbbench
import benchmark_rendering as render
from benchmark_passes import partition,settings,TAGS,offset_references,hb_diagnostics,css


def build(source,info,markers,span,target):
    assert span>=16 and span%16==0
    font=TTFont(source,recalcBBoxes=False,recalcTimestamp=False);order=list(font.getGlyphOrder())
    tones=[order[i] for i in markers['tone_marker_gids']];genders=[order[i] for i in markers['gender_marker_gids']]
    phases=[f'FencePhase{i}' for i in range(span//16)];active=[f'FenceActive{i}' for i in range(5)];ends=[f'FenceEnd{i}' for i in range(5)]
    fence='FenceBoundary';raw='FenceRaw';names=phases+active+ends+[fence,raw]
    for name in names:
        assert name not in order
        font['hmtx'].metrics[name]=(0,0)
        if 'vmtx' in font:font['vmtx'].metrics[name]=(0,0)
        font['glyf'][name]=TTGlyphPen(None).glyph()
    font.setGlyphOrder(order+names);font['maxp'].numGlyphs=len(order)+len(names)
    table=font['GSUB'].table;lookups=table.LookupList.Lookup
    sources={g for t in lookups[info['roots']['expansion']['lookup']].SubTable for g in getattr(t,'ExtSubTable',t).mapping}
    lines=['languagesystem DFLT dflt;','@source = ['+' '.join(g for g in order if g in sources)+'];',
           '@tone = ['+' '.join(tones)+'];','@gender = ['+' '.join(genders)+'];','@active = ['+' '.join(active+ends)+'];','@end = ['+' '.join(ends)+'];']
    for b in range(5):lines.append(f'@b{b} = ['+' '.join(g for g in order if g in sources and font.getGlyphID(g)%5==b)+'];')
    lines += [f'lookup drop {{ sub @tone by {raw}; }} drop;', 'lookup anchors useExtension {']
    for n in (16,8,4,2,1):lines.append('sub '+' '.join(t+"'" for t in ['@source','@tone','@gender']*(n-1)+['@source','@tone'])+' lookup drop;')
    lines += ['} anchors;']
    for i,p in enumerate(phases):lines.append(f'lookup phase{i} {{ sub {raw} by {p}; }} phase{i};')
    lines += ['lookup phases useExtension {']
    for i,p in enumerate(phases[:-1]):
        context=' '.join([p,'@gender']+['@source','@tone','@gender']*15+['@source'])
        lines.append(f"sub {context} {raw}' lookup phase{i+1};")
    lines += [f"sub {raw}' lookup phase0;",'} phases;', 'lookup collect useExtension {']
    for b in range(5):lines.append(f"rsub @b{b} {phases[-1]}' by {ends[-b%5]};")
    ordinary='['+' '.join(tones+phases[:-1])+']'
    for b in range(5):
        for future in range(5):
            following='['+active[future]+' '+ends[future]+']'
            lines.append(f"rsub @b{b} {ordinary}' @gender @source {following} by {active[(2*future+b+1)%5]};")
        for p in phases[:-1]:lines.append(f"rsub @b{b} {p}' by {active[-b%5]};")
    lines += ['} collect;', 'lookup insertFence {']
    for g in genders:lines.append(f'sub {g} by {g} {fence};')
    lines += ['} insertFence;',"lookup boundaries { sub @end @gender' lookup insertFence; } boundaries;",'lookup finish {']
    for a,t in zip(active,tones):lines.append(f'sub {a} by {t};')
    for a,t in zip(ends,tones):lines.append(f'sub {a} by {t};')
    lines += ['} finish;',f'lookup sweepFence {{ sub {fence} by NULL; }} sweepFence;',
              'feature ZZZZ { lookup anchors; lookup phases; lookup collect; lookup boundaries; lookup finish; } ZZZZ;',
              'feature YYYY { lookup sweepFence; } YYYY;']
    temp=TTFont();temp.setGlyphOrder(order+names);addOpenTypeFeaturesFromString(temp,'\n'.join(lines),tables=['GSUB'])
    extra=deepcopy(temp['GSUB'].table.LookupList.Lookup);features={r.FeatureTag:r.Feature.LookupListIndex for r in temp['GSUB'].table.FeatureList.FeatureRecord}
    # Insert hash stages at the old hash index and cleanup immediately before folding.
    root=info['roots']['suffix_hash']['lookup'];fold=info['roots']['folding']['lookup']
    # Extra lookups all occupy the old hash slot; cleanup activation is deferred by
    # placing a copy at the folding slot so HarfBuzz's numeric lookup order is correct.
    sweep=extra[features['YYYY'][0]];delta=len(extra)-1
    def shifted(index):return index+delta+(1 if index>=fold else 0) if index>root else index
    def remap(value):
        if isinstance(value,list):
            for child in value:remap(child)
        elif isinstance(value,BaseTable):
            for key,child in vars(value).items():
                if key=='LookupListIndex':
                    assert child!=root
                    setattr(value,key,shifted(child))
                else:remap(child)
    for lookup in lookups:remap(lookup)
    sweep_index=fold+delta
    for r in table.FeatureList.FeatureRecord:
        indices=[]
        for i in r.Feature.LookupListIndex:
            if i==root:indices.extend(root+s for s in features['ZZZZ'])
            else:
                if i==fold:indices.append(sweep_index)
                indices.append(shifted(i))
        r.Feature.LookupListIndex=indices;r.Feature.LookupCount=len(indices)
    for lookup in extra:offset_references(lookup,root)
    lookups[root:root+1]=extra;lookups.insert(sweep_index,deepcopy(sweep));table.LookupList.LookupCount=len(lookups)
    # Hash-only diagnostics must also sweep the fence; otherwise this is not valid output.
    r=next(r for r in table.FeatureList.FeatureRecord if r.FeatureTag=='DSWP')
    r.Feature.LookupListIndex.insert(0,sweep_index);r.Feature.LookupCount=len(r.Feature.LookupListIndex)
    font.save(target);font.close()
    return dict(path=str(target),sha256=sha256(target.read_bytes()).hexdigest(),span=span,temporary_gids=list(range(len(order),len(order)+len(names))),fence_gid=len(order)+names.index(fence))


def verify(hb,path,meta,detail):
    f=TTFont(path);cmap=f.getBestCmap();toneids=meta['tone_marker_gids'];genderids=meta['gender_marker_gids'];values={g:i for i,g in enumerate(toneids)}
    span=detail['span'];s=hb.open(path.read_bytes());checks=[]
    try:
        for length in (1,15,16,17,span-1,span,span+1,span*2+7):
            text=('🐈🚗🍎📚💡🐟🏠🚀'*100)[:length];buckets=[f.getGlyphID(cmap[ord(c)])%5 for c in text];expected=[0]*length
            start=0
            while start<length:
                size=min(span,length-start) if span>16 else max(n for n in (1,2,4,8,16) if n<=length-start)
                end=start+size;expected[end-1]=-buckets[end-1]%5
                for i in range(end-2,start-1,-1):expected[i]=(2*expected[i+1]+buckets[i]+1)%5
                start=end
            glyphs,_=s.signature(text.encode(),False,settings({'expansion','suffix_hash','folding'}))
            actual=[values[g[0]] for g in glyphs if g[0] in values]
            assert expected==actual,(span,length,actual,expected)
            assert not any(g[0] in detail['temporary_gids'] for g in glyphs)
            checks.append(length)
        # Inspect both raw state generators before folding/sweep. Chunked shaping
        # independently must give exactly the same state stream as the full run.
        text='🏃'*(span*2);features=settings({'expansion','suffix_hash','gender_seed','tone_feedback','gender_feedback'})
        def states(text):
            glyphs,_=s.signature(text.encode(),False,features)
            return [g[0] for g in glyphs if g[0] in set(toneids+genderids)]
        assert states(text)==states(text[:span])+states(text[span:]),span
        glyphs,_=s.signature(text.encode(),False,settings(TAGS))
        assert not any(g[0] in set(detail['temporary_gids']+toneids+genderids) for g in glyphs)
        assert len({g[0] for g in glyphs})>5
        count=C.c_uint();infos=hb.lib.hb_buffer_get_glyph_infos(s.buffer,C.byref(count))
        flags=hb.lib.hb_glyph_info_get_glyph_flags
        flags.restype=C.c_uint;flags.argtypes=[C.POINTER(hbbench.GlyphInfo)]
        safe=[i for i in range(count.value) if not flags(C.byref(infos[i]))&1]
        assert safe==[0,span],(span,safe)
    finally:s.close();f.close()
    return dict(lengths_checked=checks,both_generators_equal_independently_shaped_blocks=True,private_glyph_cleanup=True,safe_boundary_indices=safe)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--site',type=Path,required=True);p.add_argument('--upstream',type=Path,required=True);p.add_argument('--work',type=Path,default=Path('build/pass-fenced'));p.add_argument('--output',type=Path,required=True);p.add_argument('--chromium',default='/usr/bin/chromium');p.add_argument('--trials',type=int,default=3)
    args=p.parse_args();args.work.mkdir(parents=True,exist_ok=True);meta=json.loads((args.site/'build.json').read_text());markers=meta['modifiers']['DEImoji-COLRv1.ttf'];hb=hbbench.HarfBuzz()
    original=args.site/'fonts/DEImoji-COLRv1.ttf';diagnostic=args.work/'diagnostic.ttf';info=partition(original,meta,'DEImoji-COLRv1.ttf',diagnostic)
    paths=[args.upstream/'Noto-COLRv1.ttf',original];variants=[]
    for span in (16,32,64,128):
        target=args.work/f'fenced-{span}.ttf';detail=build(diagnostic,info,markers,span,target);detail['proof']=verify(hb,target,markers,detail);variants.append(detail);paths.append(target)
    configs=[('upstream',0,{'calt':1}),('original_off',1,{'calt':0}),('original_on',1,{'calt':1})]
    configs += [(f'fenced_{v["span"]}',i+2,settings(TAGS)) for i,v in enumerate(variants)]
    configs += [('fenced_64_hash_only',4,settings({'expansion','suffix_hash','sweep'}))]
    report=dict(source_commit=meta['commit'],harfbuzz=hb.lib.hb_version_string().decode(),trials=args.trials,format='COLRv1',variants=variants,font_inputs=[dict(path=str(p),sha256=sha256(p.read_bytes()).hexdigest()) for p in paths],cases=[],method='3200 glyphs; same warmed layout harness as prefix benchmark. Browser runner trials move one explicit male runner near start; HB uses plain runners. Fences persist through both generators and are swept before folding.')
    server=ThreadingHTTPServer(('127.0.0.1',0),render.Handler);server.fonts={f'/font/{i}.ttf':p for i,p in enumerate(paths)};Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as pw:
            browser=pw.chromium.launch(executable_path=args.chromium,headless=True);report['chromium']=browser.version;page=browser.new_page(viewport={'width':1320,'height':7000},device_scale_factor=1);page.goto(f'http://127.0.0.1:{server.server_port}/')
            page.evaluate('''async n=>{for(let i=0;i<n;i++){let f=new FontFace(`Bench${i}`,`url(/font/${i}.ttf)`);await f.load();document.fonts.add(f);}}''',len(paths))
            for kind in ('unaffected','runners'):
                for name,index,features in configs:
                    text=render.payload(3200,1) if kind=='unaffected' else '🏃'*3200
                    ids=set(markers['tone_marker_gids']+markers['gender_marker_gids']+(variants[index-2]['temporary_gids'] if index>=2 else []))
                    result,_=hb_diagnostics(hb,paths[index].read_bytes(),text,features,ids);assert result['private_markers_remaining']==0
                    entry=dict(input=kind,configuration=name,harfbuzz=result)
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

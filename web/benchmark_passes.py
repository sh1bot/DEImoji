"""Partition DEImoji GSUB roots into private features and benchmark ablations.

Diagnostic copies keep every lookup. Only feature activation changes. Never use
these copies as release fonts: the normal calt entry point is deliberately empty.
"""
import argparse
import ctypes as C
from copy import deepcopy
from hashlib import sha256
from http.server import ThreadingHTTPServer
from io import BytesIO
import json
import platform
from pathlib import Path
import statistics
from threading import Thread

from fontTools.ttLib import TTFont
from fontTools.feaLib.builder import addOpenTypeFeaturesFromString
from fontTools.ttLib.tables.otBase import BaseTable
from fontTools.ttLib.tables import otTables as ot
from PIL import Image
from playwright.sync_api import sync_playwright

import benchmark_fonts as hbbench
import benchmark_rendering as render

PASSES=(('clustering','DCLT'),('expansion','DEXP'),('suffix_hash','DHSH'),
        ('gender_seed','DGSD'),('tone_feedback','DTFB'),('gender_feedback','DGFB'),
        ('folding','DFLD'),('sweep','DSWP'),('assembly','DASM'))
TAGS=dict(PASSES)


def settings(enabled):
    return {'calt':0,**{tag:int(name in enabled) for name,tag in PASSES}}


def partition(source,metadata,published,target):
    data=source.read_bytes()
    if sha256(data).hexdigest()!=metadata['font_hashes'][published]:
        raise ValueError('Build metadata does not match the source font')
    font=TTFont(BytesIO(data),recalcBBoxes=False);font.flavor=None
    table=font['GSUB'].table;records=table.FeatureList.FeatureRecord
    calts=[r for r in records if r.FeatureTag=='calt']
    roots=metadata['modifiers'][published]['calt_roots']
    if len(calts)!=1 or len(roots)!=8:raise ValueError('Unknown calt pipeline')
    indices=calts[0].Feature.LookupListIndex
    if indices[-8:]!=roots or len(indices)!=9:raise ValueError('Unexpected clustering roots')
    indices=indices[:]
    old_records=records[:]
    calts[0].Feature.LookupListIndex=[];calts[0].Feature.LookupCount=0
    if set(TAGS.values()).intersection(r.FeatureTag for r in records):raise ValueError('Private feature collision')
    for (name,tag),index in zip(PASSES,indices):
        record=ot.FeatureRecord();record.FeatureTag=tag;record.Feature=ot.Feature()
        record.Feature.FeatureParams=None;record.Feature.LookupListIndex=[index];record.Feature.LookupCount=1
        records.append(record)
    records.sort(key=lambda r:r.FeatureTag)
    remap={i:records.index(record) for i,record in enumerate(old_records)}
    added=[i for i,r in enumerate(records) if r.FeatureTag in TAGS.values()]
    for record in table.ScriptList.ScriptRecord:
        script=record.Script
        languages=[lang.LangSys for lang in script.LangSysRecord]
        if script.DefaultLangSys is not None:languages.append(script.DefaultLangSys)
        for lang in languages:
            lang.FeatureIndex=sorted([remap[i] for i in lang.FeatureIndex]+added)
            lang.FeatureCount=len(lang.FeatureIndex)
            if lang.ReqFeatureIndex!=0xFFFF:lang.ReqFeatureIndex=remap[lang.ReqFeatureIndex]
    table.FeatureList.FeatureCount=len(records)
    target.parent.mkdir(parents=True,exist_ok=True);font.save(target)
    return dict(source=str(source),source_sha256=sha256(data).hexdigest(),diagnostic=str(target),
                diagnostic_sha256=sha256(target.read_bytes()).hexdigest(),
                roots={name:dict(tag=tag,lookup=index) for (name,tag),index in zip(PASSES,indices)})


def actual_subtables(lookup):
    for sub in lookup.SubTable:
        yield sub.ExtSubTable if lookup.LookupType==7 else sub


def offset_references(value,offset):
    if isinstance(value,list):
        for child in value:offset_references(child,offset)
    elif isinstance(value,BaseTable):
        for name,child in vars(value).items():
            if name=='LookupListIndex':setattr(value,name,child+offset)
            else:offset_references(child,offset)


def seed_variant(diagnostic,info,markers,mode,target):
    """Replace only the hash lookup at its original stage, retaining all others."""
    font=TTFont(diagnostic,recalcBBoxes=False,recalcTimestamp=False)
    order=font.getGlyphOrder();tones=[order[g] for g in markers['tone_marker_gids']]
    genders=[order[g] for g in markers['gender_marker_gids']]
    lookups=font['GSUB'].table.LookupList.Lookup
    expansion=lookups[info['roots']['expansion']['lookup']]
    sources={g for table in actual_subtables(expansion) for g in table.mapping}
    lines=['languagesystem DFLT dflt;',
           '@source = ['+' '.join(sorted(sources,key=font.getGlyphID))+'];',
           '@tone = ['+' '.join(tones)+'];','@gender = ['+' '.join(genders)+'];']
    for bucket in range(5):
        members=[g for g in order if g in sources and font.getGlyphID(g)%5==bucket]
        lines.append(f'@b{bucket} = ['+' '.join(members)+'];')
    for value,marker in enumerate(tones):
        lines.append(f'lookup set{value} {{ sub @tone by {marker}; }} set{value};')
    lines.append('lookup replacement useExtension {')
    if mode=='ltr':
        for bucket in range(5):
            for previous in range(5):
                result=(2*previous+bucket+1)%5
                lines.append(f"sub @source {tones[previous]} @gender @b{bucket} @tone' lookup set{result};")
    for bucket in range(5):
        lines.append(f"sub @b{bucket} @tone' lookup set{(-bucket)%5};")
    lines+=['} replacement;','feature ZZZZ { lookup replacement; } ZZZZ;']
    temp=TTFont();temp.setGlyphOrder(order)
    addOpenTypeFeaturesFromString(temp,'\n'.join(lines),tables=['GSUB'])
    extra=deepcopy(temp['GSUB'].table.LookupList.Lookup)
    root=temp['GSUB'].table.FeatureList.FeatureRecord[0].Feature.LookupListIndex[0]
    if root!=len(extra)-1:raise ValueError('Unexpected replacement helper ordering')
    offset=len(lookups)
    for lookup in extra:offset_references(lookup,offset)
    lookups[info['roots']['suffix_hash']['lookup']]=extra[root]
    lookups.extend(extra[:root]);font['GSUB'].table.LookupList.LookupCount=len(lookups)
    font.save(target)
    return dict(path=str(target),sha256=sha256(target.read_bytes()).hexdigest(),
                policy='prefix hash, mirror recurrence' if mode=='ltr' else 'local negative source bucket; no adjacent-source dependency')


def seeder_proof(hb,path,markers,mode):
    text='🐈🚗🍎📚💡🐟🏠🚀'*2
    with TTFont(path,lazy=True) as font:
        cmap=font.getBestCmap();buckets=[font.getGlyphID(cmap[ord(c)])%5 for c in text]
    expected=[]
    for bucket in buckets:
        expected.append((-bucket)%5 if mode=='local' or not expected else (2*expected[-1]+bucket+1)%5)
    shaper=hb.open(path.read_bytes())
    try:glyphs,_=shaper.signature(text.encode(),False,settings({'expansion','suffix_hash'}))
    finally:shaper.close()
    values={gid:i for i,gid in enumerate(markers['tone_marker_gids'])}
    actual=[values[g[0]] for g in glyphs if g[0] in values]
    if actual!=expected:raise AssertionError('Replacement seeder did not implement '+mode)
    return dict(text=text,source_buckets=buckets,expected_states=expected,actual_states=actual)


def feedback_proof(hb,data,markers):
    flags=settings({'expansion','tone_feedback','gender_feedback'})
    shaper=hb.open(data)
    try:glyphs,_=shaper.signature(('🏃'*12).encode(),False,flags)
    finally:shaper.close()
    tones={gid:i for i,gid in enumerate(markers['tone_marker_gids'])}
    genders={gid:i for i,gid in enumerate(markers['gender_marker_gids'])}
    t=[tones[g[0]] for g in glyphs if g[0] in tones]
    g=[genders[item[0]] for item in glyphs if item[0] in genders]
    if len(t)!=12 or len(g)!=12 or t[:4]!=[0]*4 or g[:4]!=[0]*4 or t[4]!=2 or g[4]!=1:
        raise AssertionError('Feedback did not execute from zero-initialized slots')
    return dict(enabled=['expansion','tone_feedback','gender_feedback'],tone_states=t,gender_states=g,
                interpretation='No RTL or gender seeding: feedback changes the fifth state; fold/sweep disabled only to inspect private slots')


def configurations(config_set):
    names=set(TAGS)
    result=[dict(name='diagnostic_off',enabled=[]),dict(name='full',enabled=sorted(names))]
    result += [dict(name='without_'+name,enabled=sorted(names-{name})) for name in TAGS]
    result += [dict(name='expansion_sweep',enabled=['expansion','sweep']),
               dict(name='clustering_only',enabled=['clustering'])]
    for name in ('suffix_hash','gender_seed','tone_feedback','gender_feedback','folding','assembly'):
        result.append(dict(name='expansion_'+name+'_sweep',enabled=['expansion',name,'sweep']))
    seeders=[dict(name='seed_'+mode+'_'+scope,enabled=sorted(names) if scope=='full' else ['expansion','suffix_hash','sweep'],font_role='seed_'+mode) for mode in ('ltr','local') for scope in ('full','hash_only')]
    return seeders if config_set=='seeders' else result if config_set=='ablation' else result+seeders


def hb_diagnostics(hb,data,text,features,marker_ids):
    shaper=hb.open(data)
    try:
        binary=text.encode();shaper.shape(binary,False,features)
        count=C.c_uint();infos=hb.lib.hb_buffer_get_glyph_infos(shaper.buffer,C.byref(count))
        getter=hb.lib.hb_glyph_info_get_glyph_flags
        getter.restype=C.c_uint;getter.argtypes=[C.POINTER(hbbench.GlyphInfo)]
        flags=[getter(C.byref(infos[i])) for i in range(count.value)]
        remaining=sum(infos[i].codepoint in marker_ids for i in range(count.value))
        glyphs,clusters=shaper.signature(binary,False,features)
        for _ in range(3):shaper.shape(binary,False,features)
        timing=hbbench.timing(lambda:shaper.shape(binary,False,features),3,3)
        return dict(**timing,glyphs=count.value,private_markers_remaining=remaining,
                    unsafe_to_break_glyphs=sum(bool(value&1) for value in flags)),(glyphs,clusters)
    finally:shaper.close()


def css(features):return ','.join(f'"{tag}" {int(value)}' for tag,value in features.items())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--site',type=Path,required=True)
    p.add_argument('--upstream',type=Path,required=True,help='Directory with the two pristine upstream TTFs')
    p.add_argument('--work',type=Path,default=Path('build/pass-ablation'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--chromium');p.add_argument('--trials',type=int,default=3)
    p.add_argument('--config-set',choices=('all','ablation','seeders'),default='all')
    args=p.parse_args()
    if args.trials<1:p.error('Trials must be positive')
    metadata=json.loads((args.site/'build.json').read_text());hb=hbbench.HarfBuzz()
    report=dict(schema=1,source_commit=metadata['commit'],passes=dict(PASSES),config_set=args.config_set,
                environment=dict(platform=platform.platform(),harfbuzz=hb.lib.hb_version_string().decode()),
                method=dict(count=3200,trials=args.trials,font_size_px=32,
                            control='Upstream, original on/off, and partitioned off/full; lookup tables are retained',
                            features='Each root is exposed as a separate private feature, in original lookup order',
                            dependencies='Removing expansion makes marker-dependent passes inapplicable. Minimal expansion+pass+sweep cases test them independently.',
                            cleanup='without_sweep intentionally retains private zero-advance glyphs: invalid final output, diagnostic only',
                            visibility='Wrapped samples entirely visible; nowrap is layout-only; glyph caches warm',
                            seeders='LTR and local replacements preserve valid slots but deliberately change seeding policy; each is installed at the original hash stage',
                            flags='unsafe_to_break counts from HarfBuzz default buffer flags, before signature/timing calls'),fonts=[])
    files={};plans=[]
    for fmt,published,upstream in [('colr','DEImoji-COLRv1.ttf','Noto-COLRv1.ttf'),('cbdt','DEImoji-CBDT.ttf','NotoColorEmoji.ttf')]:
        original=args.site/'fonts'/published;diagnostic=args.work/(fmt+'-diagnostic.ttf')
        info=partition(original,metadata,published,diagnostic)
        marker_ids=set(metadata['modifiers'][published]['tone_marker_gids']+metadata['modifiers'][published]['gender_marker_gids'])
        original_data=original.read_bytes();diagnostic_data=diagnostic.read_bytes()
        # Prove all features preserve actual shaping, including affected sequences.
        a=hb.open(original_data);b=hb.open(diagnostic_data)
        try:
            for text in ('🐈🚗🍎📚'*20,'🏃'*40,'💩'*23+'🌻'*40,'🧟'*100,'🏃🏽\u200d♀️👍🏿'):
                if a.signature(text.encode(),True)!=b.signature(text.encode(),False,settings(TAGS)):
                    raise AssertionError('Partition changed full-pipeline shaping: '+fmt)
        finally:a.close();b.close()
        markers=metadata['modifiers'][published]
        seeding={}
        paths=dict(upstream=args.upstream/upstream,original=original,diagnostic=diagnostic)
        for mode in ('ltr','local'):
            target=args.work/(fmt+'-'+mode+'.ttf')
            seeding[mode]=seed_variant(diagnostic,info,markers,mode,target)
            paths['seed_'+mode]=target
            seeding[mode]['proof']=seeder_proof(hb,target,markers,mode)
        proof=feedback_proof(hb,diagnostic_data,markers)
        shaper=hb.open(diagnostic_data)
        try:reference=shaper.signature(('🐈🚗🍎📚'*800).encode(),False,settings(set()))
        finally:shaper.close()
        cases=[]
        for config in configurations(args.config_set):
            enabled=set(config['enabled']);features=settings(enabled)
            variant_data=paths[config.get('font_role','diagnostic')].read_bytes()
            result,signature=hb_diagnostics(hb,variant_data,'🐈🚗🍎📚'*800,features,marker_ids)
            if config['name']=='diagnostic_off':reference=signature
            result['outputs_identical']=signature==reference
            result['valid_cleanup']=result['private_markers_remaining']==0
            if config['name']!='without_sweep' and not result['outputs_identical']:
                raise AssertionError('Unexpected changed unaffected output: '+config['name'])
            cases.append({**config,'features':features,'harfbuzz':result})
        families={}
        for role,path in paths.items():
            index=len(files);files[f'/font/{index}.ttf']=path
            families[role]=f'Bench{index}'
        plans.append(dict(format=fmt,info=info,cases=cases,families=families,paths=paths,seeding=seeding,proof=proof))
    server=ThreadingHTTPServer(('127.0.0.1',0),render.Handler);server.fonts=files
    Thread(target=server.serve_forever,daemon=True).start()
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=args.chromium,headless=True)
            page=browser.new_page(viewport={'width':1320,'height':4200},device_scale_factor=1)
            page.goto(f'http://127.0.0.1:{server.server_port}/')
            families=[family for plan in plans for family in plan['families'].values()]
            page.evaluate('''async families => {for(let i=0;i<families.length;i++) {
                const f=new FontFace(families[i],`url("/font/${i}.ttf")`);await f.load();document.fonts.add(f);
            }await document.fonts.ready;}''',families)
            report['chromium']=browser.version
            for plan in plans:
                print('Ablating '+plan['format'],flush=True)
                # Original controls are measured alongside the partitioned variants.
                browser_cases=[dict(name='upstream',role='upstream',features={'calt':1}),
                               dict(name='original_off',role='original',features={'calt':0}),
                               dict(name='original_on',role='original',features={'calt':1})]
                browser_cases += [dict(name=c['name'],role=c.get('font_role','diagnostic'),features=c['features']) for c in plan['cases']]
                results=[]
                for case_index,case in enumerate(browser_cases):
                    print(plan['format']+' '+case['name'],flush=True)
                    family=plan['families'][case['role']]
                    # Warm every feature configuration before timed measurements.
                    page.evaluate(render.LAYOUT_JS,dict(text='🐈🚗🍎📚',family=family,calt=0,wrapped=True,settings=css(case['features'])))
                    page.screenshot()
                    measurements={}
                    for wrapped in (True,False):
                        samples=[]
                        for trial in range(args.trials):
                            nonce=1+trial+case_index*16+(0 if wrapped else 1024)
                            text=render.payload(3200,nonce)
                            sample=page.evaluate(render.LAYOUT_JS,dict(text=text,family=family,calt=0,wrapped=wrapped,settings=css(case['features'])))
                            pixels=page.screenshot()
                            if wrapped and not sample['all_visible']:raise AssertionError('Sample not fully visible')
                            # Check against the same text in the original font, rules off.
                            page.evaluate(render.LAYOUT_JS,dict(text=text,family=plan['families']['original'],calt=0,wrapped=wrapped))
                            baseline=page.screenshot()
                            if case['role']!='upstream':
                                if Image.open(BytesIO(pixels)).convert('RGBA').tobytes()!=Image.open(BytesIO(baseline)).convert('RGBA').tobytes():
                                    raise AssertionError('Changed unaffected pixels: '+case['name'])
                            sample['nonce']=nonce;samples.append(sample)
                        measurements['wrapped' if wrapped else 'nowrap']=dict(
                            median_layout_ms=round(statistics.median(s['forced_layout_ms'] for s in samples),4),samples=samples)
                    results.append({**case,'measurements':measurements})
                report['fonts'].append(dict(format=plan['format'],**plan['info'],
                                            font_inputs={role:dict(path=str(path),sha256=sha256(path.read_bytes()).hexdigest()) for role,path in plan['paths'].items()},
                                            all_on_matches_original=True,feedback_without_rtl=plan['proof'],seeding_variants=plan['seeding'],harfbuzz_cases=plan['cases'],browser_cases=results))
            browser.close()
    finally:server.shutdown()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(args.output)


if __name__=='__main__':main()

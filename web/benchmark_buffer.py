"""Compare fresh, preallocated and reused HarfBuzz buffers; no font changes."""
import argparse
import ctypes as C
import json
from hashlib import sha256
from pathlib import Path
import statistics
import time

from benchmark_fonts import HarfBuzz
from benchmark_passes import PASSES, settings


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--font',type=Path,required=True,help='Partitioned diagnostic font')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--trials',type=int,default=25)
    args=parser.parse_args()
    hb=HarfBuzz()
    preallocate=hb.lib.hb_buffer_pre_allocate
    preallocate.restype=C.c_int
    preallocate.argtypes=[C.c_void_p,C.c_uint]
    data=args.font.read_bytes();text=('🐈🚗🍎📚'*800).encode()
    cases={'off':set(),'expansion_sweep':{'expansion','sweep'},
           'expansion_hash_sweep':{'expansion','suffix_hash','sweep'},
           'full':{name for name,_ in PASSES}}
    result={'harfbuzz':hb.lib.hb_version_string().decode(),'font':str(args.font),
            'font_sha256':sha256(data).hexdigest(),'input_glyphs':3200,'preallocated_capacity':12800,'trials':args.trials,
            'method':'Fresh font/buffer setup and preallocation outside timer; shape includes reset/add_utf8. Reused buffers warmed three times. Paired fresh/preallocated order alternates.',
            'cases':{}}
    for name,enabled in cases.items():
        features=settings(enabled);samples={k:[] for k in ('fresh','preallocated','reused')}
        for trial in range(args.trials):
            for mode in (('fresh','preallocated') if trial%2==0 else ('preallocated','fresh')):
                shaper=hb.open(data)
                try:
                    if mode=='preallocated':assert preallocate(shaper.buffer,12800)
                    start=time.perf_counter_ns();count=shaper.shape(text,False,features)
                    samples[mode].append((time.perf_counter_ns()-start)/1e6)
                    assert count==3200
                finally:shaper.close()
        shaper=hb.open(data)
        try:
            for _ in range(3):shaper.shape(text,False,features)
            for _ in range(args.trials):
                start=time.perf_counter_ns();shaper.shape(text,False,features)
                samples['reused'].append((time.perf_counter_ns()-start)/1e6)
        finally:shaper.close()
        result['cases'][name]={mode:{'median_ms':statistics.median(values),'samples_ms':values} for mode,values in samples.items()}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({name:{mode:round(value['median_ms'],3) for mode,value in modes.items()} for name,modes in result['cases'].items()},indent=2))


if __name__=='__main__':main()

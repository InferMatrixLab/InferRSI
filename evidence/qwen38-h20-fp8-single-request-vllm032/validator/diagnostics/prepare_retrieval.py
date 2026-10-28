"""Deterministic proposed retrieval inputs; preparation does not activate gates."""
import argparse
import gzip
import hashlib
import importlib.metadata
import json
from pathlib import Path
from transformers import AutoTokenizer


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ident(text):
    return hashlib.sha256(('inferrsi-retrieval-v1:'+text).encode()).hexdigest()[:12].upper()


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--model', required=True);p.add_argument('--output', required=True)
    args=p.parse_args()
    model=Path(args.model);out=Path(args.output);out.mkdir(parents=True,exist_ok=False)
    assert digest(model/'config.json') == '74227dd615bf1ea975aa676bdf355a0379858c12f394b5365cd9dfa5fc2c70bc'
    tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True)
    encode=lambda text:tokenizer.encode(text,add_special_tokens=False)
    cases=[];manifest=[]
    for length in (8192,65536,131072):
        for index in range(10):
            case=f'retrieval-n{length}-s{index}'
            keys=['KEY_'+ident(case+':key:'+str(i)) for i in range(4)]
            values=['VAL_'+ident(case+':value:'+str(i)) for i in range(4)]
            query='Return one JSON object and nothing else. For each requested key, copy its recorded value exactly. Requested keys: '+', '.join(keys)+'.'
            message='Read this archive of independent records. Each record associates a key with a value. Ignore unrelated records.\nARCHIVE_START\n__ARCHIVE_BODY__\nARCHIVE_END\n'+query
            template=tokenizer.apply_chat_template([{'role':'user','content':message}],tokenize=False,add_generation_prompt=True,enable_thinking=False)
            assert template.count('__ARCHIVE_BODY__')==1
            prefix,suffix=map(encode,template.split('__ARCHIVE_BODY__'))
            filler=''.join('\nRecord KEY_D'+ident(case+':decoy-key:'+str(i))+' has value VAL_D'+ident(case+':decoy-value:'+str(i))+'. This record is independent of all other records.\n' for i in range(128))
            filler_ids=encode(filler); tokens=list(prefix);placements=[];cursor=0
            def pad(count):
                nonlocal cursor
                assert count>=0
                for _ in range(count):
                    tokens.append(filler_ids[cursor%len(filler_ids)]);cursor+=1
            for i,percent in enumerate((10,35,65,90)):
                position=length*percent//100
                pad(position-len(tokens))
                needle='\nRecord '+keys[i]+' has value '+values[i]+'.\n'
                needle_ids=encode(needle);tokens.extend(needle_ids)
                placements.append({'index':i,'target_percent':percent,'record_start_token':position,'record_tokens':len(needle_ids),'key':keys[i],'value':values[i]})
            pad(length-len(suffix)-len(tokens));tokens.extend(suffix)
            assert len(tokens)==length
            decoded=tokenizer.decode(tokens,skip_special_tokens=False)
            assert all(decoded.count(k)==2 for k in keys)
            assert all(decoded.count(v)==1 for v in values)
            for row in placements:
                start=row['record_start_token'];end=start+row['record_tokens']
                assert tokenizer.decode(tokens[start:end])=='\nRecord '+row['key']+' has value '+row['value']+'.\n'
            token_sha=hashlib.sha256(json.dumps(tokens,separators=(',',':')).encode()).hexdigest()
            row={'id':case,'input_tokens':length,'input_ids':tokens,'input_ids_sha256':token_sha,'expected':dict(zip(keys,values)),'placements':placements,'max_output_tokens':2048,'ignore_eos':False,'temperature':0,'thinking':False}
            cases.append(row);manifest.append({k:v for k,v in row.items() if k!='input_ids'})
    with (out/'inputs.jsonl').open('x') as f:
        for row in cases:f.write(json.dumps(row,separators=(',',':'))+'\n')
    with (out/'inputs.jsonl.gz').open('xb') as f:
        with gzip.GzipFile(filename='',fileobj=f,mode='wb',mtime=0) as z:z.write((out/'inputs.jsonl').read_bytes())
    report={'schema':'retrieval-proposal-v1','status':'PROPOSED_NOT_ACTIVATED','cases':manifest,'generator_sha256':digest(__file__),'inputs_sha256':digest(out/'inputs.jsonl'),'compressed_sha256':digest(out/'inputs.jsonl.gz'),'tokenizer_files':{p.name:digest(p) for p in sorted(model.iterdir()) if p.name in ('tokenizer.json','tokenizer_config.json','chat_template.jinja','special_tokens_map.json','config.json')},'transformers':importlib.metadata.version('transformers'),'extraction':'Strip whitespace; optionally unwrap one enclosing json code fence; json.loads entire remaining response; require exactly the four expected keys, all string values. Duplicate JSON keys are rejected. Exact string equality; no case folding or substring matching.','gate_status':'baseline qualification and owner approval pending'}
    (out/'manifest.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k!='cases'}),flush=True)
    print(json.dumps({'prepared_cases':len(cases),'input_tokens':sum(len(r['input_ids']) for r in cases),'all_exact_lengths_and_placements':True}),flush=True)


if __name__=='__main__':main()

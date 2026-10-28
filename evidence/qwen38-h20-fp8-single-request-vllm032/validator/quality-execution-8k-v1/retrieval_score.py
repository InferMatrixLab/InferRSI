"""Unchanged four-position JSON scorer from the reviewed retrieval baseline v3."""
import json

def score_response(text, expected):
    def unique(pairs):
        result={}
        for key,value in pairs:
            if key in result: raise ValueError('duplicate_key')
            result[key]=value
        return result
    body=text.strip()
    if body.startswith('```json\n') and body.endswith('\n```'):
        body=body[8:-4].strip()
    try:
        parsed=json.loads(body,object_pairs_hook=unique)
        shape_valid=isinstance(parsed,dict) and set(parsed)==set(expected) and all(isinstance(v,str) for v in parsed.values())
    except (ValueError,TypeError):
        parsed={};shape_valid=False
    matches=[isinstance(parsed,dict) and isinstance(parsed.get(key),str) and parsed.get(key)==value for key,value in expected.items()]
    return {'shape_valid':shape_valid,'position_matches':matches,'complete':shape_valid and all(matches)}

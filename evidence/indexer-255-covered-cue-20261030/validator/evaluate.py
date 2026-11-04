"""Frozen single paired CPU retrieval capture; no rewriting or candidate implementation."""
import gzip
import hashlib
import json
import sys
from fractions import Fraction
from pathlib import Path

root, prep, output = (Path(x).resolve() for x in sys.argv[1:])
sys.path.insert(0, str(root / 'src'))
from inferrsi.knowledge_operations import KnowledgeReader
from inferrsi._skill_selection import indexed_skill


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write(name, value):
    (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


freeze = json.loads((prep / 'input-freeze.json').read_text())
for path, expected in freeze['files'].items():
    assert sha((prep / path).read_bytes()) == expected
source = json.loads((prep / 'source-manifest.json').read_text())['files']
assert all(sha((root / path).read_bytes()) == digest for path, digest in source.items())
cases = json.loads((prep / 'evaluation-inputs.json').read_text())['cases']
rows = []
errors = []
for case in cases:
    assert sha((root / case['evidence_path']).read_bytes()) == case['source_sha256']
    pair = {'id': case['id'], 'identity_control': case['identity_control'], 'arms': {}}
    for arm, field in (('raw', 'raw_task'), ('cue', 'cue')):
        try:
            reader = KnowledgeReader()
            result = reader.collect(query=case['query'], relevance=case[field],
                                    limit=case['limit'], context_bytes=case['context_bytes'],
                                    **case['filters'])
            data = encode(result)
            name = case['id'] + '-' + arm + '.json.gz'
            (output / name).write_bytes(gzip.compress(data, mtime=0))
            ids = [item['id'] for item in result['items']]
            rank = next((i + 1 for i, identity in enumerate(ids)
                         if identity in case['relevant_ids']), None)
            complete = []
            audited = 0
            for context in result['contexts']:
                bundle = reader.read(context['ref'], revision=context['revision'])
                view = {**bundle.view(), 'authority': 'package'}
                _, required, _ = indexed_skill(reader.records()[view['id']], view, bundle.content)
                emitted = {r['path']: r for r in context['resources']}
                assert all(path in emitted for path in required)
                assert all(r['content'].encode() == bundle.content[path]
                           and r['sha256'] == sha(bundle.content[path])
                           for path, r in emitted.items())
                assert context['content_bytes'] == sum(len(r['content'].encode())
                                                       for r in emitted.values())
                audited += 1
                if view['id'] in case['relevant_ids']:
                    complete.append(view['id'])
            assert result['context_bytes'] == sum(c['content_bytes'] for c in result['contexts'])
            assert result['context_bytes'] <= case['context_bytes']
            for omission in result['context_omissions']:
                if omission['reason'] == 'context_limit':
                    assert omission['required_bytes'] > omission['available_bytes']
            pair['arms'][arm] = dict(rank=rank, ids=ids, complete_relevant=complete,
                                    audited_contexts=audited, output_bytes=len(data),
                                    context_bytes=result['context_bytes'],
                                    context_omissions=result['context_omissions'],
                                    sha256=sha(data), artifact=name)
        except Exception as exc:
            errors.append(dict(case=case['id'], arm=arm, type=type(exc).__name__, message=str(exc)))
    rows.append(pair)
    write('partial-results.json', {'rows': rows, 'errors': errors})

captures = []
for arm in ('raw', 'cue'):
    reader = KnowledgeReader()
    identity = 'inferrsi.common.skills.cgroup_resource_controls'
    values = []
    for options in ({}, {'relevance': 'cgroupv2', 'context_bytes': 262144},
                    {'query': 'stat.loc', 'relevance': 'cgroupv2'},
                    {'relevance': 'gpu', 'backend': 'ascend'},
                    {'ids': [identity], 'relevance': 'ram', 'context_bytes': 262144},
                    {'ids': [identity], 'relevance': 'ram', 'context_bytes': 1}):
        data = encode(reader.collect(**options))
        values.append({'options': options, 'sha256': sha(data), 'bytes': len(data)})
    captures.append(values)
write('default-captures.json', {'raw': captures[0], 'cue': captures[1]})
source_same = all(sha((root / path).read_bytes()) == digest for path, digest in source.items())
metrics = {}
gates = {}
if not errors:
    for arm in ('raw', 'cue'):
        ranks = [row['arms'][arm]['rank'] for row in rows]
        metrics[arm] = {'hit': sum(rank is not None for rank in ranks),
                        'mrr_exact': str(sum((Fraction(1, r) if r else Fraction(0)
                                              for r in ranks), Fraction(0)) / len(ranks)),
                        'complete_relevant': sum(len(row['arms'][arm]['complete_relevant'])
                                                 for row in rows)}
    gates = {'no_hit_lost': all(not row['arms']['raw']['rank'] or row['arms']['cue']['rank']
                              for row in rows),
             'hit_nondecreasing': metrics['cue']['hit'] >= metrics['raw']['hit'],
             'mrr_strictly_greater': Fraction(metrics['cue']['mrr_exact']) >
                                    Fraction(metrics['raw']['mrr_exact']),
             'complete_nondecreasing': metrics['cue']['complete_relevant'] >=
                                       metrics['raw']['complete_relevant'],
             'identity_control_parity': all(row['arms']['raw']['sha256'] ==
                                           row['arms']['cue']['sha256'] for row in rows
                                           if row['identity_control']),
             'default_parity': captures[0] == captures[1], 'resource_audits': True}
verdict = 'INCONCLUSIVE' if errors or not source_same else ('PASS' if all(gates.values()) else 'FAIL')
write('results.json', {'verdict': verdict, 'metrics': metrics, 'gates': gates,
                       'source_unchanged': source_same, 'rows': rows, 'errors': errors})
print(json.dumps({'verdict': verdict, 'metrics': metrics, 'gates': gates, 'errors': errors}))

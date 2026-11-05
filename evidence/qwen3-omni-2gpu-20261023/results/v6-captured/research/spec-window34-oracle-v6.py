"""Exact CPU W3/W4 round oracle. No RNG, torch, GPU or performance claims."""
from fractions import Fraction as F
from itertools import product
from collections import defaultdict
from pathlib import Path
import hashlib,json

def valid(p):
 assert sum(p)==1 and all(x>=0 for x in p)
 return p

def target_completion(target,prefix,remaining):
 if remaining==0:return {tuple(prefix):F(1)}
 out=defaultdict(F)
 for token,mass in enumerate(valid(target(tuple(prefix)))):
  if mass:
   for seq,p in target_completion(target,prefix+[token],remaining-1).items():out[seq]+=mass*p
 return dict(out)

def round_distribution(target,proposal,window,total):
 """One speculative round then target continuation to a fixed total length.

 q(prefix,j) may ignore intermediate draft tokens or condition on them.
 Pre-generate all drafts; after first rejection all later drafts are discarded.
 remaining<window uses remaining-1 drafts plus one bonus; remaining1 uses target.
 """
 assert window in (3,4) and total>=1
 n_draft=min(window-1,total-1)
 drafted=[((),F(1),())]
 for j in range(n_draft):
  nxt=[]
  for tokens,weight,qs in drafted:
   q=valid(proposal(tokens,j))
   for token,p in enumerate(q):
    if p:nxt.append((tokens+(token,),weight*p,qs+(q,)))
  drafted=nxt
 out=defaultdict(F);lengths=defaultdict(F)
 def finish(prefix,weight,emitted):
  lengths[emitted]+=weight
  for seq,p in target_completion(target,list(prefix),total-len(prefix)).items():out[seq]+=weight*p
 for drafts,weight,qs in drafted:
  prefix=();survival=weight
  for j,draft in enumerate(drafts):
   p=valid(target(prefix));q=qs[j]
   assert q[draft]>0 # impossible zero-support drafts never enumerated
   accept=min(F(1),p[draft]/q[draft]);rejected=survival*(1-accept)
   if rejected:
    residual=[max(a-b,F(0)) for a,b in zip(p,q)];z=sum(residual)
    assert z>0
    for token,mass in enumerate(residual):
     if mass:
      assert p[token]>q[token]
      # Crucially do not append any pre-generated suffix after rejection.
      finish(prefix+(token,),rejected*mass/z,j+1)
   survival*=accept;prefix+=(draft,)
   if not survival:break
  if survival:
   for bonus,mass in enumerate(valid(target(prefix))):
    if mass:finish(prefix+(bonus,),survival*mass,len(prefix)+1)
 assert sum(out.values())==sum(lengths.values())==1
 return dict(out),dict(lengths)

def check():
 families=[(F(1),F(0)),(F(0),F(1)),(F(1,2),F(1,2)),(F(1,4),F(3,4))]
 counts=defaultdict(int)
 for window in (3,4):
  for total in (1,2,3,4,5):
   for first,second in product(families,repeat=2):
    def target(prefix,a=first,b=second):return a if (len(prefix)+sum(prefix))%2==0 else b
    expected=target_completion(target,[],total)
    for proposal_row in families:
     # All depth proposals ignore intermediate drafts (common anchor model).
     proposal=lambda prefix,j,q=proposal_row:q
     actual,lengths=round_distribution(target,proposal,window,total)
     assert actual==expected
     counts['fixed_proposal_cases']+=1
     counts['tail_'+str(total)+'_cases']+=total<window
    # Exact target conditional proposal: all drafts accepted, even with zeros.
    actual,lengths=round_distribution(target,lambda prefix,j:target(prefix),window,total)
    assert actual==expected and lengths=={min(window,total):F(1)}
    counts['conditional_p_equals_q_cases']+=1
 # Explicit disjoint support: rejection at first draft emits exactly one.
 for window in (3,4):
  actual,lengths=round_distribution(lambda p:(F(1),F(0)),lambda p,j:(F(0),F(1)),window,5)
  assert actual=={(0,)*5:F(1)} and lengths=={1:F(1)}
  counts['explicit_disjoint_cases']+=1
 return {'status':'PASS','scope':'Exact Fraction algorithm distribution only; no finite precision/RNG/model/performance evidence','counts':dict(counts),'total_cases':sum(counts[k] for k in ['fixed_proposal_cases','conditional_p_equals_q_cases','explicit_disjoint_cases']),'limitations':['One round plus exact ordinary target continuation; equality composes across repeated rounds','Binary vocabulary and history-dependent target fixtures; finite enumeration supplements standard acceptance/residual proof','No head/position/BF16/native filter or actual sampler integration tested','Proposals may ignore intermediate drafts; each verifier p conditions on accepted prefix','Tail uses remaining-1 drafts plus bonus; other valid tail policies need separate tests']}

if __name__=='__main__':
 result=check();result['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
 with Path(__file__).with_name('spec-window34-oracle-v6-results.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
 print(json.dumps(result))

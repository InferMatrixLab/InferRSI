# Zero-support proposal extension — exact CPU oracle

New independent script/results; original prototype and results unchanged. Status PASS only for exact rational algebra, not native numerical/RNG/model equivalence.

Let p,q be any nonnegative normalized finite distributions. A draw from q never visits q(v)=0, so the algorithm skips those entries before evaluating p(v)/q(v). Accepted mass at v is min(p(v),q(v)), including zero when q(v)=0. Total rejection mass Z=sum(q-p)_+=sum(p-q)_+ follows from sum(p-q)=0. If Z>0, correction samples r(v)=(p(v)-q(v))_+/Z; therefore accepted plus corrected mass is min(p(v),q(v))+(p(v)-q(v))_+=p(v). In particular q(v)=0<p(v) is recovered through correction, without dividing by q(v). Correction has support only where p>q.

If Z=0, nonnegative positive parts all vanish and normalization implies p=q. Every possible draft is accepted; no correction normalization executes. Zero-probability entries are skipped, so p=q with zeros also avoids 0/0. Disjoint supports imply acceptance mass0 and Z=1, making correction exactly p.

An accepted draft receives a bonus from the actual target next-depth conditional. A rejected draft emits only the corrected token for that round; ordinary target continuation then supplies the next token. The completed two-token law is p(v)p2(w|v); it is not a claim that rejection emits a bonus in the same round. remaining=1 bypasses speculation and returns p.

CPU exact enumeration passed:315 joint cases,315 tails,225 cases with some q=0,27 disjoint-support cases,15 p=q cases including zeros,64 target/proposal pairs from8 distinct top-k/top-p filtered distributions. Native filter tie order and finite-precision arithmetic remain outside scope. No RNG or torch/GPU imports, source changes, seed changes or performance claims.

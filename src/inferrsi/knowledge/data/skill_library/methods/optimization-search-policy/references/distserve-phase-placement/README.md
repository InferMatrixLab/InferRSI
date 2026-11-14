# DistServe phase-placement constraints

Source-derived reference for candidate selection under the existing
optimization-search-policy owner. It records one distinction from Zhong et al.,
[DistServe, OSDI 24](https://www.usenix.org/conference/osdi24/presentation/zhong-yinmin)
([official paper](https://www.usenix.org/system/files/osdi24-zhong-yinmin.pdf)),
especially Sections 3.3 and 4.1-4.2, Algorithms 1-2. Edition, readset, source
identity, rights and evidence status are in the [source record](source-record.json).

## The placement assumption determines the feasible plans

Prefill processes the input tokens; decoding produces subsequent tokens. Their
different batching and parallelism needs motivate separate plans in DistServe.
The planning branches also assume different costs for moving the key/value
(KV) attention cache between the phases:

| Paper branch | Assumption and search | Constraint to retain |
| --- | --- | --- |
| Algorithm 1, high cross-node bandwidth / HighNode-Affinity | Cross-node KV transfer is treated as negligible. Search tensor/pipeline parallelism for each phase independently, then replicate the selected phase instances to serve the target rate. | Independent phase optima are conditional on that transfer assumption. |
| Algorithm 2, weak cross-node bandwidth / LowNode-Affinity | Group corresponding model-layer segments for same-node NVLink transfer. Jointly enumerate the two phases' memory-feasible intra-node parallelism configurations, subject to their combined GPU allocation fitting the node. | A phase's locally best configuration can be infeasible when the paired configuration must fit in the same node; total per-phase pipeline-parallel degrees can differ. |

The second branch restricts the feasible placement set before scoring plans;
it is not an extra transfer penalty applied after choosing independent optima.
The same-node condition concerns corresponding model-layer segments. Algorithm
2 shares an outer `inter_op` grouping, then selects `Pp` and `Pd` from the general
intra-node configurations described in Section 4.2. Keep that outer grouping
separate from each phase's complete tensor/pipeline-parallel layout. Appendix B,
Table 3 reports OPT-66B prefill TP=4/PP=1 and decoding TP=2/PP=2 for the main
end-to-end workloads, which Section 6.1 says use Low. The inner search is not
specified as TP-only, and the shared outer grouping does not require equal
total PP. The helper's internals and reconstruction of a concrete placement
remain unqualified here.

The grouping does not require an entire multi-node model to fit in one node.
Duplicate phase weights, KV capacity and the prefill-side source buffer remain
resource costs (Sections 3.2-3.3 and 5); they cannot be omitted because compute
is separated.

For a future comparison, declare the cross-node bandwidth assumption, per-node
GPU capacity, outer corresponding-layer grouping and complete per-phase
tensor/pipeline layouts
before selecting candidates. If the intended mapping exceeds node capacity,
exclude that mapping from Algorithm 2's feasible set. If transfer is material,
the independent-search assumption needs separate evidence. These are
source-derived decision checks, with no planner or runtime implementation here.

## Preserve the score and its denominator

The paper optimizes the maximum offered request rate at which the declared
fraction of requests meets **both** time-to-first-token (TTFT) and time-per-output-token
(TPOT) limits, divided by the GPUs provisioned for the placement. TPOT averages
decoding time within a request, excluding its first token. It does not bound
every individual token gap. Keep the joint request-attainment target, latency
limits, workload and GPU denominator fixed when comparing phase plans
(Sections 1-2 and 6.1-6.2).

## Evidence limits and counter-signals

- The authors' main testbed uses four nodes with 32 A100-80GB SXM GPUs,
  intra-node NVLink and 25-Gbps cross-node links; FP16 OPT-13B/66B/175B,
  dataset-derived lengths and synthetic Poisson arrivals. LongBench inputs are
  capped for OPT's 2048-position limit. This is historical author-reported
  evidence; exact serving-code revisions and a modern-vLLM reproduction are
  not established here.
- Figure 11's High-bandwidth and vLLM++ comparisons are simulated. Table 2
  compares measured vLLM and DistServe-Low attainment with the simulator at
  listed loads. The printed values differ by at most 1.8 percentage points;
  the authors' “less than 2%” wording does not establish relative error or
  universal SLO certification. A calibrated model still needs qualification
  for a changed workload, device, engine or transfer path.
- Section 6.5's opening sentence reverses the High/Low Algorithm 1/2 labels.
  The table above follows the explicit algorithm titles and Section 6.4,
  preserving that source inconsistency rather than silently reconciling it.
- Section 6.3's transfer fraction below 0.1% uses summed request-lifecycle
  times under local corresponding-stage NVLink placement. It is not a general
  inter-node cost or a device-wall-time fraction.
- Section 7 identifies throughput-only and scarce/single-GPU settings as
  counter-indications for disaggregation. Advanced preemption and fault
  tolerance remain future work. GQA/MQA and extreme-context benefits are
  expectations, without supporting evaluations in this edition.

Use the existing calibration and performance-ceiling owners for simulation
qualification and cost accounting. Current-engine KV readiness, ownership and
release require the vLLM lifetime owner and the selected implementation's
contracts; this paper does not establish connector conformance. Those owners
are declared in the parent skill's metadata, without copying their procedures.

## Relationship to prior work and source handling

This reference requalifies a subject overlapping closed-unmerged
[PR #156](https://github.com/InferMatrixLab/InferRSI/pull/156),
`case.distserve-phase-placement`. It uses original attributed prose from the
fresh official edition; it neither resumes nor copies that proposal. The
missing original archive and its synthesis remain unavailable. Novelty against
that unseen synthesis is UNKNOWN.

The publisher provides open access, while paper-specific third-party
redistribution and derivative rights remain UNKNOWN. Raw PDF, extracted text,
figures and page renders are excluded. This reference grants no paper license,
candidate promotion, execution authority or local performance claim.

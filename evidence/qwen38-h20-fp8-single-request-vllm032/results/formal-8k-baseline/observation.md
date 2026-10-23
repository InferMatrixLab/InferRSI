# Completed formal 8K baseline observations

Governing acceptance Issue67; harness plane; baseline-only observation, not a
paired candidate result or campaign PASS. Original2139 failed attempt remains
in observation-preparation.md and its immutable raw artifacts.

GPU2140 completed0:0 in1214allocatedGPU-seconds, one H20 and8CPU. Three restarts
produced3discarded warmups and30measured requests (10fixed8Kinputs×3), each with
2048actual generated tokens ignoringEOS. Independent audit re-parsed every SSE
and official client result: prompt/output identity, usage, text, DONE, choice
counts and ITL/timing all match. The saved raw audit is byte-value equivalent.
Full before/after guard receipts are identical:74model/tokenizer/config files,
5446installed vLLM members and214packages. All3outer owned-group cleanups are
exit0,unforced,remaining0,errors[]. Baseline logs retain missing-cubin warnings,
internal EngineCore force-kill after abort timeout0, and a semaphore warning;
outer cleanup success does not mean every internal worker stopped gracefully.

TTFT median1.681210257s; TPOT median10.452101140ms. Observed min/max TTFT
1.679883572/1.687585426s; TPOT10.357489934/10.722856366ms. Request latency median
23.077676588s is descriptive only, not an acceptance gate. Later candidate
statistics must use their contemporaneous paired baseline, not substitute
these30observations.

Complete private raw archive SHA256
68a755285f13dbde2183b60c1a7720d77eaaa8c06980e47784765c31c1c70b69.
Independent review SHA256
95310bf77a74853660c81273b218584422d8e931f69d1c46783a02c5f8e727f9.
Frozen component792cc20248c7657e0ac7f837ff864a58bab05f00bf950fcb4bd7027579285aa3.
Baseline phase cumulative1221/14400GPU-s including2139's7seconds. Readiness
7119/7200; search and final phases unused at this result. No environment changes.
Verdict INCONCLUSIVE: baseline work is complete; candidate/quality gates remain.

# DwarfStar assertion-backed usability cases

Cases verify guidance; they do not execute or qualify GPU/model behavior.

| Case | Target | Assertions | Evidence basis |
| --- | --- | --- | --- |
| integration/image-tool-prefix-after-restart | integration | 4 | docs/SERVER.md, docs/SSD_STREAMING.md, docs/SPECULATIVE_DECODING.md, tests/test_session_state.c |
| integration/ssd-cache-session-budget-and-quality | integration | 4 | docs/SERVER.md, docs/SSD_STREAMING.md, docs/SPECULATIVE_DECODING.md, tests/test_session_state.c |
| root/offline-request | dwarfstar | 3 | docs/SERVER.md, docs/SSD_STREAMING.md, docs/SPECULATIVE_DECODING.md, tests/test_session_state.c |
| sub-skills/qualification/checkpoint-matched-control | qualification | 6 | docs/SPECULATIVE_DECODING.md:13-38,112-137, QA_BEFORE_RELEASES.md:118-124,257-309 |
| sub-skills/qualification/opportunistic-is-not-exact-sampling | qualification | 6 | docs/SPECULATIVE_DECODING.md:112-137, tests/test_sampling.c:279-354, QA_BEFORE_RELEASES.md:257-309, ds4.c:86072-86195 |
| sub-skills/qualification/parser-test-is-not-physical-tp | qualification | 6 | tests/test_tp_commands.c:20-153, ds4_tp.c:700-738, docs/DISTRIBUTED.md:13-32,89-106,139-144, docs/SPECULATIVE_DECODING.md:66-78, ds4.c:82967-83022 |
| sub-skills/runtime-memory/expert-cache-is-not-total-memory | runtime-memory | 7 | docs/SSD_STREAMING.md:44-73, docs/SERVER.md:60-91, ds4.c:43279-43289, tests/test_session_state.c:163-190 |
| sub-skills/runtime-memory/presence-switches-and-model-specific-streaming | runtime-memory | 7 | README.md:5-25, docs/SSD_STREAMING.md:44-93, ds4_ssd.c:46-69, ds4.c:42625-42638, ds4_cuda.cu:29123-29129, ds4_cuda.cu:29408-29425 |
| sub-skills/serving-state/disk-key-versus-token-state | serving-state | 7 | ds4_kvstore.h:36-56, ds4_kvstore.c:1196-1308, ds4.c:64250-64292, ds4.c:77826-77860, ds4_server.c:10679-10731, ds4_server.c:11094-11133 |
| sub-skills/serving-state/same-text-changed-image | serving-state | 6 | ds4.h:448-472, ds4.c:76362-76425, ds4_server.c:11593-11614, tests/test_session_state.c:6-117 |

Each sub-skill has at least two new difficult synthetic cases. Qualification also
has a source-native-anchored sampling case. Two integrated cases combine source
state/memory/sampling contracts; these are adapted source-backed scenarios, not
a substitute for the unavailable real-model/physical-backend tests.

Assertion-bearing cases: 10. Assertions: 56.
All included routes have source-native anchors and synthetic assertions; no model
or accelerator capability is validated solely by these assertion grades.

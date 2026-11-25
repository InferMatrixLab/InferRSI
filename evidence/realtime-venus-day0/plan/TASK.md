Compare the adapted Realtime-Venus Omni profile with Thinker enforce_eager=true
against the same source and weights with enforce_eager=false. Retain 10 Flow steps,
FP32 Flow, one codec replica, identical ngram speculation and all other defaults.
One baseline and one candidate measurement only. Each starts an isolated service;
startup is excluded. Warm up one text and one image request; validate speech WAV
structure without claiming perceptual speech quality or speech speedup. Metric:
sum of three sequential C1 non-streaming HTTP text/image request durations.
Require non-truncated responses, expected capital/count/color facts and exact
baseline/candidate text equality. A zero-percent improvement gate is an exploratory
point comparison, not an SLO or statistical claim. No independent final retest is
authorized by the user's single-measurement rule; managed campaign remains
unfinalized and broad quality/performance acceptance remains INCONCLUSIVE.

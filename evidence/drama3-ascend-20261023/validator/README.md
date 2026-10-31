# Validator

Re-run: start the service with the candidate deploy config on two 910B1 cards,
then run the streaming benchmark (`bench/bench_stream.py` in the campaign
workspace) over concurrency 1, 2, 4, 8, 16, 32, 64 with 64 prompts, 1 warmup.

Pass requires: no request failures, C1 RTF mean at least 20% below the control
build measured the same day, and identical sampling parameters. Measure the
control and candidate back to back; this host is shared and single readings
move by tens of percent.

The preceding native GLM-Image candidate shares the position tables but still launches two rotary sequences per decoder layer. Its 40-layer position-only diagnostic on one decode token took 18.552 ms. In the warmed two-card native candidate quality run (512x512, 20 steps), the following stage times were recorded:
- seed 42: total 51.024 s, AR 46.665 s, diffusion 4.349 s.
- seed 771: total 51.689 s, AR 46.640 s, diffusion 5.040 s.
The QKV projection delivers contiguous Q and K head groups. Both groups use the same position-dependent elementwise arithmetic. This motivates testing joint Q/K rotation to reduce repeated elementwise launches. The stage timings do not attribute all autoregressive time to this region.

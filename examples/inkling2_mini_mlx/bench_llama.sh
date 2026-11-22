#!/bin/bash
# llama.cpp route: llama-bench prefill/decode with the peak memory reported by /usr/bin/time -l
# Usage: bench_llama.sh <gguf> <out-dir>  (LLAMA_BIN = llama.cpp build/bin)
set -e; G=$1; O=$2; mkdir -p $O; B=${LLAMA_BIN:?set LLAMA_BIN to llama.cpp build/bin}
P='用 Python 写一个线程安全的 LRU 缓存类，支持 get/put/容量上限和过期时间（TTL），附 3 个 pytest 用例。只输出代码。'
/usr/bin/time -l $B/llama-bench -m $G -p 512 -n 128 -r 3 -o json > $O/bench.json 2> $O/bench.err  # 512/128, 3 repetitions: llama-bench defaults
cat $O/bench.json | python3 -c "import sys,json;[print(x['n_prompt'],x['n_gen'],round(x['avg_ts'],2),'tok/s') for x in json.load(sys.stdin)]"
grep -E "peak memory footprint" $O/bench.err

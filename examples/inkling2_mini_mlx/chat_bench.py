# One code-generation request through llama-server's streaming OpenAI API; records time to first token and server timings.
import sys, json, time, urllib.request
url, maxtok = sys.argv[1], int(sys.argv[2])
P = "用 Python 写一个线程安全的 LRU 缓存类，支持 get/put/容量上限和过期时间（TTL），附 3 个 pytest 用例。只输出代码。"
body = dict(messages=[{"role": "user", "content": P}], max_tokens=maxtok, temperature=0, stream=True,
            chat_template_kwargs={"reasoning_effort": "none"}, timings_per_token=False, cache_prompt=False)  # no prompt-cache reuse, so time to first token is comparable across runs
req = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body).encode(), {"Content-Type": "application/json"})
t0 = time.time(); ttft = None; text = ""; think = ""; timings = None
for line in urllib.request.urlopen(req):
    line = line.decode().strip()
    if not line.startswith("data: ") or line == "data: [DONE]": continue
    d = json.loads(line[6:])
    if d.get("timings"): timings = d["timings"]
    for c in d.get("choices", []):
        dl = c.get("delta") or {}
        t = dl.get("content") or ""; r = dl.get("reasoning_content") or ""
        if (t or r) and ttft is None: ttft = time.time() - t0
        text += t; think += r
print(json.dumps(dict(ttft_s=ttft, wall_s=time.time() - t0, timings=timings, text=text, reasoning=think), ensure_ascii=False))

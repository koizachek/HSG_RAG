"""Streaming latency probe: time-to-first-partial over the public /_chat endpoint.

Usage (repo venv has gradio_client):

    venv/bin/python .claude/skills/hsg-rag-diagnostics-and-tooling/scripts/streaming_latency_probe.py

Sends ONE retrieval-heavy question (forces the tool-call path, the historically
fragile one) via client.submit(), which yields partial outputs as they stream.

Healthy (baseline 2026-07-07): first partial < 6 s (typically ~4 s),
total ~6–7 s, answer > 200 chars.

Failure signature: NO partials arrive and the full answer lands at the end
after 12–15 s → token streaming is dead and the agent fell back to blocking
invoke. Root cause historically: the middleware misread streamed tool-call
responses ("empty response, reason - tool_callstool_calls" in host logs) —
see hsg-rag-failure-archaeology. Exit 1 in that case.
"""
import sys
import time

from gradio_client import Client

URL = "https://chatbot.emba.unisg.ch/"

c = Client(URL, verbose=False)
c.predict(api_name="/on_accept")

t0 = time.time()
job = c.submit(message="Was macht die HSG besonders?", api_name="/_chat")

first_partial = None
last = None
for partial in job:
    if first_partial is None and partial and str(partial).strip():
        first_partial = time.time() - t0
    last = partial
total = time.time() - t0

text = last if isinstance(last, str) else str(last)
if first_partial is None:
    print("NO PARTIALS — streaming is dead (blocking fallback). Check host logs for")
    print("'empty response' / 'falling back to blocking' (src/rag/middleware.py).")
else:
    print(f"first partial : {first_partial:.2f}s   (healthy: < 6 s)")
print(f"total         : {total:.2f}s   (healthy: ~6-7 s)")
print(f"answer length : {len(text)}")

ok = first_partial is not None and first_partial < 6 and len(text) > 200
print("PASS" if ok else "FAIL")
sys.exit(0 if ok else 1)

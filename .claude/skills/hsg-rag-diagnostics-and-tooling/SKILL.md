---
name: hsg-rag-diagnostics-and-tooling
description: Measure instead of eyeball — diagnostic scripts and interpretation guides that quantify the HSG RAG chatbot's CURRENT state. Load when you need to measure production health, measure latency or time-to-first-token numbers, verify Weaviate object counts after an import, run public smoke tests over the Gradio API, scan the Docker image for CVEs (Trivy), or watch GitHub Actions runs (deploy, programme facts). Triggers: "is prod healthy", "measure latency", "get timing numbers", "verify streaming is alive", "smoke test", "Weaviate counts", "how many objects", "Trivy scan", "watch the deploy run", "timing logs". If something is broken and you need the CAUSE, load hsg-rag-debugging-playbook instead.
---

# HSG RAG — Diagnostics and Tooling

Purpose: give you **numbers, not impressions**. Every claim about the system
("it's slow", "retrieval is broken", "the import worked") must be backed by one
of the probes below. All baselines in this skill are **as of 2026-07-07**.
Latency/timing baseline numbers are owned by `hsg-rag-debugging-playbook`
§ Healthy baselines — the values repeated here are for probe interpretation;
if they disagree, the playbook wins and gets updated first.

Production endpoint: `https://chatbot.emba.unisg.ch` (Gradio app behind Caddy).
Quick pulse without any script:

```bash
curl -s https://chatbot.emba.unisg.ch/health
# healthy: {"timestamp":"...","status":"ok","weaviate":true}
```

## The three shipped scripts (scripts/)

Run all of them from the **repo root** with the **repo venv** interpreter
(`venv/bin/python`) — it has `gradio_client` and `weaviate-client` installed.
Do NOT use the anaconda interpreter here (that one is only for pytest — see
hsg-rag-build-and-env).

### 1. weaviate_counts.py — did the import actually land?

```bash
venv/bin/python .claude/skills/hsg-rag-diagnostics-and-tooling/scripts/weaviate_counts.py
```

Reads `WEAVIATE_CLUSTER_URL` / `WEAVIATE_API_KEY` from the repo-root `.env`
(explicit path — `load_dotenv()` without arguments crashes with
`AssertionError` when invoked via heredoc/`-c`).

| Metric | Baseline 2026-07-07 | Alarm if |
|---|---|---|
| `hsg_rag_content_de` total | 227 | 0, or drops sharply after re-import |
| `hsg_rag_content_en` total | 144 | « 100 (EN underrepresented) |
| embax.ch objects | 12 in EN, **0 in DE** | 0 in EN |

**0 embax objects in DE is plausible, not a bug**: embax.ch is an
English-only site; German emba-X content enters the DE collection via
emba.unisg.ch articles. Do not "fix" this.

### 2. public_smoke_test.py — the 6-check production suite

```bash
venv/bin/python .claude/skills/hsg-rag-diagnostics-and-tooling/scripts/public_smoke_test.py
```

Checks: consent decline notice, consent accept + booking widget HTML,
DE USP/retrieval question, DE pricing question, DE advisor handover,
EN language switch. Exit 0 = 6/6. Runtime ~45 s. **Each chat turn is a real
paid LLM call in production** — run on demand, never in a loop.

Gradio API facts that save an hour of debugging:

- Named endpoints: `/on_decline`, `/on_accept`, `/on_language_change`, `/_chat`.
  Rediscover with `Client(URL).view_api(all_endpoints=True)` if they drift.
- Handlers returning `gr.update(...)` arrive client-side as **dicts**
  `{'value': ...}` — unwrap before string operations or you get
  `KeyError: slice(None, 80, None)`.
- One `Client` instance = one server session; consent/agent state persists
  across `predict()` calls on the same instance. Call `/on_accept` before `/_chat`.

### 3. streaming_latency_probe.py — is token streaming alive?

```bash
venv/bin/python .claude/skills/hsg-rag-diagnostics-and-tooling/scripts/streaming_latency_probe.py
```

Sends one retrieval-heavy question via `client.submit()` (streams partials).
This deliberately exercises the tool-call path — the historically fragile one.

| Signal | Healthy | Broken |
|---|---|---|
| first partial | < 6 s (typically ~4 s) | none at all |
| total | ~6–7 s | 12–15 s, answer arrives all at once |

**No partials + slow total = streaming dead, agent fell back to blocking
invoke.** Known root cause pattern: middleware misreads streamed tool-call
responses (`finish_reason` concatenates across chunks to `tool_callstool_calls`)
— see hsg-rag-failure-archaeology, fixed 2026-07-07 in `src/rag/middleware.py`.

## Interpreting the [timing] host logs

The agent chain logs per-turn timings (`src/rag/agent_chain.py`). On the host:

```bash
# host-side (maintainer SSH access required):
grep "\[timing\]" /opt/hsg-rag/logs/logs.log | tail -20
grep -c "empty response\|falling back" /opt/hsg-rag/logs/logs.log
```

Three lines per turn:

| Line | Meaning | Healthy |
|---|---|---|
| `preprocessing` | language detection, scope check | 0.0–0.6 s |
| `agent loop (lead_agent)` | all LLM calls + retrieval | 2–3 s (facts turn), ~5–6 s (retrieval turn) |
| `total turn` | end-to-end server-side | ≈ agent loop + preprocessing |

Red flags in the same log:

- `Model returned an empty response, reason - ...! Retrying the call...` —
  wasted duplicate LLM calls (cost + latency).
- `Streaming failed for lead_agent (...); falling back to blocking invoke.` —
  user sees nothing until the full answer is done.
- Weaviate query line should read `retrieved 8 objects in ~0.4 seconds`;
  retrieval is essentially never the bottleneck — the LLM generation is.

## Image vulnerability scan (Trivy) — host-side

Trivy is not installed as a binary on the host; run it as a container
(maintainer SSH access required):

```bash
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  -v /root/.cache/trivy:/root/.cache/ \
  aquasec/trivy image --severity HIGH,CRITICAL --ignore-unfixed -q hsg-rag:latest
```

Reading the result: gradio/python-package findings are runtime-relevant and
must be triaged; Debian base-image findings (openssl/gnutls/libcap) are
low-exposure here (container is behind Caddy, TLS is outbound-only) and clear
when a rebuild pulls a patched base image.

## GitHub Actions observability

```bash
gh run list --workflow=deploy.yml --limit 5           # recent deploys (push / workflow_run / manual)
gh run list --workflow=update_programme_facts.yml --limit 5
gh run watch <run-id> --exit-status --interval 20     # block until finished
gh run view <run-id> --log | grep -iE "dispatched|fee|Health OK|error"
```

Facts-run success line to look for: `Change notification dispatched (email + slack).`
Deploy success lines: `Health OK after Ns` and `Public health: {"status":"ok"...}`.

## When NOT to use this skill

- You want to **fix** a diagnosed failure → hsg-rag-debugging-playbook
  (symptom→triage) and hsg-rag-change-control (gating).
- You wonder whether a failure was seen before → hsg-rag-failure-archaeology.
- You need to (re)build the environment or find the right interpreter →
  hsg-rag-build-and-env.
- You want to run/deploy the app itself → hsg-rag-run-and-operate.
- You need the release evidence bar (31/31 eval, UAT judge) →
  hsg-rag-validation-and-qa.
- Domain questions (programmes, fees, advisors) → emba-domain-reference.

## Provenance and maintenance

Scripts are hardened versions of probes used during the 2026-07-07 go-live
verification (smoke tests 6/6, streaming fix validation, import verification).
Baselines date from that day. Re-verify before relying on drift-prone facts:

```bash
curl -s https://chatbot.emba.unisg.ch/health                          # endpoint alive
venv/bin/python -c "from gradio_client import Client; Client('https://chatbot.emba.unisg.ch/').view_api(all_endpoints=True)"  # endpoint names
venv/bin/python .claude/skills/hsg-rag-diagnostics-and-tooling/scripts/weaviate_counts.py   # counts drift with every scrape
grep -n "\[timing\]" src/rag/agent_chain.py                           # timing log lines still exist
grep -n "tool_calls" src/rag/middleware.py                            # middleware guard still in place
```

If object counts change materially after a scheduled scrape, update the
baseline table in this file rather than treating the new numbers as a failure.

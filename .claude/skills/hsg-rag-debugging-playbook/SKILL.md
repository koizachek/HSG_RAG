---
name: hsg-rag-debugging-playbook
description: Symptom-to-triage playbook for diagnosing WHY something in the HSG RAG chatbot is broken or slow. Load when you need to find the cause of — slow answers, missing token streaming, error messages instead of answers ("Es tut mir leid, ich kann im Moment keine hilfreiche Antwort geben"), wrong programme prices, the booking widget never shows/appears, bot unreachable, blank iframe, empty PDF extraction in the facts pipeline, flaky LLM-judge tests, container start problems, or confusing log lines like "empty response" / "falling back to blocking invoke". Contains discriminating experiments with exact commands and the historical trap behind each failure mode. (To MEASURE current state with scripts — health, latency numbers, counts — use hsg-rag-diagnostics-and-tooling instead.)
---

# HSG RAG Debugging Playbook

Triage guide for the production EMBA chatbot (`https://chatbot.emba.unisg.ch`).
Work top-down: orient → match symptom in the table → run that section's
discriminating experiment. Do not fix by guesswork; every failure mode here has
a cheap experiment that tells you which branch you are in.

**Terms used once, defined once**

| Term | Meaning here |
|---|---|
| Facts turn | A user turn answered directly from the system prompt's injected facts (prices, deadlines) — no retrieval tool call |
| Retrieval turn | A turn where the agent calls the `retrieve_context` tool against Weaviate before answering (two LLM calls total) |
| Streaming | Token-by-token output via `src/rag/stream_parser.py`; user sees text before the turn finishes |
| Facts file | `data/database/programme_facts.json` — auto-generated, injected into the system prompt, **baked into the Docker image at build time** |
| Host | The Hetzner production server (`178.105.196.130`, app dir `/opt/hsg-rag`, container `hsg-rag`). Maintainer machines have the SSH alias `hsg-rag-prod` (machine-local convention, not in the repo) |

## Step 0 — Orient (always)

```bash
curl -s https://chatbot.emba.unisg.ch/health        # expect {"status":"ok","weaviate":true}
tail -50 logs/logs.log                              # local runs
ssh hsg-rag-prod 'tail -50 /opt/hsg-rag/logs/logs.log'   # production (host volume, mounted at /app/logs in the container)
grep "\[timing\]" logs/logs.log | tail -20          # per-turn latency
```

Log line anatomy: `(YYYY.MM.DD HH:MM:SS) <logger> LEVEL: message`. Loggers you
will grep for: `agent_chain`, `chain_model_call`, `chain_tool_call`,
`weaviate_service`, `chatbot_app`. User queries never appear in the wording:
all user text is redacted to `<redacted user input, N chars>` (GDPR, commits
`7d76603` and `413dd1f` — the latter closed the former 100-char
`Processing user query:` leak, so log wording cannot be used to reproduce a
user's exact input; work from the `N chars` lengths and timestamps instead).

## Healthy baselines (measured in production 2026-07-07)

This table is the library's **single home** for these numbers — sibling skills
(architecture-contract, run-and-operate, diagnostics-and-tooling,
conversion-campaign) reference it. When baselines drift, update here first.

| Metric | Healthy | Where to read it |
|---|---|---|
| Facts turn, end-to-end | 2–3 s | `[timing] total turn` |
| Retrieval turn, end-to-end | ~5.5–6.5 s | `[timing] total turn` |
| First streamed token (retrieval turn) | ~4 s | client-side only; not logged |
| Weaviate query | ~0.4 s | `Querying retrieved N objects in X seconds` |
| Preprocessing | 0.0–0.6 s | `[timing] preprocessing` |
| Model call retries | 0 | absence of `Retrying the call...` |

## Symptom → triage table

| Symptom | First check | Section |
|---|---|---|
| Retrieval turns 12 s+, nothing streams until the end | `grep -c "falling back to blocking" logs/logs.log` | A |
| Bot answers with QUERY_EXCEPTION_MESSAGE ("…keine hilfreiche Antwort…" / "…cannot provide a helpful response…") | `venv/bin/python main.py --weaviate checkhealth` | B |
| Wrong/outdated programme price or deadline | Compare answer vs `data/database/programme_facts.json` on `main` | C |
| Bot unreachable / blank page / blank iframe | Layered curl checks | D |
| Facts pipeline: PDF source yields no facts | `grep -i "near-empty\|fallback parser" logs` | E |
| `RUN_LLM_EVAL` / UAT judge tests fail sporadically | Re-read the failure: same case twice? | F |
| Health check fails right after container recreate | Wait; poll up to 240 s | G |
| `AssertionError` in `find_dotenv` from a python heredoc/`-c` | Pass explicit path to `load_dotenv` | H |
| Booking widget never appears despite booking intent | `grep -E "Show Booking Widget\|Suppressed booking state\|Proactive booking offer" logs/logs.log` — the model's raw flag (logged at `src/rag/agent_chain.py:773-775`) is post-processed by the gate at `:833-872`, which can suppress or grant it | — (reproducible → regression: probe #10 in `hsg-rag-conversion-campaign` Phase 1; flag semantics: `emba-domain-reference` §4) |

---

## A. Slow retrieval turns / streaming dead

**Story (the trap that cost a morning, fixed 2026-07-07, PR #67 — full
incident record: `hsg-rag-failure-archaeology` #8).** Under
streaming, LangChain aggregates message chunks and *concatenates* string
metadata — `finish_reason` arrives as `'tool_callstool_calls'`. The middleware's
exact-string check classified every correct tool-call response as "empty",
retried it `MODEL_MAX_RETRIES` (=2, `config.py`) times, gave up, and fell back
to a blocking `invoke`. Effect: 2 wasted (billed) LLM calls per retrieval turn
and zero streamed tokens — users stared at nothing for 12–14 s. The fix in
`src/rag/middleware.py` checks `result.tool_calls` directly instead of the
`finish_reason` string (see the comment above the `elif not result.content and
not getattr(result, 'tool_calls', None)` branch).

**Discriminating experiment:**

```bash
grep -E "empty response|falling back to blocking" logs/logs.log | tail
```

- Hits with recent timestamps → the streaming path is broken **again**. Read the
  `WARNING` reason text. If it prints a doubled/garbled `finish_reason`, a
  dependency bump likely changed chunk-metadata merging — inspect
  `_model_call_wrapper` in `src/rag/middleware.py` and `_invoke_streaming` in
  `src/rag/agent_chain.py` (the fallback lives at the `Streaming failed for`
  warning).
- No hits but still slow → check `[timing] agent loop` vs `[timing] total turn`.
  If agent loop dominates and Weaviate logs show ~0.4 s, the time is LLM
  generation (OpenRouter) — that is capacity/model behaviour, not a bug here.
  Distinguish provider slowness by the gap between consecutive
  `chain_model_call` INFO lines.

Note: `[timing]` lines log wall time of the whole turn; a *working* streaming
turn still shows ~5–6 s total — streaming changes perceived latency, not the
logged total.

## B. QUERY_EXCEPTION_MESSAGE instead of answers

The chain returns `QUERY_EXCEPTION_MESSAGE`
(`src/const/agent_response_constants.py`) when the agent loop raises. Two usual
suspects; discriminate before touching anything:

```bash
venv/bin/python main.py --weaviate checkhealth
grep -E "weaviate_service|chain_model_call" logs/logs.log | tail -30
```

| Evidence | Branch |
|---|---|
| checkhealth fails / connection errors | **Weaviate down or cluster expired.** Historical incident: the cloud cluster expired and returned 404s while the app was "up" — everything looked healthy except answers. Check the Weaviate Cloud console; cluster URL comes from `WEAVIATE_CLUSTER_URL` in `.env`. |
| checkhealth OK, log shows `chain_model_call ERROR` / OpenAI errors | **OpenRouter-side**: rate limit, 5xx, or model unavailable. Middleware retries transient errors (`MODEL_MAX_RETRIES=2`) then raises. Check https://status.openrouter.ai and the exact exception class in the log. |
| checkhealth OK, `ContextRetrievalError` in log | Retrieval tool itself failed mid-call — treat as Weaviate branch (`_tool_call_wrapper` in `src/rag/middleware.py` wraps `retrieve_context` failures in this error). |

Also distinct: `NOT_VALID_QUERY_MESSAGE` ("Das habe ich nicht ganz verstanden…")
is **not** an outage — it is the gibberish-input path (see
`tests/test_input_handler_gibberish.py`).

## C. Wrong programme prices / deadlines

Three distinct causes; check in this order:

1. **Stale baked-in facts.** The facts file is baked into the image at build
   time and cached in process memory — production only picks up changes on a
   redeploy. Since 2026-07-07 the deploy workflow auto-runs after every
   successful *Update Programme Facts* run, closing this gap. Verify the chain
   actually ran:
   ```bash
   gh run list --workflow=update_programme_facts.yml --limit 3
   gh run list --workflow=deploy.yml --limit 3
   git log --oneline -5 -- data/database/programme_facts.json
   ```
   If a facts commit exists but no deploy followed it, report the gap and
   propose dispatching `gh workflow run deploy.yml` — **maintainer OK required
   before triggering a production deploy** (per `hsg-rag-change-control`); do
   not dispatch it on your own initiative.
2. **Cross-programme contamination.** The bot quotes an IEMBA or emba X figure
   for an EMBA question (or vice versa). This is a release blocker, historically
   caused by the deleted regex fact-extraction router (see
   `AUDIT_LATENCY_HALLUCINATIONS.md`). Reproduce, then run the contamination
   guards in `tests/test_llm_fact_eval.py` (opt-in, paid — get maintainer OK).
3. **Source truth changed.** The official pages changed and the pipeline
   extracted them differently. Inspect the diff the pipeline saw:
   ```bash
   venv/bin/python -m src.pipeline.update_programme_facts --dry-run
   ```

Deadline logic reminder: fees are deadline-dependent; the bot must treat a
passed `first_deadline` as unavailable (facts injection carries an
expired-deadline rule) — "wrong price" reports near a deadline are often
actually correct behaviour.

## D. Bot unreachable / blank iframe

Walk the layers from the inside out; the first failing layer is your culprit.

```bash
# 1. container up?
ssh hsg-rag-prod 'docker ps --filter name=hsg-rag --format "{{.Status}}"'
# 2. app healthy on loopback? (app binds 127.0.0.1:7860 only — by design)
ssh hsg-rag-prod 'curl -sf http://127.0.0.1:7860/health'
# 3. Caddy terminating TLS and proxying?
curl -sSI https://chatbot.emba.unisg.ch/ | head -5
ssh hsg-rag-prod 'systemctl status caddy --no-pager | head -5'
# 4. DNS still correct?
dig +short A chatbot.emba.unisg.ch     # expect 178.105.196.130
dig +short AAAA chatbot.emba.unisg.ch  # expect 2a01:4f8:c014:9702::1
```

**Blank iframe with everything above green:** browser console will show a
`frame-ancestors` / CSP violation. The embedding page must be HTTPS on
`*.unisg.ch`, `embax.ch`, or `*.embax.ch` — that allowlist lives in
`deploy/Caddyfile` (`Content-Security-Policy: frame-ancestors ...`). Staging
domains of the WordPress host are *expected* to be blocked. To extend the
allowlist: edit `deploy/Caddyfile`, copy to the host, `systemctl reload caddy`
(no container rebuild). A `sandbox` attribute on the iframe also breaks the
embedded Calendly widget — check the embed snippet.

Container port publishing is `127.0.0.1:7860:7860` (deploy workflow), so port
7860 being closed from outside is correct, not a failure.

## E. Facts pipeline: empty PDF extraction

**Story.** Docling occasionally returns near-empty text for the fee-sheet PDFs.
Since commit `3f33dd7`, `extract_pdf_text` in
`src/pipeline/update_programme_facts.py` detects this ("Docling returned
near-empty text (N chars) … trying fallback parser") and falls back to `pypdf`.
No HuggingFace token is needed anywhere in the pipeline (Docling models load
anonymously; an HF rate-limit *warning* in CI logs is noise, not an error).

Check which parser produced the text and whether both failed:

```bash
# in a facts-workflow run log or local run output:
grep -iE "near-empty|fallback parser|could not parse" <logfile>
```

Both parsers failing on a *new* PDF URL usually means the source PDF moved —
check the `sources` array at the top of `data/database/programme_facts.json`.

## F. Flaky LLM-eval / UAT-judge tests

Known non-determinism, already mitigated — do not "fix" a single flake by
changing prompts or thresholds. The flake-vs-regression policy (one
fresh-session retry per fact-eval case; retry-don't-zero on malformed judge
JSON; "fails twice = regression") is owned by `hsg-rag-validation-and-qa` §5 —
read it there; do not stack more retries.

Discriminator: run the single failing case in isolation —
`RUN_LLM_EVAL=1 ... -k "<case_id>"` (paid; maintainer OK required). Passes in
isolation and only fails ~once per full run → flake, note it. Fails
repeatedly → regression; treat as blocking (release gate is **31/31**).

## G. Container slow to become healthy

After `docker run`, the app needs time to initialise (model/client setup)
before `/health` responds — observed ~30–90 s in production recreates. The
deploy workflow polls `/health` every 10 s for up to 240 s. If you probe
manually, poll instead of concluding failure from one early `curl` refusal:

```bash
ssh hsg-rag-prod 'for i in $(seq 1 24); do sleep 10; curl -sf http://127.0.0.1:7860/health && break; done'
ssh hsg-rag-prod 'docker logs hsg-rag --tail 40'   # if still failing after 240 s
```

Rollback anchor: the previous image is tagged `hsg-rag:previous` on the host.

## H. `AssertionError` in `find_dotenv` (heredoc trap)

`load_dotenv()` without arguments calls `find_dotenv()`, which walks stack
frames and asserts — this **crashes when Python runs from stdin/heredoc**
(`python - <<EOF`) or sometimes `python -c`. Always pass the explicit path in
scripts and one-liners:

```python
from dotenv import load_dotenv
load_dotenv("/absolute/path/to/HSG_RAG/.env")
```

Prefer writing a temp script file over heredocs for anything importing app code.

## When NOT to use this skill

- Changing/gating behaviour after you found the bug → `hsg-rag-change-control`
- Past incidents' full history and settled dead ends → `hsg-rag-failure-archaeology`
- Understanding *why* the design is the way it is → `hsg-rag-architecture-contract`
- Programme/domain facts (EMBA vs IEMBA vs emba X) → `emba-domain-reference`
- Measuring performance properly (not eyeballing) → `hsg-rag-diagnostics-and-tooling`
- Running tests / what counts as evidence → `hsg-rag-validation-and-qa`
- Setting up an environment from scratch → `hsg-rag-build-and-env`
- Routine start/deploy/operate tasks (nothing broken) → `hsg-rag-run-and-operate`

## Provenance and maintenance

Written 2026-07-07 against `main` (post-PR #69). Volatile items and how to
re-verify:

```bash
# middleware fix still present (section A)
grep -n "tool_callstool_calls" src/rag/middleware.py
# retry budget (sections A/B)
grep -n "MODEL_MAX_RETRIES" config.py
# error message constants (section B)
grep -n "QUERY_EXCEPTION_MESSAGE\|NOT_VALID_QUERY_MESSAGE" src/const/agent_response_constants.py
# pypdf fallback (section E)
grep -n "fallback parser" src/pipeline/update_programme_facts.py
# eval retry policy (section F)
grep -n "FLAKE_RETRIES" tests/test_llm_fact_eval.py
# CSP allowlist (section D)
cat deploy/Caddyfile
# health poll loop + port binding + rollback tag (sections D/G)
grep -nE "seq 1 24|127.0.0.1:7860|hsg-rag:previous" .github/workflows/deploy.yml
# baseline latency numbers (re-measure, don't trust 2026-07-07 forever)
grep "\[timing\]" logs/logs.log | tail -20
```

DNS/IP, latency baselines, and container start times are 2026-07-07
observations; re-verify before relying on them after infra changes.

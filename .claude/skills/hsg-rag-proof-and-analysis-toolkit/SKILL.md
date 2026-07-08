---
name: hsg-rag-proof-and-analysis-toolkit
description: First-principles analysis recipes for HSG_RAG — prove a mechanism instead of patching a symptom. Load when you are about to claim a root cause, ship a performance change, verify a multi-system chain (alerts, deploys), blame the LLM for a wrong answer, migrate models/providers, or audit dependencies. Each recipe includes a worked example from this repo's real history with commits and numbers. NOT a symptom→fix lookup table (that is hsg-rag-debugging-playbook) and not the chronicle of past incidents (that is hsg-rag-failure-archaeology).
---

# HSG_RAG Proof and Analysis Toolkit

The project's standing rule: **a fix is accepted when one mechanism explains all
observations and a measurement confirms the prediction — never "it looks better
now".** This skill packages the six analysis methods that produced this repo's
accepted results, each as a copy-pasteable recipe plus the historical worked
example that proves the method works here.

All dates, numbers, and commit hashes below are ground truth as of **2026-07-07**.

**When NOT to use this skill:**
- You have a symptom and want the known fix → `hsg-rag-debugging-playbook`.
- You want to know whether a battle was already fought → `hsg-rag-failure-archaeology`.
- You are deciding whether/how a change may ship → `hsg-rag-change-control`.
- You need the measurement scripts themselves → `hsg-rag-diagnostics-and-tooling`.
- You need domain facts (programmes, fees, advisors) → `emba-domain-reference`.

---

## Recipe 1 — Log-timeline root-cause analysis

**Use when:** something is slow or misbehaving in production and you have logs.

**Method:**
1. Pull the raw log window for ONE representative request
   (`grep "\[timing\]" logs/logs.log` for the coarse picture; then the full
   sequence between two `Processing user query` lines). Production logs live on
   the host at `/opt/hsg-rag/logs/logs.log`; local runs write `logs/logs.log`.
2. Reconstruct a per-second timeline: one row per log line, column for elapsed
   time since turn start. The gap owns the latency — never guess which phase is
   slow when the timestamps already say it.
3. Hunt for an **anomaly literal**: a log string that is not merely bad but
   *malformed* (doubled text, empty field, wrong enum). Malformed output is a
   fingerprint of the mechanism, not just the symptom.
4. Form a mechanism hypothesis that explains the literal exactly, then verify
   it in the source of the component that produced it (including third-party
   library code under `venv/lib/`).
5. Only then write the fix.

**Worked example (streaming bug, fixed 2026-07-07, commit `334da90`, PR #67):**
Retrieval questions took 12–14 s with nothing streamed. The per-second timeline
showed ~3.5 s of retries before a fallback. The anomaly literal was in the retry
warning (emitted by `src/rag/middleware.py:87`):

```
Model returned an empty response, reason - tool_callstool_calls! Retrying the call...
```

`tool_callstool_calls` is `tool_calls` **twice** — a doubled string is
concatenation evidence. Mechanism: under streaming, LangChain aggregates message
chunks and string metadata concatenates, so `finish_reason` became
`'tool_callstool_calls'`, failing the exact-match check
`finish_reason != 'tool_calls'` and misclassifying every tool-call response as
empty → 2 wasted LLM calls → streaming abandoned → blocking fallback. The fix is
one line (`src/rag/middleware.py:79`): test `result.tool_calls` directly instead
of the fragile string. The doubled literal was the entire case; without it the
retries looked like provider flakiness.

---

## Recipe 2 — Predict-then-measure performance work

**Use when:** any change is justified by "faster", "cheaper", or "less".

**Method:**
1. Before touching code, write down a **numeric prediction** and the mechanism
   it follows from ("removing X saves ~N s because the timeline attributes N s
   to X").
2. Choose one probe and keep it fixed: same question, same language, same
   measurement point (e.g. time-to-first-token and total turn via the public
   Gradio API, or `[timing]` log lines).
3. Measure before. Apply change. Measure after — same probe.
4. Accept only if the delta matches the prediction's mechanism. A speedup you
   cannot attribute is a coincidence waiting to revert.

**Worked example (same streaming fix):** Prediction recorded in the commit
message of `334da90`: eliminate ~3.5 s of wasted retries per retrieval turn and
restore token streaming. Measured with the same probe before/after: total
14.2 s → 5.7–6.7 s, first visible token ~4 s, retries 0, blocking fallbacks 0
(recorded in commit `334da90` and `DEPLOYMENT_CHECKLIST.md` §8/§10). The
measured delta (≈3.5 s from retries + the rest perceived via streaming) matched
the mechanism, so the change shipped same-day.

---

## Recipe 3 — End-to-end chain proof by controlled fault injection

**Use when:** you must prove a multi-system chain works (scrape → diff → alert →
commit → deploy), not just that each link is configured.

**Method:**
1. Identify a fault the chain is *designed* to detect and that the chain itself
   will **self-heal** (so the test cannot strand production in a bad state).
2. Inject exactly that fault, minimally.
3. Observe every link by its own evidence (workflow logs, commits, dispatch log
   lines, live behaviour) — a green overall run is not proof that each link fired.
4. Verify the end state equals the pre-test state.

**Worked example (alert chain, 2026-07-07):** EMBA final fee deliberately set
wrong, 77500 → 77000 (commit `ba880fb`). Facts workflow run **28864823526**
then produced, link by link: diff detected (`emba.tuition_chf.final_deadline.fee:
77000 -> 77500` in the run log), alert dispatched (log line
`Change notification dispatched (email + slack).` —
`src/pipeline/update_programme_facts.py:1062`), corrected file auto-committed
(`be9cc80`), the `workflow_run`-triggered production deploy followed, and the
live bot answered CHF 77'500 again. Every link had its own observable; the fault
healed itself by design. Full record: `DEPLOYMENT_CHECKLIST.md` §7.

**Fence:** this is the only currently documented sanctioned reason to hand-edit
`data/database/programme_facts.json` or push directly to `main` (AGENTS.md #7
lists it as the example, non-exhaustively) — and it changes production for
~10 minutes, so it routes through `hsg-rag-change-control` first.

---

## Recipe 4 — Determinism-vs-LLM discrimination

**Use when:** the bot said something wrong and the reflex is "the model
hallucinated".

**Method:**
1. Characterise the error class precisely (e.g. "right price, wrong programme").
2. Ask: could a deterministic component produce **exactly** this class? Trace the
   data path of the wrong value: prompt injection (`src/rag/verified_facts.py`),
   retrieval chunks, post-processing.
3. A deterministic bug produces *systematic* errors (same trigger → same wrong
   answer); sampling noise does not. Reproduce twice at temperature-equivalent
   settings before accepting "hallucination".
4. Only if no deterministic path explains it, treat it as a model/grounding
   problem — and fix grounding, not vibes.

**Worked example (regex fact router, June 2026):**
`AUDIT_LATENCY_HALLUCINATIONS.md` documents recurring "hallucinated" programme
prices that were actually a deterministic bug: ~2'000 lines of regex extraction
pulled CHF amounts from chunks and assigned them to programmes by keyword
matching — systematically attributing prices to the wrong programme. It looked
exactly like an LLM hallucination and was not one. Resolution: the router was
deleted outright (~1'800 lines removed from `agent_chain.py`) and replaced by
the auto-generated `programme_facts.json` injected into the system prompt.
Cost of the misdiagnosis: weeks of prompt-tweaking that could not have worked.

---

## Recipe 5 — Eval-based parity proof for model/provider migrations

**Use when:** changing anything in the model stack — provider, model name,
temperature, prompts with factual content. Concretely pending: the potential
EU-hosted LLM migration (`DEPLOYMENT_CHECKLIST.md` §2).

**Method:**
1. The parity instruments are the two opt-in suites (paid; keys required;
   pytest interpreter choice is machine-specific — see `hsg-rag-build-and-env`):
   ```bash
   RUN_LLM_EVAL=1 python -m pytest tests/test_llm_fact_eval.py -v
   RUN_UAT_LLM_JUDGE=1 python -m pytest tests/test_uat_llm_judge.py -v -s
   ```
   The fact eval is 31 cases with expected values loaded dynamically from
   `programme_facts.json` (so facts drift does not stale the suite), including
   cross-programme contamination guards.
2. Freeze everything except the axis under test. Model roles are configured as
   `(PROVIDER, MODEL_NAME)` tuples in `config.py` (`MAIN_AGENT_MODEL`,
   `FALLBACK_MODELS`, `LANGUAGE_DETECTION_MODEL`, …).
3. Run both configurations; compare **per-case**, not just the pass count — a
   31/31 that swapped which borderline cases pass is a behaviour change.
4. Release gate: 31/31 on the fact eval. A single contamination-guard failure is
   an automatic no-go (see `hsg-rag-validation-and-qa`).

**Worked example:** the June 2026 migration of all runtime LLM roles to
OpenRouter (`config.py` note: only the OpenRouter provider is used at runtime)
was accepted on a 31/31 fact-eval run, recorded in
`AUDIT_LATENCY_HALLUCINATIONS.md` ("Stand 2026-06-11: 31/31 passed").

---

## Recipe 6 — Transitive-dependency and false-positive analysis

**Use when:** an import/requirements audit, a vulnerability scan, or a "missing
dependency" report produces a scary list.

**Method:**
1. Generate the raw list mechanically (AST-walk imports vs `requirements.txt`).
2. Classify every entry before acting: (a) repo-internal module misread as a
   package, (b) import name ≠ package name, (c) transitive dependency of a
   pinned package, (d) documented lazy/optional import, (e) genuinely missing.
3. Only class (e) is a defect. Fix the audit's alias table for (b) so the false
   positive dies permanently.

**Worked example (requirements audit, 2026-07-07):** a raw audit flagged 12
"missing" imports. Classification: `config` = repo file (a); `usp` =
`ultimate-sitemap-parser`, `weaviate` = `weaviate-client` (b — verify with
`src/scraping/scraper.py:6` and `requirements.txt:34`); `fastapi`/`uvicorn`/
`pydantic`/`typing_extensions`/`docling_core` = transitive via gradio, langchain,
docling (c); `langchain_groq`/`_deepseek`/`_ollama`/`_huggingface` = lazy
provider imports, explicitly documented in the `requirements.txt` header comment
and guarded in `src/rag/models.py` (d). Genuinely missing: none. Result:
`requirements.txt` confirmed complete — zero changes, defect count 0, and the
checklist item closed with evidence instead of hope.

---

## Provenance and maintenance

Written 2026-07-07 from this repo's history; all citations verified against the
working tree at that date. Re-verify before trusting load-bearing claims:

```bash
git show 334da90 --stat                                   # streaming fix + numbers in message
sed -n '75,90p' src/rag/middleware.py                      # concatenation comment + retry warning
git log --oneline | grep -E "ba880fb|be9cc80"              # alert-chain fault + self-heal commits
grep -n "dispatched" src/pipeline/update_programme_facts.py
grep -n "1'800\|Regex" AUDIT_LATENCY_HALLUCINATIONS.md     # regex-router story
grep -n "RUN_LLM_EVAL" tests/test_llm_fact_eval.py         # eval suite still opt-in, 31 cases
grep -n "MAIN_AGENT_MODEL" config.py                       # model tuple config still there
```

Volatile: latency reference numbers (re-measure via Recipe 2's probe), the
31-case count (recount with `RUN_LLM_EVAL=1 ... --collect-only -q`), and the
pending EU-LLM migration status (`DEPLOYMENT_CHECKLIST.md` §2).

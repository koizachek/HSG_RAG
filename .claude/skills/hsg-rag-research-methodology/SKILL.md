---
name: hsg-rag-research-methodology
description: How a hunch becomes an accepted change in HSG_RAG — the evidence bar, predict-numbers-before-running, the idea lifecycle from proposal to merge or documented retirement, and where good ideas historically came from. Load this BEFORE starting any investigation, experiment, prompt change, latency/conversion improvement, or "I think the problem is X" hypothesis work. Also load it when deciding whether a result is strong enough to propose, or whether an idea should be retired.
---

# HSG_RAG Research Methodology

The discipline that turns "I have an idea" into an adopted change — or into a
documented retirement that nobody re-fights. This project has one maintainer,
a production system serving real prospective students, and a history in which
the costliest failure (the caching layer, ~2 months of work, fully removed)
came from skipping exactly this discipline. Token cost is cheap here;
unverified claims are expensive.

**Terms used once:** *eval gates* = the test suites a change must pass (see
`hsg-rag-validation-and-qa`); *merge=deploy* = every push to `main` deploys to
production via `.github/workflows/deploy.yml`; *maintainer* = the project
owner, who must approve changes before you edit (propose-before-edit rule,
see `AGENTS.md`).

## When NOT to use this skill

| You want to… | Use instead |
|---|---|
| Classify/gate/review a concrete change | `hsg-rag-change-control` |
| Triage a live symptom (bot slow, wrong answer, 5xx) | `hsg-rag-debugging-playbook` |
| Check whether a battle was already fought and lost | `hsg-rag-failure-archaeology` |
| Understand why the system is built this way | `hsg-rag-architecture-contract` |
| Run the eval suites / know what counts as passing | `hsg-rag-validation-and-qa` |
| Execute the conversion-improvement campaign | `hsg-rag-conversion-campaign` |
| Pick a first-principles analysis method (log archaeology, A/B on evals) | `hsg-rag-proof-and-analysis-toolkit` |
| Find an open problem worth attacking | `hsg-rag-research-frontier` |

## 1. The evidence bar

A hypothesis is accepted only when **one mechanism explains ALL observations,
including the negatives** (the things that did *not* go wrong), and the fix
derived from it survives adversarial verification at multiple levels.

Worked reference — the streaming bug (fixed 2026-07-07, commit `334da90`,
PR #67):

| Observation | Explained by "finish_reason concatenation" mechanism? |
|---|---|
| Retrieval questions took 12.6–14.2 s with nothing streamed | Yes — tool-call responses were misclassified as "empty", retried twice, then fell back to blocking invoke |
| Facts-only questions were fine (2–3 s) | Yes — the negative: their responses have non-empty `content`, which short-circuits the flawed check in `src/rag/middleware.py` |
| Prod log literal `reason - tool_callstool_calls!` (doubled string) | Yes — LangChain chunk aggregation concatenates `finish_reason` across streamed chunks |

A hypothesis that only explained the slowness (e.g. "gpt-4.1 is slow today",
"Weaviate is slow") would have failed this bar: it does not explain the doubled
literal or why facts turns were unaffected. If your mechanism leaves one
observation unexplained, you do not have the mechanism yet — design a
discriminating experiment instead of proposing a fix.

**Adversarial verification levels** (the streaming fix passed all four —
match this, scaled to your change class):

1. Offline suites green (`python -m pytest -q`; interpreter choice is
   machine-specific — see `hsg-rag-build-and-env`).
2. Live local reproduction shows the predicted improvement.
3. Production logs after deploy show the improvement **and** the absence of the
   red-flag lines (`empty response`, `falling back to blocking`).
4. Independent path confirms (public-domain probe, not just localhost).

## 2. Predict numbers before running

State the expected metric movement **before** the experiment, in writing, in
your proposal to the maintainer. If you cannot predict a number, you do not
understand the mechanism well enough to change production code.

Reference predictions that were made and then measured:

- Streaming fix (2026-07-07): predicted removal of ~3.5 s of wasted retries plus
  restored streaming → measured 14.2 s → 5.7 s end-to-end, first token ~4 s.
- June 2026 overhaul (`AUDIT_LATENCY_HALLUCINATIONS.md`): predicted ~6 s
  end-to-end from removing quality-eval calls, LLM language detection, and
  reasoning-class main model → measured 31 eval turns in 181 s.

For conversion work (the current campaign): pre-register expected movement in
the per-turn signals logged by `src/rag/agent_chain.py` —
`Appointment Requested: True/False` and `Show Booking Widget: True/False`
(lines ~773–774; note these are RAW pre-gate model flags — a post-processing
gate at `agent_chain.py:833-872` computes the final UI flags, see
`hsg-rag-conversion-campaign`) — e.g. "prompt change X should raise widget-show rate on
booking-intent turns from A% to B% on the UAT conversation set, with no
regression on the 31-case fact eval." Never judge a conversion change by eye.

## 3. The idea lifecycle

```
idea
 └─ 1. check hsg-rag-failure-archaeology: was this tried? (dead branches are evidence)
 └─ 2. written proposal to maintainer: mechanism + predicted numbers + eval obligations
        (propose-before-edit is a hard rule — see AGENTS.md)
 └─ 3. experiment: branch off main; config flag if behaviour must be switchable
        (pattern: ENABLE_EVALUATE_RESPONSE_QUALITY in config.py — retired feature,
         flag kept, default False)
 └─ 4. eval gates per change class (hsg-rag-validation-and-qa):
        offline suite → RUN_LLM_EVAL=1 (31/31 required) → UAT judge for tone/behaviour
 └─ 5a. ADOPTED: PR, maintainer merges → merge=deploy → verify prod logs + public probe
 └─ 5b. RETIRED: document in failure-archaeology (symptom → root cause → evidence →
        status); leave the dead branch in git as evidence; do not delete the history
```

**The anti-pattern this lifecycle exists to prevent** — the caching layer:
patched across Jan–Apr 2026 (`21d86db` cache metadata bug, 2026-01-27;
`9f7f202` session-id cache keys, `56acd61` disabling cache for
context-dependent messages, `ebdcdfd` config fixes, `cdf4744` prompt tuning —
all 2026-04-20), i.e. months of patching symptoms of an unsound idea
(commit-level chronology: `hsg-rag-failure-archaeology` entry 1). Cached responses
made answers non-deterministic and context-blind — per maintainer testimony
the cache "made everything unsafe", and it was the project's costliest
failure. It was removed wholesale in PR #41 (merge `dd98ea3`, 2026-06-16);
`src/cache/` no longer exists. The tell: each cache commit fixed a new way the
cache returned the wrong answer, and no commit stated a predicted, measurable
win. When you find yourself adding guards to protect users from your own
feature, stop and re-enter this lifecycle at step 2.

## 4. Where good ideas historically came from

Mine these sources before inventing from scratch:

| Source | Historical yield |
|---|---|
| **Real-user testing** of the deployed bot | The ten-defect overhaul plan (`docs/chatbot_overhaul_plan.md`) that reshaped prompts and architecture came from user testing of the old Hugging Face Space deployment |
| **Log archaeology** | The `[timing]` instrumentation in `src/rag/agent_chain.py` exposed both the June latency profile and the July streaming bug; the doubled `finish_reason` literal in one log line was the decisive clue |
| **Eval/judge failures** | UAT-judge failures drove concrete pipeline fixes: split scoring thresholds, contact-handoff and current-fee-first prompt rules (commit `532baba`, 2026-06-30) |
| **Maintenance pain → automation** | Hand-maintained facts became the scraped+diffed `programme_facts.json` pipeline with alerts; manual rsync deploys became `deploy.yml` after a facts update was found to never reach production |

## 5. Experiment template (copy into your proposal)

```markdown
## Experiment: <one-line name>
- Hypothesis: <the mechanism, one sentence>
- Explains ALL observations? <list each observation incl. negatives → how explained>
- Predicted numbers: <metric, current value, predicted value, measurement command>
- Change class + eval obligations: <offline / 31-case eval / UAT judge — per validation-and-qa>
- Abort criteria: <what observation falsifies the mechanism mid-experiment>
- Decision rule: <numbers that mean "propose for merge" vs "retire and document">
```

An experiment without abort criteria is a commitment, not an experiment.

## Provenance and maintenance

Facts verified against the repo on 2026-07-07. Re-verify before relying on:

- Streaming-fix anchors: `git show 334da90 --stat` and `git log --oneline --grep="#67"`
- Cache saga anchors: `git log --all --oneline --grep="cache" -i | head -15`
  (expect `dd98ea3` PR #41 removal merge, 2026-06-16) and `ls src/cache` → must not exist
- UAT-judge-driven fixes: `git show -s 532baba`
- Conversion log signals: `grep -n "Appointment Requested\|Show Booking Widget" src/rag/agent_chain.py`
- Flag pattern example: `grep -n "ENABLE_EVALUATE_RESPONSE_QUALITY" config.py`
- Eval gate commands and thresholds: see `hsg-rag-validation-and-qa` (source of truth;
  do not duplicate numbers here if they drift)
- Latency baselines (6 s end-to-end, first token ~4 s) are as-of 2026-07-07;
  re-measure via `grep "\[timing\]" logs/logs.log` on the host before citing.

Maintainer-testimony-only (no repo artifact): the judgement that the cache
"made everything unsafe" and was the costliest failure. The commit trail
corroborates the churn but the cost assessment is testimony (2026-07-07).

---
name: hsg-rag-research-frontier
description: Open research problems where HSG_RAG could advance the state of the art. Load when asked "what should we research next", "how could this bot be best-in-class", "can we publish something", "EU/sovereign LLM migration", "conversion measurement research", "bilingual retrieval parity", or "personalization under GDPR" — or when planning work that is exploratory rather than a bugfix or feature request. Provides, per problem: why current SOTA falls short, this repo's specific asset, the first three concrete in-repo steps, and a falsifiable "you have a result when…" milestone.
---

# HSG_RAG Research Frontier

Status date: **2026-07-07**. Every problem below is a **candidate — none has been
started**. Nothing here is a commitment or a claim of achieved results.

This skill frames *what* is worth researching and *how you would know you got a
result*. It does not execute anything.

**When NOT to use this skill:**
- Executing the conversion-improvement work itself → `hsg-rag-conversion-campaign`
  (that skill owns commands and gates; this one owns the research framing).
- The discipline for turning a hunch into an accepted result (evidence bar,
  pre-registration, adversarial refutation) → `hsg-rag-research-methodology`.
- Deriving/analyzing from first principles (cost models, statistics on eval runs)
  → `hsg-rag-proof-and-analysis-toolkit`.
- Claiming results publicly or to stakeholders → `hsg-rag-stakeholder-comms`.
- Anything operational (deploying, debugging, config) → `hsg-rag-run-and-operate`,
  `hsg-rag-debugging-playbook`, `hsg-rag-config-and-flags`.

**Ground rules for all four problems** (non-negotiable):
- Pre-register the success threshold *before* running anything
  (see `hsg-rag-research-methodology`).
- Every change routes through `hsg-rag-change-control`; the frozen 31-case eval
  (`RUN_LLM_EVAL=1 pytest tests/test_llm_fact_eval.py`) must stay **31/31** —
  a research win that breaks factual correctness is a regression, not a result.
  (Gate commands and threshold details: `hsg-rag-validation-and-qa`.)
- "SOTA falls short" paragraphs below are **assessments** (model knowledge,
  cutoff January 2026), not literature reviews. Verify before citing externally.

---

## Problem 1 — Measurable conversion for advisory chatbots

**The maintainer's declared success metric for this project (2026-07-07) is
conversion to booked advisor appointments.** This is the highest-priority
frontier problem and the subject of `hsg-rag-conversion-campaign`.

**Why current SOTA falls short (assessment):** published advisory/sales chatbot
work overwhelmingly reports engagement proxies (session length, satisfaction
ratings, resolution rate). Real funnel outcomes — a human booking a meeting with
a named advisor — are rarely measured end-to-end, because most deployments lack
a closed loop from bot turn to booking event.

**This repo's specific asset:** a *live, closed* funnel. Every turn produces
structured intent flags — `appointment_requested`, `show_booking_widget`,
`relevant_programs` — logged per turn (`src/rag/agent_chain.py:773-775`), a
widget gate (`src/rag/agent_chain.py:839`), advisor-specific Calendly handovers
(`src/const/data_consent_constants.py`), plus a conversation-level LLM judge
(`tests/test_uat_llm_judge.py`, opt-in `RUN_UAT_LLM_JUDGE=1`, 11 scripted
scenarios in `uat-results/TC-*.json`).

**First three steps in this repo:**
1. Quantify the measurable funnel from production logs: turns → widget flag →
   `appointment_requested=True`, per programme and language
   (`grep "Show Booking Widget: True" /opt/hsg-rag/logs/logs.log` on the host —
   mind 30-day log retention; export counts before they rotate). Caveat: these
   lines are the RAW pre-gate model flags; the `:839` gate computes the final
   UI flags — see the pre-gate/post-gate caveat in `hsg-rag-conversion-campaign`.
2. Define the metric contract: which logged event is the numerator/denominator,
   observation window, minimum n. Write it down before any intervention
   (pre-registration, per `hsg-rag-research-methodology`). Note the boundary:
   the Calendly booking itself happens outside our logs — completed-booking
   counts need advisor/Calendly-side data; flag this in any claim.
3. Run one controlled prompt intervention (single variable, e.g. the booking
   nudge rules in `src/rag/prompts.py`) and compare the pre-registered metric
   against baseline, with 31/31 eval and UAT judge unchanged.

**You have a result when:** a documented baseline rate (widget-shown →
appointment-requested) with stated n and window exists, AND one intervention
moves it by more than the pre-registered threshold while `RUN_LLM_EVAL` stays
31/31 and the UAT judge shows no regression.

---

## Problem 2 — EU-sovereign advisory LLM with *proven* quality parity

**Why current SOTA falls short (assessment):** EU/GDPR "sovereign AI" migrations
are usually argued legally (DPAs, hosting regions) and asserted qualitatively;
rigorous before/after quality-parity evidence on a frozen eval is rare.

**This repo's specific asset:** the host and vector DB are already EU
(Hetzner Falkenstein; Weaviate `eu-central-1` AWS) — only the LLM and embeddings
route to US providers (OpenRouter, `config.py`). And the project owns a frozen
parity instrument: 31 eval cases + the UAT judge. That turns "is the EU config
as good?" into a measured question. This also directly serves the open GDPR
sign-off (DEPLOYMENT_CHECKLIST.md §2).

**First three steps in this repo:**
1. Enumerate candidate EU-hosted endpoints for chat + embeddings (e.g. Azure
   OpenAI EU regions — *candidates to verify*, availability/DPA terms change).
   Record for each: region, no-training DPA availability, model equivalence.
2. Cost the embedding migration: 371 objects total (DE 227 / EN 144 as of
   2026-07-07) — re-embedding is cheap; the rebuild path exists
   (`python main.py --weaviate redo` then `--scrape full`). Embedding config
   axes: `EMBEDDING_MODEL`, `EMBEDDING_BASE_URL`, `EMBEDDING_DIMENSIONS`
   (`config.py:108-112`).
3. Write the parity protocol: run `RUN_LLM_EVAL` + UAT judge on the current US
   config (baseline), then identical runs on the EU config; pre-register the
   acceptable delta N *before* the EU runs.

**You have a result when:** an EU-only configuration (LLM + embeddings) scores
within the pre-registered delta of the US baseline on both instruments, with the
runs archived and reproducible.

---

## Problem 3 — Bilingual retrieval parity

**Why current SOTA falls short (assessment):** multilingual RAG evaluations
typically measure retrieval benchmarks, not whether a *production* bilingual
assistant gives equally good answers in both languages when its corpora are
asymmetric — which they almost always are.

**This repo's specific asset:** a measured asymmetry: `hsg_rag_content_de` 227
objects vs `hsg_rag_content_en` 144; embax.ch content is English-only (12 EN /
0 DE objects as of 2026-07-07), while German emba-X coverage rides on
emba.unisg.ch articles. The eval suite is already bilingual (DE/EN cases), and
language handling is deterministic and local (`src/rag/language_detection.py`).

**First three steps in this repo:**
1. Build a parallel DE/EN probe set (same questions, both languages) for topics
   beyond the verified-facts block, so answers depend on retrieval, not the
   injected facts.
2. Quantify the gap: retrieval hit quality and answer quality per language
   (UAT-judge scoring on the parallel set); identify topics where EN retrieval
   returns thin or off-programme chunks.
3. Close the worst gaps by targeted scraping additions
   (`SCRAPING_TARGET_URLS`, `config.py:142-145`) or import of EN source
   documents, then re-measure.

**You have a result when:** on the parallel probe set, EN answer quality is
within a pre-registered delta of DE, and the gap-quantification method is
documented well enough that a Sonnet-class session can re-run it.

---

## Problem 4 — GDPR-compatible personalization under 30-day retention

**Why current SOTA falls short (assessment):** personalization literature
assumes persistent user identity and long-horizon histories; advising quality
under deliberate data minimization (ephemeral sessions, short retention) is
largely unexplored territory.

**This repo's specific asset:** session-level profiling already exists and is
GDPR-scoped: profile fields (experience years, leadership years, field,
interests, suggested programme, handover wish) per
`docs/user_profile_tracking.md`, stored in `logs/user_profiles/*.json` with a
**30-day deletion cron** on the host (`docs/datenschutz_deployment.md`), behind
the `TRACK_USER_PROFILE` flag. Stage-aware prompting is already in place
(`src/rag/prompts.py:157`: early discovery vs expressed interest framing).

**First three steps in this repo:**
1. Measure whether stage-awareness actually fires: from UAT judge transcripts,
   check that framing shifts between discovery-stage and interest-stage turns
   of the same conversation.
2. Design 3–5 UAT stage-sensitivity cases (workbook format,
   `tests/fixtures/UAT.xlsx` / `uat-results/TC-*.json` pattern) that a
   stage-blind bot would fail.
3. Compare `TRACK_USER_PROFILE` on vs off on those cases — does within-session
   profiling measurably improve advising, given zero cross-session memory?

**You have a result when:** the stage-sensitivity cases pass with profiling on
and fail (or score measurably lower) with it off — i.e. personalization value
is demonstrated *within* the 30-day/ephemeral constraint, not despite it.

---

## Picking among the four

Default order: **1 (conversion)** — it is the maintainer's declared metric and
has `hsg-rag-conversion-campaign` ready; then **2 (EU parity)** — it unblocks
the GDPR sign-off; 3 and 4 are cheaper side quests that strengthen 1.

## Provenance and maintenance

Written 2026-07-07 from direct repo inspection. Field-level "SOTA falls short"
paragraphs are model assessments (cutoff Jan 2026) — re-assess before citing
externally. Re-verify volatile facts:

```bash
# Intent flags still logged per turn (expect log lines at ~773-775)
grep -n "Appointment Requested\|Show Booking Widget" src/rag/agent_chain.py
# Eval + UAT judge entry points still exist
grep -n "RUN_LLM_EVAL" tests/test_llm_fact_eval.py | head -3
grep -n "RUN_UAT_LLM_JUDGE" tests/test_uat_llm_judge.py | head -3
# Embedding axes unchanged
grep -n "EMBEDDING_" config.py | head -5
# Object counts (needs .env)
venv/bin/python .claude/skills/hsg-rag-diagnostics-and-tooling/scripts/weaviate_counts.py
# Profile retention doc still says 30 days
grep -n "30 Tage" docs/datenschutz_deployment.md
```

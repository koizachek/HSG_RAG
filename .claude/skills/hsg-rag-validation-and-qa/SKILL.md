---
name: hsg-rag-validation-and-qa
description: What counts as evidence in HSG_RAG and how to produce it. Load when you need to run or interpret the test suites (offline pytest, RUN_LLM_EVAL 31-case fact eval, RUN_UAT_LLM_JUDGE), decide which gates a change must pass before merge, add a new test / eval case / UAT conversation, judge whether a failing case is a flake or a regression, or understand the uat-results golden inventory and the CI gates (pr-llm-eval.yml, main-smoke.yml). Not for debugging failures (use hsg-rag-debugging-playbook) or changing the gates themselves (use hsg-rag-change-control).
---

# HSG_RAG Validation and QA

All facts date-stamped **as of 2026-07-07**. This skill defines what "proven" means
in this repo: which suite provides which evidence, which gates block which change,
and how to extend the evidence base without weakening it.

**Machine convention (dev Mac):** the repo venv has no pytest. Run pytest with
`/opt/anaconda3/bin/python -m pytest`; run the app with `venv/bin/python`.
In CI, plain `python -m pytest` works (pytest installed explicitly). The
two-interpreter trap is owned by `hsg-rag-build-and-env` — see it before
assuming the anaconda path exists on your machine.

## 1. The test pyramid as it actually exists

| Layer | Command | Cost | What it proves |
|---|---|---|---|
| Offline suite (default) | `/opt/anaconda3/bin/python -m pytest -q` | free, ~16 s | invariants, parsers, consent, prompts, facts-file sanity |
| LLM fact eval (31 cases) | `RUN_LLM_EVAL=1 /opt/anaconda3/bin/python -m pytest tests/test_llm_fact_eval.py -v` | paid, ~3 min | live chain answers facts correctly, no cross-programme contamination, latency cap |
| UAT LLM judge | `RUN_UAT_LLM_JUDGE=1 /opt/anaconda3/bin/python -m pytest tests/test_uat_llm_judge.py -v -s` | paid, ~10 min | full conversations meet quality bar (avg ≥ 8.5, every case ≥ 8.0) |
| Live probes (streaming, smoke over public domain) | see `hsg-rag-diagnostics-and-tooling` | free/cheap | production actually behaves as the code claims |

Verified baseline 2026-07-07: offline suite = **286 passed, 1 skipped, 12 deselected in 15.6 s**.
The 12 deselected are `network`/`integration`-marked tests excluded by
`pytest.ini` (`addopts = -m "not network and not integration"`).

### 1.1 Offline suite map (`tests/`)

| File / package | Guards |
|---|---|
| `test_verified_facts.py` | facts-file invariants (fees unique per programme, early < final fee), prompt rendering of the facts block, local language-detection heuristics, config sanity |
| `test_stream_parser.py` | incremental JSON `response`-field stream parser incl. fuzz across chunk boundaries, escapes, unicode |
| `test_pricing_prompts.py` | pricing rules in prompts (current-fee-first, deadline awareness) |
| `test_tone_and_handover.py` | lead-prompt tone rules, user-led booking, advisor routing content |
| `test_language_handling.py` | DE/EN detection, clarification and fallback messages |
| `test_input_handler_gibberish.py`, `test_invalid_input_escalation.py` | garbage input → `NOT_VALID_QUERY_MESSAGE` / escalation paths |
| `test_scope_guardian_offtopic.py` | off-topic queries stay refused |
| `test_main_happy_path.py` | app-level happy path with a fake agent (no LLM) |
| `test_programme_tagging_strategy.py`, `test_safe_import_reconciliation.py`, `test_master_transfer_integrations.py` | import pipeline strategies and reconciliation |
| `consent/` (4 files) | consent constants (texts, links, DE+EN coverage), consent state machine, consent logger format, agent-chain session handling |
| `scraping/` (5 files) | scraper, chunking, resume behaviour, URL utils (some files `network`-marked) |
| `test_weaviate_connection.py`, `test_weaviate_restore_schema.py`, `test_programme_positioning_real_agent.py`, `test_reply_speed_real_agent.py` | marked `network`/`integration` — excluded by default |

`tests/conftest.py` auto-skips whole files when optional imports are missing
(`pytest_ignore_collect` + `TEST_DEPENDENCIES` map). Consequence: a wrong/renamed
dependency makes tests silently vanish, not fail — after dependency changes,
compare the collected count against the baseline above. (Known drift: the map
still lists `tests/test_chatbot_improvements.py`, which no longer exists.)

### 1.2 LLM fact eval — the 31/31 release gate

File: `tests/test_llm_fact_eval.py`. Opt-in via `RUN_LLM_EVAL=1`
(module-level `skipif`). Needs `OPEN_ROUTER_API_KEY` + `WEAVIATE_*` in `.env`
(the module docstring still says "30 questions" and "OPENAI_API_KEY" — both
stale; there are 31 cases and the chain runs on OpenRouter).

Mechanics you must preserve when touching it:

- **Expected values are computed at collection time from
  `data/database/programme_facts.json`** (`_fee()`, `_start_year()`, `_ects()`),
  so the nightly facts regeneration never breaks the suite. Never hardcode a
  price or date into a case.
- Each case: `expect_any` = list of token **groups**; at least one token of
  *every* group must appear in the normalized answer. `forbid` = tokens that
  must NOT appear — this is the **cross-programme contamination guard**, the
  test encoding of the historic wrong-price bug (see
  `hsg-rag-failure-archaeology`). `_normalize()` lowercases and strips thousand
  separators so `77'500`, `77,500`, `77 500` all match `77500`.
- Case taxonomy (31): pricing 8 (the hotspot; includes 3-programme comparison
  and deadline logic), deadlines 3, starts 3, duration 3, language/format 4,
  advisors 3 (with forbid-guards against wrong advisor), grounding/honesty 3
  (no invented facts, no "six-figure" vagueness), conversational 4 (fit
  questions, booking intent, overview).
- **Latency gate**: every turn must finish < `MAX_TURN_SECONDS = 25.0` —
  catches gross regressions like an accidental reasoning-model switch.
- **Flake absorption**: `FLAKE_RETRIES = 1` — one retry with a *fresh chain and
  session* (commit `8d0136d`). A real regression fails both attempts.

Single case: `RUN_LLM_EVAL=1 ... -k "de_price_emba"`.

### 1.3 UAT LLM judge

UAT = User Acceptance Testing (the term is used unexpanded across this skill
library; this suite is its home). File: `tests/test_uat_llm_judge.py`. Opt-in
via `RUN_UAT_LLM_JUDGE=1`.
Scenarios come from `tests/fixtures/UAT.xlsx` (one sheet per case; sheets
`About`, `TestProtocol`, `Reporting` are skipped). Each `UATCase` carries
persona, user turns, expected behaviour, success criteria, red flags, expected
language, greeting expectation.

- Judge model: `openai/gpt-4o-mini` **via OpenRouter** by default (consistent
  with the app; opt out with `UAT_USE_OPENROUTER=0`, override with
  `UAT_JUDGE_MODEL`).
- Two thresholds, both required (commit `532baba`): average score
  ≥ `UAT_AVERAGE_MIN_SCORE` (default **8.5**) AND every case
  ≥ `UAT_CASE_MIN_SCORE` (default **8.0**). Gate test:
  `test_uat_average_score_passes_llm_judge`.
- Judge JSON can arrive malformed (observed 2026-07-06, 1 of 11 cases):
  `JUDGE_PARSE_ATTEMPTS = 3` re-judges instead of scoring 0 (commit `c48b2c1`);
  persistent malformed JSON still raises. Unit-tested via monkeypatch in the
  same file (those tests run offline).
- Results are written per case to `UAT_RESULTS_DIR` (default `uat-results/`).
- The file also contains offline tests (workbook structure, deterministic
  deadline-status enrichment `test_tuition_deadline_status_enrichment_is_deterministic`,
  date-independent hard-facts test — commit `ca11dec`).

## 2. Golden inventory — `uat-results/TC-*.json`

11 judged transcripts from the last accepted UAT run: `TC-EMBA-01..03`,
`TC-IEMBA-01..02`, `TC-EMBAX-01`, `TC-EDGE-01..05`. Each file: `case_id`,
`title`, `score`, thresholds, `passed`, `verdict`, `issues`,
`criteria_missed`, full `judgement` (strengths/weaknesses) and transcript
payload. Uses:

- **Reference evidence** of the accepted quality bar — compare a new run's
  verdicts against these before arguing a score change is noise.
- Regenerated on every judged run (files are overwritten); commit them when a
  run is accepted as the new baseline, per change control.

## 3. Acceptance discipline — which gate blocks what

CI (verified in `.github/workflows/`):

| Gate | Trigger | What runs | Threshold |
|---|---|---|---|
| `pr-llm-eval.yml` ("PR UAT LLM Judge") | every PR to `main` | UAT judge suite | avg ≥ 8.5, every case ≥ 8.0 |
| `main-smoke.yml` ("Main Smoke") | every push to `main` | 31-case fact eval | all pass; asserts `EXPECTED_SMOKE_TESTS=31` collected |
| `deploy.yml` | push to `main` / after facts run | deploy + health checks | `/health` local + public |

**Caveat:** `main-smoke.yml` and `deploy.yml` run in **parallel** — the deploy is
NOT blocked by the smoke result. A red smoke on main means production may
already be running the bad commit: treat as incident, fix or roll back
(`hsg-rag-run-and-operate`).

Minimum evidence per change class (details and rationale in
`hsg-rag-change-control`):

| Change | Offline suite | 31/31 fact eval | UAT judge | Live probe |
|---|---|---|---|---|
| Prompts / model / chain / middleware | required | required (PR merge triggers it on main anyway — run locally first) | required (runs on PR) | streaming + latency probe |
| Facts pipeline / `programme_facts.json` schema | required | required (soll-values must stay dynamic) | — | alert-chain awareness |
| UI / consent / booking | required (consent package) | — | recommended | smoke over public domain |
| Scraping / import | required (scraping package) | — | — | object counts before/after |
| Docs only | — | — | — | — (deploy skips doc-only pushes) |

Numbers decide, not impressions: a quality claim without a 31/31 run and UAT
scores is an opinion.

## 4. How to add evidence

**A new offline test:** put it under `tests/` (or the matching subpackage);
mark it `@pytest.mark.network` / `@pytest.mark.integration` if it needs the
outside world, otherwise it must pass with no network and no `.env` keys. If it
imports optional dependencies, add the file to `TEST_DEPENDENCIES` in
`tests/conftest.py`. Verify: run the offline suite and check it *collects* (the
silent-skip trap above).

**A new fact-eval case:** append a `dict` in `build_cases()` — `id` prefixed
`de_`/`en_`, `lang`, `query`, `expect_any` (token groups), `forbid`
(contamination tokens for every pricing/advisor case). Pull every volatile
value through `_facts()`/`_fee()`/`_start_year()`/`_ects()`; never literal
prices/dates. Then update `EXPECTED_SMOKE_TESTS` in
`.github/workflows/main-smoke.yml` (it pins the collected count — forgetting
this fails Main Smoke by design) and the "31/31" references per
`hsg-rag-docs-and-writing`.

**A new UAT conversation:** add a sheet to `tests/fixtures/UAT.xlsx` following
an existing case sheet (persona, user turns, expected behaviour, success
criteria, red flags; language cues like "Websiteaufruf auf Deutsch" drive
`expected_language`). Sheet names in `SKIPPED_SHEETS` are ignored. Run the
judge suite once locally; commit the new `uat-results/TC-*.json` with the
change.

## 5. Flake policy

Legitimate, already built in — do not stack more retries on top:

- One fresh-session retry per fact-eval case (sampling noise; `FLAKE_RETRIES=1`).
- Up to 3 judge re-calls on malformed judge JSON (infrastructure, not quality).

**Not legitimate:** raising `FLAKE_RETRIES`, lowering UAT thresholds, widening
`expect_any` groups, or deleting `forbid` tokens to get CI green. A case that
fails twice with a fresh session is a regression. Contamination and latency
failures are never flakes. Threshold changes are change-control decisions with
before/after numbers, not test fixes.

## When NOT to use this skill

- Diagnosing *why* a case fails or prod misbehaves → `hsg-rag-debugging-playbook`
- Changing gates/thresholds or classifying a change → `hsg-rag-change-control`
- Measuring latency, streaming, live smoke probes → `hsg-rag-diagnostics-and-tooling`
- What the correct programme facts *are* → `emba-domain-reference`
- Past failed approaches behind these guards → `hsg-rag-failure-archaeology`
- Deploy/rollback mechanics → `hsg-rag-run-and-operate`

## Provenance and maintenance

Written 2026-07-07 from repo state on `main` (post PR #69). Re-verify volatile claims:

```bash
/opt/anaconda3/bin/python -m pytest -q                       # baseline: 286 passed, 1 skipped, 12 deselected
/opt/anaconda3/bin/python -m pytest --collect-only -q | tail -3   # collected count vs silent skips
grep -c "dict(id=" tests/test_llm_fact_eval.py               # eval case count: 31
grep "EXPECTED_SMOKE_TESTS" .github/workflows/main-smoke.yml # must equal case count
grep -E "MIN_SCORE|PARSE_ATTEMPTS" tests/test_uat_llm_judge.py | head -4   # thresholds 8.5 / 8.0 / 3
ls uat-results/                                              # golden inventory (11 files)
cat pytest.ini                                               # default marker exclusions
```

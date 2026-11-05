# Lead-agent model comparison — evaluation of 2026-11-05

**As of:** 2026-11-05. **Production:** unchanged, `openai/gpt-4.1`. **Reason:** according
to third-party sources, OpenAI removes `gpt-4.1` and `gpt-4o-mini` from its API on
2027-01-14 (official page not checked directly; the OpenRouter date is unknown).

**Decision (2026-11-05, revised):** stay on `gpt-4.1` and keep looking for a successor
until the shutdown. `gemini-3.5-flash-lite` was approved first, but in CI and in 10
repeats it quoted an outdated fee on a price complaint; `gpt-5.6-luna` did the same and
`gpt-4.1` did not (section 12). The trial configuration is in section 11 and not merged.

Raw data (transcripts, judge verdicts, logs, test harness):
[`docs/model_comparison_2026-11-05/`](model_comparison_2026-11-05/), see section 14.

## 1. Results at a glance

OpenRouter prices per 1M tokens (input/output). UAT judged by `openai/gpt-4.1`.
Median and mean: answers with a model call (over 0.5 s).

| Model (effort) | Price | UAT avg | Worst case | Median | Mean | Fact eval | Status |
|---|---|---|---|---|---|---|---|
| `gpt-4.1` (current) | $2 / $8 | 9.09 | 8.0 | 3.44 s | 5.74 s | 34/34 | baseline |
| `gemini-3.5-flash-lite` (low) | $0.30 / $2.50 | 9.14 | 8.5 | 3.54 s | 3.94 s | 34/34 | rejected: outdated fee on price complaint (section 12) |
| `gpt-5.6-luna` (low) | $0.20 / $1.20 | 9.27 | 8.0 | 6.87 s | 6.06 s | 34/34 | rejected: outdated fee on price complaint, 1 wrong value in the facts pipeline |
| `gemini-3.8-flash` (low) | $0.825 / $4.125 | 9.41 | 8.0 | 7.80 s | 8.31 s | not run | passed, slow, expensive |
| `claude-haiku-5.5` (low) | $0.10 / $0.50 | 9.14 | 7.5 | 3.11 s | 4.59 s | not run | rejected |
| `gpt-6-luna` (low) | $0.10 / $0.50 | 9.23 / 9.00 | 7.5 | 5.38–5.83 s | 5.30–6.66 s | 34/34 | rejected |
| `gpt-6-luna` (standard) | $0.10 / $0.50 | 9.14 | 8.5 | 8.63 s | 10.04 s | not run | rejected, too slow |
| `gpt-6.1-terra` (low) | $1 / $5 | 9.14 | 8.0 | 6.78 s | 6.70 s | not run | struck by the maintainer (cost) |
| `mistral-large-4-0` (low) | $0.70 / $2.10 | – | – | – | – | not run | aborted, 1 of 11 cases |
| `mistral-medium-3-5` (low) | $1.50 / $7.50 | – | – | – | – | not run | aborted, 1 of 11 cases |
| `claude-sonnet-5.5` (low) | $2 / $10 | – | – | – | – | not run | aborted on request (cost), no result |

## 2. Method

- **UAT:** `tests/test_uat_llm_judge.py`, 11 cases. Gate: average at least 8.5, every case
  at least 8.0. Judge `openai/gpt-4.1`, as in CI.
- **Fact eval:** `tests/test_llm_fact_eval.py`, 34 cases, one retry per case on failure.
  Whether retries were needed was not evaluated.
- **Repeats:** the critical cases TC-EDGE-01 and TC-IEMBA-01 (partly TC-EDGE-03).
- **Facts pipeline:** `src.pipeline.update_programme_facts --dry-run`, output compared with
  `data/database/programme_facts.json`. Nothing was written.
- **Execution:** the lead-agent model was set by an override outside the repo
  (`harness/uat_override.py`); test code and `main` were unchanged. Only the lead agent was swapped.
- **Answering model:** recorded from the comparison runs with Terra onwards. Terra, Haiku,
  Gemini 3.8, `gpt-5.6-luna` and Flash Lite: only the tested model answered, no fallback. For
  the first full UAT runs of `gpt-4.1` and `gpt-6-luna` the logs are missing, so a fallback
  cannot be ruled out there.

**Limitations:**
- Mostly one full UAT run per model; differences of a few tenths are not reliable.
- Runs were parallel under varying load (up to 5 at once). Times are only roughly
  comparable and are total time per answer, not time to first token.
- Some saved answers were overwritten by later repeats (see section 13).

## 3. UAT per case (judge `gpt-4.1`)

| Case | `gpt-4.1` | Luna std | Luna low (1) | Luna low (2) | Terra | Haiku | Gemini 3.8 | `gpt-5.6-luna` | Flash Lite |
|---|---|---|---|---|---|---|---|---|---|
| TC-EDGE-01 | 8.0 | 9.0 | 10.0 | **7.5** | 9.5 | 9.0 | 9.5 | 9.5 | 9.0 |
| TC-EDGE-02 | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 |
| TC-EDGE-03 | 9.5 | 8.5 | **7.5** | 8.0 | 8.0 | 8.5 | 8.0 | 9.0 | 9.5 |
| TC-EDGE-04 | 9.0 | 9.0 | 9.0 | 9.0 | 9.0 | 9.0 | 9.0 | 8.0 | 9.0 |
| TC-EDGE-05 | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 | 10.0 |
| TC-EMBA-01 | 9.0 | 8.5 | 9.0 | 8.5 | 8.0 | 9.0 | 9.5 | 9.0 | 9.0 |
| TC-EMBA-02 | 9.5 | 9.5 | 9.5 | 9.5 | 9.5 | 9.5 | 9.5 | 9.5 | 8.5 |
| TC-EMBA-03 | 9.0 | 9.0 | 9.0 | 9.0 | 9.5 | 9.5 | 9.5 | 9.5 | 9.0 |
| TC-EMBAX-01 | 9.0 | 9.5 | 9.5 | 9.5 | 9.5 | 9.0 | 9.5 | 9.5 | 8.5 |
| TC-IEMBA-01 | 8.5 | 8.5 | 9.5 | 9.5 | 8.5 | **7.5** | 9.5 | 8.5 | 8.5 |
| TC-IEMBA-02 | 8.5 | 9.0 | 8.5 | 8.5 | 9.0 | 9.5 | 9.5 | 9.5 | 9.5 |
| **Average** | 9.09 | 9.14 | 9.23 | 9.00 | 9.14 | 9.14 | 9.41 | 9.27 | 9.14 |

Luna low (1): via override. Luna low (2): with the branch configuration.

## 4. Repeats of the critical cases (judge `gpt-4.1`)

First run plus repeats.

| Model | Case | Scores | Below 8.0 |
|---|---|---|---|
| `gpt-4.1` | TC-EDGE-01 | 8.0 / 9.0 / 8.0 / 9.0 / 8.5 / 9.5 | 0 of 6 |
| `gpt-6-luna` (low) | TC-EDGE-01 | 10.0 / 7.5 / 9.5 / 8.5 / 9.5 / 6.0 | 2 of 6 |
| `gpt-6-luna` (low) | TC-EDGE-03 | 7.5 / 8.5 / 9.0 / 9.0 | 1 of 4 |
| `gpt-6-luna` (standard) | TC-EDGE-03 | 8.5 / 8.5 / 8.0 / 8.5 | 0 of 4 |
| `claude-haiku-5.5` | TC-IEMBA-01 | 7.5 / 8.5 / 7.5 / 8.5 / 8.5 / 7.5 / 8.5 / 7.5 / 8.5 / 7.5 / 7.5 | 6 of 11 |
| `claude-haiku-5.5` | TC-EDGE-01 | 9.0 / 9.5 / 9.0 / 9.0 / 10.0 / 9.0 | 0 of 6 |
| `gpt-6.1-terra` | TC-EDGE-01 | 9.5 / 9.0 / 9.0 / 10.0 / 9.0 / 9.0 | 0 of 6 |
| `gemini-3.8-flash` | TC-EDGE-01 | 9.5 / 9.0 / 9.5 / 9.5 / 9.5 / 9.5 | 0 of 6 |
| `gpt-5.6-luna` | TC-EDGE-01 | 9.5 / 9.0 / 9.5 / 9.0 / 9.0 / 8.5 | 0 of 6 |
| `gpt-5.6-luna` | TC-IEMBA-01 | 8.5 / 9.5 / 8.5 / 9.5 / 8.5 / 8.5 | 0 of 6 |
| `gemini-3.5-flash-lite` | TC-EDGE-01 | 9.0 / 9.0 / 9.0 / 9.0 / 9.0 / 9.0 | 0 of 6 |
| `gemini-3.5-flash-lite` | TC-IEMBA-01 | 8.5 / 8.5 / 8.5 / 7.5 / 7.5 / 8.0 | 2 of 6 |

All TC-IEMBA-01 scores in this table use the old visa expectation (section 10).

## 5. Findings per model

### `gpt-6-luna` — rejected
- Answers are factually correct, but when the user does not meet the criteria the
  alternative (regular MBA) is often missing, although `src/rag/prompts.py` requires it.
- Effort comparison in the UAT: no visible quality gain of standard over `low`, but
  8.63 s instead of 5.83 s median.
- **Two extra prompt rules were tried and reverted.** Result: UAT average 8.77, TC-EDGE-01
  and TC-IEMBA-02 at 7.5 each; TC-EDGE-01 below 8.0 in 6 of 10 repeats
  (10.0 / 7.0 / 7.5 / 6.5 / 7.5 / 10.0 / 7.5 / 9.0 / 7.5 / 9.5). The rule to name a contact on
  frustration worked (TC-EDGE-03: named contact in 10 of 10, 1 of 10 below 8.0); the rule
  on alternatives did not. `src/rag/prompts.py` is identical to `main` again.
- In 4 of 10 answers to the "Wucher" complaint, CHF 77'500 appears before the currently
  applicable fee of CHF 72'500, once in the first sentence. Not a cross-programme mix-up,
  but it can convey the wrong price.

### `claude-haiku-5.5` — rejected
TC-IEMBA-01 was below 8.0 in 6 of 11 runs. In the first run it answered the alumni-network
question only by saying it was retrieving the current information; the answer itself was
missing. The repeats were not read individually. Part of the deductions in this case came
from the outdated visa expectation (section 10).

### Mistral — aborted
Both runs were stopped after 45 minutes at 1 of 11 cases each.

| | `mistral-large-4-0` | `mistral-medium-3-5` |
|---|---|---|
| **TC-EMBA-01 score** | 8.5 | 7.5 |
| **Response time per turn** | 18 / 863 / 50 / 907 / 11 s | 137 / 753 / 465 / 68 / 1 s |
| **Single request: our prompt, schema, tools** | 3–11 s | 3–4 s |
| **Single request after a tool result** | unstable | 2–8 s |

- The hangs also occurred in isolation, not only under parallel load: with
  `mistral-large-4-0`, turn 2 hung after the tool call despite `200 OK` while reading the
  response, until the 4.5-minute test limit (`logs/trace_large.out`).
- After a tool result, `mistral-large-4-0` sometimes calls the tool again or writes more
  than 5,000 characters until the set limit of 1,500 tokens (`finish_reason=length`).
- **Inferred, not directly proven cause of the minutes:** runaway output without token
  limit and timeout (section 8). For `mistral-medium-3-5` the cause is open.
- Whether the long answers came from Mistral or from the fallback is unknown. The two
  scores are not a quality verdict.
- OpenRouter already routes to the provider Mistral. The direct Mistral API was not
  tested (no key). It would mainly matter for EU processing; that is not confirmed, and
  embeddings would not be affected.

### `gemini-3.8-flash`, `gpt-6.1-terra`, `claude-sonnet-5.5`
- `gemini-3.8-flash`: best average, but more than twice as slow as `gpt-4.1`.
- `gpt-6.1-terra`: passed, struck by the maintainer because of cost.
- `claude-sonnet-5.5`: stopped before a result because of cost. According to Anthropic,
  [retirement not before 2027-09-28](https://platform.claude.com/docs/en/models/sonnet-5-5/overview).

### `gpt-5.6-luna` and `gemini-3.5-flash-lite`
Compared in section 9.

## 6. Facts pipeline (dry run)

The pipeline uses the lead-agent model (`update_programme_facts.py:337`, `:1187`).
One run per model.

| Model | Differences | Assessment |
|---|---|---|
| `gpt-6-luna` (low) | `emba_x.programme_start` 2027-02-01 → 2027-02-02 | correct |
| `gpt-5.6-luna` (low) | as above, plus `emba_x.structure` "56 days on campus" → "13 weeks on campus" | date correct, **structure wrong**: `embax.ch` and `emba.unisg.ch` state 56 days |
| `gemini-3.5-flash-lite` (low) | none | no wrong value, but does not correct the start date |

**Separate finding:** `programme_facts.json` has 2027-02-01 for emba X, the
[official deadlines page](https://emba.unisg.ch/bewerbung/fristen) states 2 February 2027.
Why the daily pipeline with `gpt-4.1` has not corrected this is unknown.

## 7. Second judge: `google/gemini-2.5-flash`

Existing answers were re-judged, one answer per case, judged twice. No new lead-agent calls.

| Model | Avg, judge `gpt-4.1` | Avg, judge Gemini | Worst case (Gemini) |
|---|---|---|---|
| `gpt-4.1` | 9.09 | **9.59** | 9.0 |
| `gemini-3.5-flash-lite` | 9.09 | 9.32 | 8.5 |
| `gpt-5.6-luna` | 9.18 | 9.27 | 7.0 |

- The `gpt-4.1` judge average differs in places from section 3 because for some cases
  the last saved answer was judged.
- **The 7.0 for `gpt-5.6-luna` (TC-IEMBA-02) is a judge error:** criteria (10 / 5 years)
  and fees (CHF 110'000 / 99'000) match `programme_facts.json`.
- For `gemini-3.5-flash-lite`, a Gemini model judges a Gemini model; not a fully neutral check.
- **Judge stability (`gpt-4.1`):** four TC-EDGE-01 answers were re-judged six times each,
  deviation at most 0.5. Run-to-run variance comes from the model's answers, not the judge.
- `gemini-2.5-flash` itself is retired on the Gemini API on 2026-12-01 and then routed to
  `gemini-3.5-flash-lite` ([Gemini deprecations](https://ai.google.dev/gemini-api/docs/deprecations)).

## 8. Other findings

- **No bounds on the production path:** the OpenRouter path in `src/rag/models.py` sets
  neither timeout nor `max_tokens`; `_openai_budget` only applies to the direct OpenAI
  path. The OpenAI client default applies (600 s read timeout), so a hanging request can
  take up to 10 minutes, also with `gpt-4.1`. Separate topic, independent of the model change.
- **OpenRouter key:** without `max_tokens`, OpenRouter reserves the model's output
  maximum. With only $0.19 of key limit left, `gpt-4.1` therefore returned `402`; with
  `max_tokens: 200` it worked. The tests had used $10.41 by then. Whether production uses
  the same key was not checked.
- **`scripts/rubric_judge.py`:** the weekly-report judge runs on `gpt-4o-mini` and must be
  switched before the shutdown.

## 9. Evaluation

| Criterion | `gemini-3.5-flash-lite` | `gpt-5.6-luna` | Advantage |
|---|---|---|---|
| Wrong facts in chat | 34/34, none found | 34/34, none found | equal |
| UAT average (`gpt-4.1` / Gemini) | 9.14 / 9.32 | 9.27 / 9.27 | practically equal |
| Median per answer | 3.54 s | 6.87 s | **Flash Lite** |
| Facts pipeline | no wrong value | 1 wrong value | **Flash Lite** |
| TC-IEMBA-01 below 8.0 (old expectation) | 2 of 6 | 0 of 6 | `gpt-5.6-luna` |
| Cost (in/out) | $0.30 / $2.50 | $0.20 / $1.20 | `gpt-5.6-luna` |

**Reasoning (before section 12):** quality is level. Flash Lite is almost twice as fast and keeps today's
`gpt-4.1` speed, and it produced no wrong value in the pipeline. Costs drop sharply
compared with `gpt-4.1`. With the `gemini-2.5-flash` judge, `gpt-4.1` is still ahead of
both candidates (section 7).

## 10. Test case TC-IEMBA-01 corrected

The visa expectation in the test case contradicted the product rule in
`src/rag/prompts.py:160` (redirect to the admissions team, no own visa details). In all 10
checked Flash Lite runs the judge deducted points for this. Changed in
`tests/fixtures/UAT.xlsx`, sheet `IEMBA` (cell text kept in German like the rest of the workbook):

- **C16:** "Verweist an das Admissions-Team", "Keine eigenen Visa-Details (Permit, Timeline, Dokumente)"
- **F5:** "Visa-Frage wird an das Admissions-Team verwiesen"

The same 10 answers re-judged: before, nine times 8.5 and once 7.5; after, ten times 9.5
(`runs/gemini-3.5-flash-lite__iemba01-10-runs-with-judge.json`). Earlier TC-IEMBA-01 scores
of all models in this document still use the old expectation.

## 11. Trial configuration (not merged)

Approved by the maintainer on 2026-11-05 and withdrawn the same day after the finding in
section 12. The configuration was reverted to `gpt-4.1`.

| Role | Model |
|---|---|
| Lead agent, summarization, facts pipeline | `google/gemini-3.5-flash-lite`, effort `low` |
| Language detection, confidence scoring | `google/gemini-3.5-flash-lite` |
| Fallback | `openai/gpt-5.6-luna`, effort `low` |

Gates with this configuration:

| Gate | Result |
|---|---|
| Offline suite | 391 passed, 1 skipped |
| Fact eval | 34/34 |
| UAT | passed: avg 9.09, worst case 8.0 (TC-EDGE-04), median 3.1 s |
| Streaming (8 DE/EN questions) | first token 1.0–3.0 s, total 1.5–3.8 s, 2–8 chunks per answer, no warnings, only Flash Lite answered |
| Facts pipeline (dry run) | no differences from `programme_facts.json` |
| Shutdown date | Gemini API: none announced; [Google Cloud](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions): 2027-07-21 or later |

## 12. Price complaint: outdated fee (TC-EDGE-03)

**Trigger:** the CI UAT of the trial configuration failed once: TC-EDGE-03 at 7.0 (run
[42094060632](https://github.com/koizachek/HSG_RAG/actions/runs/42094060632)); the next run
on unchanged code passed. The user writes "Warum ist das so teuer?! Das ist doch Wucher!"
without naming a programme.

**Finding:** until 2026-11-23 the EMBA HSG fee is CHF 72'500; CHF 77'500 applies only
after that. Answers that state only CHF 77'500 convey an outdated price. A new prompt rule
for price complaints was added (`src/rag/prompts.py`, TONE & FORMAT): explain value with
retrieved facts, quote only the fee that applies today, end with the named advisor.

TC-EDGE-03, 10 runs each (judge `gpt-4.1`):

| | Flash Lite, before rule | Flash Lite, with rule | `gpt-5.6-luna`, with rule | `gpt-4.1`, with rule |
|---|---|---|---|---|
| Average | 8.20 | 8.85 | 9.15 | 9.45 |
| Below 8.0 | 1 | 1 | 0 | 0 |
| Named advisor | 1 | 10 | 10 | 9 |
| Only CHF 77'500 stated | 1 | **3** | **3** | 0 |

**New fact-eval case `de_price_complaint`** (`tests/test_llm_fact_eval.py`): same question;
while a programme's first deadline is open, its final-deadline fee may only appear together
with the first-deadline fee. 10 runs each without retry:

| Model | Passed |
|---|---|
| `gpt-4.1` | 10 of 10 |
| `gemini-3.5-flash-lite` | 10 of 10 |
| `gpt-5.6-luna` | 9 of 10 |

The case did not reproduce the Flash Lite error seen in the UAT (3 of 10), so it is a
partial guard only. With one retry per case in the eval, an error rate around 15 % mostly
goes unnoticed. With "der EMBA" in the question, Flash Lite passed 10 of 10.

**Combined:** outdated fee in 3 of 20 Flash Lite answers, 4 of 20 `gpt-5.6-luna` answers
and 0 of 20 `gpt-4.1` answers. Prompt rules did not prevent it.

**Gates on the kept branch state (`gpt-4.1`, new prompt rule, corrected TC-IEMBA-01, new eval case):**

| Gate | Result |
|---|---|
| Offline suite | 391 passed, 1 skipped |
| Fact eval | 35/35 |
| UAT | passed: avg 9.36, worst case 8.5 |

## 13. Open items

- [ ] Find a `gpt-4.1` successor before 2027-01-14; every candidate must pass TC-EDGE-03 repeatedly without an outdated fee
- [ ] Make the price-complaint eval case reproduce the error reliably (e.g. several samples per case)
- [ ] Clarify the emba X start date in `programme_facts.json` (2027-02-01 vs 2 February 2027)
- [ ] Switch the CI judge (`UAT_JUDGE_MODEL`) and `scripts/rubric_judge.py` before `gpt-4.1`/`gpt-4o-mini` shut down
- [ ] Set a timeout and `max_tokens` on the OpenRouter path
- [ ] Confirm the `gpt-4.1` shutdown date officially
- [ ] Rework `docs/datenschutz_deployment.md` (maintainer) once the successor is chosen

## 14. Raw data

Folder [`docs/model_comparison_2026-11-05/`](model_comparison_2026-11-05/):

| Path | Content |
|---|---|
| `runs/<model>__<run>/TC-*.json` | per case: transcript, judge verdict, score (format of `tests/test_uat_llm_judge.py`) |
| `runs/gpt-6-luna-low-prompt-rules__repeat-transcripts/` | all 20 transcripts of the repeats with the reverted prompt rules |
| `runs/gemini-3.5-flash-lite__iemba01-10-runs-with-judge.json` | 10 TC-IEMBA-01 runs with full judge output |
| `runs/gemini-3.5-flash-lite__uat-final-config/` | UAT of the trial configuration (section 11) |
| `runs/*__edge03-10-runs-*.json` | 10 TC-EDGE-03 runs per model with answer, score and judge output (section 12) |
| `runs/gpt-4.1__uat-final-branch/` | UAT of the kept branch state (section 12) |
| `logs/*.out` | console output of UAT, fact eval, facts dry runs, streaming check, Mistral trace |
| `harness/*.py` | scripts used for overrides, repeats, re-judging and latency measurements |
| `openrouter_prices_2026-11-05.json` | price snapshot of the compared labs |

Notes on the raw data:
- Repeats write to the same file per case, so a run folder keeps only the **last** answer
  per case. In the `__uat` folders of Terra, Haiku, Gemini 3.8, `gpt-5.6-luna` and Flash Lite,
  `TC-EDGE-01.json` and `TC-IEMBA-01.json` come from the last repeat, not the UAT run;
  some of them are `402` aborts with score 0.0.
- The scores of all runs are in sections 3 and 4 and in the `RESULT` lines of the `logs/*.out` files.
- Key-management URLs were removed from error messages; local paths were shortened.
- The UAT personas are synthetic; there is no real user data.

## Sources

- [OpenRouter: model list and prices](https://openrouter.ai/api/v1/models), retrieved 2026-11-05
- [Anthropic: model deprecations](https://platform.claude.com/docs/en/about-claude/model-deprecations)
- [Gemini API: deprecations](https://ai.google.dev/gemini-api/docs/deprecations)
- [OpenAI deprecations (mirror)](https://hn.jakechampion.name/reader/https://platform.openai.com/docs/deprecations)
- [Sessionwatcher: GPT-4o and GPT-4.1 shutdown](https://sessionwatcher.com/news/openai-api-gpt-4o-gpt-4-1-shutdown-january-14-2027)

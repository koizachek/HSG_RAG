---
name: hsg-rag-failure-archaeology
description: The chronicle of every major HSG_RAG failure, dead end, rejected fix, and revert — response cache saga, June 2026 latency/hallucination overhaul, regex fact router, sub-agent removal, Weaviate 404 outage, HF Space era, streaming bugs, judge flakiness, dead branches. Load this BEFORE proposing a caching layer, sub-agents, regex fact extraction, model swaps, or any "why don't we just…" idea; before investigating a bug that smells historical; before resurrecting code from an old branch; or when asked "has this been tried before?". Prevents re-fighting settled battles.
---

# HSG_RAG Failure Archaeology

**As of 2026-07-07.** This is the project's institutional memory: what failed, why, what the evidence is, and whether the battle is settled. Every entry is anchored to commits, PRs, branches, or docs in this repo. Claims that rest only on the maintainer's word are explicitly labeled **[maintainer testimony]**.

**How to use:** before proposing a change, scan the entry titles and the dead-branch table. If your idea matches a retired entry, the burden of proof is on you to explain what is different this time — route it through `hsg-rag-change-control`, do not just re-implement.

**Status vocabulary:**

| Status | Meaning |
|---|---|
| `fixed-verified` | Fix merged AND behavior re-verified by test/eval/live measurement |
| `fixed-believed` | Fix merged; no individual re-verification since |
| `retired` | Feature/approach deliberately removed; do not reintroduce without change control |
| `managed` | Inherent problem, mitigated but not eliminated |
| `open` | Still live |

---

## 1. The response cache saga — the costliest failure (Jan–Jun 2026)

| | |
|---|---|
| **Symptom** | Wrong/stale answers replayed to users: conversation-specific answers returned verbatim later in a session; cached prices could outlive fact changes; cached booking flags (`show_booking_widget`, `appointment_requested`) replayed UI behavior out of context. |
| **Root cause** | A Redis/dict response cache keyed on `cache:{session_id}:{language}:{normalized_query}` (normalization stripped ALL non-alphanumerics — `get_cache_key` in the deleted `src/cache/utils.py`). The key ignored conversation history entirely, so the same literal query later in a conversation (after context had moved on) hit the old answer. Worse: whether a response was cacheable at all was decided by the **LLM's own self-report** (`is_context_dependent` boolean in the structured output, plus `should_cache` logic in the old `agent_chain.py`) — one wrong self-flag poisoned the session. Cached responses also bypassed the verified-facts injection completely. |
| **Evidence** | Built: `80c2d7d` (2026-01-15 skeleton) → `9e00888` (01-16, local Redis + docker) → `6273673` (01-18, Redis cloud) → PR #8 (`res_cache`, merged `82873a8`). Patch treadmill: `f3d3ed2` (2026-01-27, skip appointment requests), then the 2026-04-20 cluster — `45cea9f` (LLM context-dependency boolean), `56acd61` (skip context-dependent), `9f7f202` (session id in key), `d9ab21c` (moved into agent chain), `cdf4744` (prompt changed "to better flag context dependent queries"). Removed: `0c2eb13` (2026-06-15, −692 lines net: `src/cache/*`, `src/database/redisservice.py`, `docker-compose-cache.yml`, `tests/test_cache.py`), merged as **PR #41** `dd98ea3` (2026-06-16). |
| **Status** | **retired** |

**The lesson (why this entry is first):** the maintainer names the cache implementations as the most expensive failure of the project — "they made everything unsafe" **[maintainer testimony, 2026-07-07]**. The git record independently shows the classic shape of a structurally unsound feature: six months of narrowing patches (session key → LLM self-flag → prompt tuning → per-feature exclusions), each closing one hole while the design guaranteed more. A response cache for a *stateful conversation* keyed on the *stateless query string* cannot be patched into correctness. Do not reintroduce response caching. If latency pressure returns, the settled alternatives are streaming (already in place) and model choice — see entry 2.

---

## 2. June 2026 latency + hallucination overhaul (15–40 s → ~6 s)

| | |
|---|---|
| **Symptom** | 15–40 s end-to-end answers; recurring wrong programme prices; generic answers ignoring retrieved content. |
| **Root cause (latency, 8 stacked causes)** | gpt-5.1 reasoning model as main agent (10–30 s/loop); a blocking quality-eval LLM call after every answer (which could *discard* the finished answer); no token streaming; an LLM call per turn for language detection; HF Inference API vectorization (see entry 6); unbounded conversation history; retry multiplication (60 s timeouts × 3 retries × 2–4 fallback models); sub-agent architecture doubling calls. |
| **Root cause (hallucinations, 5 causes)** | ~1,800–2,000 lines of **regex fact extraction** pulling CHF amounts/dates out of chunks and assigning them to programmes by keyword matching — a deterministic code bug that *looked like* LLM hallucination; thin grounding (4 chunks × 200 tokens); a quality gate that never saw the retrieval context; keyword routers answering misclassified questions with templates; chunks without source/programme metadata. |
| **Evidence** | `AUDIT_LATENCY_HALLUCINATIONS.md` (full diagnosis + before/after table). Fix commits: `ef98e70` (2026-06-10, fast model + local lang detection + history cap + retrieval guards), `b773b5d` (verified facts), `9981251` (31-case eval + timing logs), `f8bf0df` (streaming JSON field parser), `3323cb4` (2026-06-11, **deleted regex routers, subagents, chunk-based fact provider — ~2,000 lines**), `ddcfc65`, `ca90654` (handover doc). |
| **Status** | **fixed-verified** — 31/31 LLM eval (last run 2026-07-07); prod timing logs ~6 s retrieval turns, 2–3 s facts turns. |

**Settled battles inside this entry — do not re-fight:** regex/keyword fact extraction from chunks (**retired**); per-turn LLM language detection (**retired** — local heuristic + lazy LLM fallback in `src/rag/language_detection.py`); blocking post-answer quality eval (**retired**; `ENABLE_EVALUATE_RESPONSE_QUALITY` defaults False in `config.py`); reasoning-class main model (**retired** — `openai/gpt-4.1` via OpenRouter, `config.py` line ~38).

---

## 3. Sub-agent architecture: enabled, compared, deleted

| | |
|---|---|
| **Symptom** | High latency and generic answers; "RAG never gets called" — the lead agent answered from its own bloated prompt and almost never invoked `call_emba_agent`/`call_iemba_agent`/`call_embax_agent` (Problem 1 in `docs/chatbot_overhaul_plan.md`). |
| **Root cause** | The lead prompt had accumulated all sub-agent content (pricing, USPs, snapshots), so the model had no reason to delegate; when it did, calls doubled. Orchestration, static facts, and content generation were mixed in one always-on context. |
| **Evidence** | Single-agent switch: PR #35 `fd779ae` (2026-05-13, "multiagent system can be activated in the config"). Re-enabled for A/B comparison: PR #36 `84e8deb` (2026-05-21) + UAT branch-comparison runner (`de0dc82`…). Deleted for good: `3323cb4` (2026-06-11). Confirmed in `config.py` comment: "programme-specific subagents … removed entirely". |
| **Status** | **retired** — single lead agent + one retrieval tool is the architecture of record (see `hsg-rag-architecture-contract`). |

---

## 4. Weaviate free-trial cluster expiry — the 404 outage

| | |
|---|---|
| **Symptom** | Retrieval dead: Weaviate cloud endpoint returning 404; bot degraded to no-context answers. |
| **Root cause** | The project ran on a Weaviate Cloud **free-trial/sandbox cluster**, which expires; on expiry the endpoint vanishes. The cluster URL was hardcoded in `config.py`, so every expiry required a **code change** to point at a new cluster. |
| **Evidence** | `2326992` (2026-01-12): "moved weaviate cloud rest endpoint variable from config.py to .env variables to exclude the need for code update on cluster free trial timeout". `DEPLOYMENT_CHECKLIST.md` §10: "Weaviate-Cluster-Status (läuft, nicht abgelaufen — Lehre aus dem 404-Ausfall)". Paid cluster since: `0fc01e0` ("replication factor config since the paid weaviate servers require a different factor"). |
| **Status** | **fixed-believed** (paid EU cluster `eu-central-1.aws`, URL in env) — but cluster-status monitoring is an **open** checklist item (§10). |

---

## 5. HF Inference API embeddings with silent BM25 fallback

| | |
|---|---|
| **Symptom** | Unstable/degraded retrieval quality that was hard to notice: when remote vectorization failed, search silently fell back to keyword-only BM25. |
| **Root cause** | Embeddings were generated via the Hugging Face Inference API (rate-limited, flaky); the failure path swallowed the downgrade. A silent fallback means you cannot distinguish "hybrid search worked" from "we quietly ran BM25". |
| **Evidence** | `AUDIT_LATENCY_HALLUCINATIONS.md` diagnosis item 5. Replaced: `ecc0043` (2026-06-15) — app-side OpenRouter `openai/text-embedding-3-small`, self-provided vectors in Weaviate, tiktoken tokenization, **BM25 fallback only after logged embedding/vector-query failures**. |
| **Status** | **fixed-verified** (import + live retrieval on this path verified 2026-07-07). Rule of thumb this bought: fallbacks must log loudly. |

---

## 6. The Hugging Face Space deployment era

| | |
|---|---|
| **Symptom** | A public HF Space (`Pygmales/hsg_rag_eea`) served as de-facto deployment; the GitHub→HF sync workflow broke repeatedly; the Space imposed HF constraints (tokens, headers) on the repo. |
| **Root cause** | HF Space was a stopgap before real infrastructure existed. Sync via workflow is brittle (auth, force-push semantics), and a Space is the wrong place for a GDPR-conscious EU production bot. |
| **Evidence** | Sync added `81f51b8` (2026-06-15); fix chain `16fba15` → `dbb86cf` ("fixed HF sync **for real**") → `0fdd439` → `e6ced91`; HF headers workaround `e7f08b0`. Removed with the Space deployment: `bff7867` (2026-07-06, PR #63); `HUGGING_FACE_API_KEY` secret deleted (checklist §7). Production is the Hetzner EU host (`chatbot.emba.unisg.ch`) with auto-deploy (`.github/workflows/deploy.yml`, PR #68). Note: the user testing that produced the 10-defect overhaul plan ran against the Space URL (`docs/chatbot_overhaul_plan.md` header). |
| **Status** | **retired** — anyone mentioning "the bot on Hugging Face" is working from stale knowledge. |

---

## 7. CSP `frame-ancestors` pointed at the wrong university domain

| | |
|---|---|
| **Symptom** | (Latent — caught before go-live.) The iframe embedding on the actual target sites would have been silently blocked by every browser. |
| **Root cause** | `deploy/Caddyfile` allowed `https://*.hsg.ch`, but the EMBA sites live on `*.unisg.ch` and `embax.ch`. Plausible-looking domain, wrong zone. |
| **Evidence** | Fix `a08cba0`, merged `b45b359` (PR #56, 2026-07-04). Header verified live 2026-07-07: `frame-ancestors https://*.unisg.ch https://embax.ch https://*.embax.ch`. |
| **Status** | **fixed-believed** — header is correct and served, but the real cross-origin iframe test on an `emba.unisg.ch` page is still pending the web team (checklist §6/§9). |

---

## 8. Streaming `finish_reason` concatenation killed streaming for all retrieval turns

| | |
|---|---|
| **Symptom** | Every retrieval question: 12–14 s with **nothing** visible until the end; logs showed `Model returned an empty response, reason - tool_callstool_calls! Retrying...` then `Streaming failed ... falling back to blocking invoke`. Two LLM calls per turn silently wasted (double cost). Facts-only questions (2–3 s, no tool call) were unaffected — which disguised the bug. |
| **Root cause** | Under streaming, LangChain chunk aggregation **string-concatenates** `response_metadata.finish_reason` across chunks (OpenRouter emits it on more than one chunk) → `"tool_callstool_calls"`. The middleware's exact-match check `finish_reason != 'tool_calls'` (`src/rag/middleware.py`) then misclassified every valid tool-call response as empty → retries → abort → blocking fallback. |
| **Evidence** | Fix `334da90`, PR #67 (2026-07-07): check `result.tool_calls` directly, never the aggregated string. Verified live pre/post: first token ~4 s, total ~6 s (was 14.2 s), zero retry/fallback warnings since deploy. |
| **Status** | **fixed-verified**. Watchdog: `grep "empty response\|falling back" /opt/hsg-rag/logs/logs.log` — any new hit means a regression of this class (see `hsg-rag-diagnostics-and-tooling`). Lesson: **never exact-match aggregated streaming metadata.** |

---

## 9. Streaming leaked raw structured-output JSON to users

| | |
|---|---|
| **Symptom** | During streaming, users briefly saw raw JSON (`{"response": "...`) instead of prose. |
| **Root cause** | The agent streams a *structured output* (JSON with `response`, booking flags, etc.); naive streaming shows the serialization, not the answer. |
| **Evidence** | `5f7e82b` (2026-06-11): incremental JSON **field** parser extracts only the `response` field live (`src/rag/stream_parser.py`, fuzz-tested across chunk boundaries/escapes/unicode in `tests/test_stream_parser.py`). |
| **Status** | **fixed-verified** (73/73 in the verified-facts + stream-parser release-gate pair, incl. parser fuzz, 2026-07-07 — the full offline suite is larger; see `hsg-rag-validation-and-qa`). Any future change to the structured-output schema must keep the parser in sync. |

---

## 10. Gibberish / off-topic handler oscillation

| | |
|---|---|
| **Symptom** | Two failure directions, alternating: (a) valid queries rejected as gibberish (including multi-word questions and short programme names); (b) obvious keyboard-mash and off-topic input reaching the LLM. Also: "restaurant" was matched but "restaurants" was not. |
| **Root cause** | Deterministic input filtering is a sensitivity dial with no free lunch; the handlers were also **deleted during the overhaul and had to be restored**. Word-boundary/plural handling in ScopeGuardian was buggy. |
| **Evidence** | Tightened `a3c16d6` → loosened `2bbd25a` ("was rejecting too much") → Kinjalk-era fix `3e2d919` → **restored after overhaul deletion** `83314df` (2026-06-18) → false positives again `1400ec6` (2026-06-19, PR #47). Plural matching `5ed653c`; off-topic dedupe PR #54 (`32f69dd`, `5ae5e05`, `57205b4`). Tests: `tests/test_input_handler_gibberish.py`, `tests/test_scope_guardian_offtopic.py`, `tests/test_invalid_input_escalation.py`. |
| **Status** | **managed** — current calibration holds (offline tests green 2026-07-07), but any tweak to `InputHandler`/`ScopeGuardian` must run those three test files; expect to trade false positives for false negatives. |

---

## 11. Language-detection false positives ("emba X" is not English+German)

| | |
|---|---|
| **Symptom** | German queries mentioning "emba X" (or other programme names) triggered mixed-language clarification prompts; users got asked to pick a language instead of an answer. |
| **Root cause** | Language heuristics scored programme names/anglicisms as English tokens inside German sentences. |
| **Evidence** | `93b51db` (2026-06-22, PR #51: "stop agent treating 'emba X' as a language mix"), `c6d8d17` (PR #52, mixed-language false positives), `0fec3d2` (programme-name rule), PR #50 clarification-flow saga (`392fba8`, `1ec1973`…), `d596b04` (language-neutral word detection tests). Tests: `tests/test_language_handling.py`. |
| **Status** | **fixed-believed** — covered by offline tests; the heuristic lives in `src/rag/language_detection.py`. |

---

## 12. LLM judge / eval flakiness

| | |
|---|---|
| **Symptom** | UAT/eval suites failing on unchanged code: judge returned malformed JSON (scored 0), single sampling flakes failed the whole suite, judge disagreed with correct pricing answers, date-dependent tests rotted. |
| **Root cause** | LLM-as-judge is stochastic and schema-unreliable; strict per-case gates amplify noise. |
| **Evidence** | `d39f79c` (judge pricing expectations), `da91e71` (average-only scoring), `88d2eaa`+`b9a7c60` (stricter `UAT_MIN_SCORE=9`), `532baba` (2026-06-30: split into average AND per-case thresholds), `8d0136d` (2026-07-06: retry each fact-eval case once), `c48b2c1` (2026-07-06: retry malformed judge JSON instead of scoring 0), `ca11dec` (date-independent deadline test). |
| **Status** | **managed** — the settled mechanics are: one retry per case, retry-don't-zero on malformed JSON, avg+per-case thresholds. A single red case on rerun is signal, not noise. Gate remains 31/31 (`RUN_LLM_EVAL=1`). |

---

## 13. Facts pipeline false alarms and misses

| | |
|---|---|
| **Symptom** | Diff alerts fired on paraphrasing/no real change; some real facts missed (IEMBA locations); workflow couldn't push its commit; structure facts extracted wrong. |
| **Root cause** | LLM extraction of volatile facts is noisy in both directions; workflow permissions were wrong initially. |
| **Evidence** | `6fd07c8` (no alerts on paraphrase), `5dbb34a` (false-positive change detection), `00f3789` (ignored IEMBA locations), `b431091` (workflow commit permissions), `3ab6508` (error handling), `0effa37`/`3a5e1e4` (missing facts), extraction prompt's `materially_changed` conservatism rules (`src/pipeline/update_programme_facts.py` ~line 130–160), `a0d5a5f` (2026-07-06: **parse programme structure deterministically from page fact tables** — took structure out of the LLM's hands entirely). |
| **Status** | **fixed-believed** — daily runs green; alert chain verified end-to-end 2026-07-07 (deliberate wrong fee → diff detected → email+slack dispatched → self-healing commit `be9cc80`). Pattern that works here: deterministic parsing where the page structure allows it, LLM extraction only for the rest. |

---

## 14. Docling returns near-empty PDF text

| | |
|---|---|
| **Symptom** | Facts pipeline silently lost PDF-sourced facts (fee/payment-plan PDFs) when docling produced ~empty text. |
| **Root cause** | Docling can fail quietly on some PDFs; no guard existed. |
| **Evidence** | `3f33dd7` (2026-07-06, PR #62): pypdf fallback in `extract_pdf_text` when docling output is near-empty; `0c3b038` added pypdf to requirements. Side effect: killed the last `HUGGING_FACE_API_KEY` dependency (checklist §7). |
| **Status** | **fixed-verified** (facts runs green with PDF sources present in `programme_facts.json` `sources`). |

---

## 15. Bare "EMBA" triggered a clarification counter-question

| | |
|---|---|
| **Symptom** | German users asking about "der EMBA" got "which programme do you mean?" instead of an answer. |
| **Root cause** | The agent treated "EMBA" as ambiguous across EMBA HSG / IEMBA / emba X. Domain rule: in German, bare "EMBA" **always** means EMBA HSG. |
| **Evidence** | `230eaa7` (2026-07-06, PR #59). Domain rule codified in `AGENTS.md` non-negotiable #5 and `emba-domain-reference`. |
| **Status** | **fixed-verified** (eval cases cover it). Related settled rule: EMBA answers must never contain IEMBA/emba-X prices — contamination guards in `tests/test_llm_fact_eval.py`. |

---

## 16. Apertus as main reasoning model — tried, retired

| | |
|---|---|
| **Symptom** | (Experiment, not incident.) Attempt to run Apertus as the main model, with 512-token cap for speed. |
| **Root cause of retirement** | Not stated in-repo; superseded by routing all roles through OpenRouter `openai/gpt-4.1` (PR #49 `dd087b5`). No apertus reference survives in `config.py`/`src/`. |
| **Evidence** | `d3a4a8b` (2026-05-19), `cd85a8a` (merged apertus branch, max tokens 512). |
| **Status** | **retired** — model swaps must go through the eval gate (31/31) per `hsg-rag-change-control`. |

---

## 16a. Calendly `primary_color` theming — tried, empirically dead (2026-07-12)

| | |
|---|---|
| **Symptom** | (Experiment, not incident.) Attempt to brand the booking calendar HSG-green via Calendly's `primary_color` embed param. Available days rendered as green filled circles with green digits — unreadable. |
| **Root cause of retirement** | Calendly derives ALL accents (day-chip fill, digit, month arrows, slot buttons) as tone-on-tone variants of the one `primary_color`; there is no separate text color for day chips, and CSS injection into their cross-origin iframe is impossible. Setting ANY custom value — including Calendly's own default blue `0069ff` as control — switches available days from the legible default (pale chip, dark digit) to filled circles with tone-on-tone digits. |
| **Evidence** | Six headless-Chrome renders of the live booking page (2026-07-12): `008435`, `00702d`, `003415`, `99cfb3`, `cce7d9`, `0069ff`, plus parameterless default. Only the default is readable. Documented in the code comment at `BASE_BOOKING_PARAMS` (`src/const/data_consent_constants.py`). |
| **Status** | **retired** — do not re-add `primary_color` (any value). If a green calendar is ever wanted: account-level branding in the advisors' Calendly accounts renders through a different path (`custom_theme_allowed` in their bundle) — that is a stakeholder request (`hsg-rag-stakeholder-comms`), not an embed param. |

---

## 17. Dead and dormant branches — what's in them, why they stalled

61 branches exist; these are the notable unmerged ones (checked with `git merge-base --is-ancestor <b> main`, 2026-07-07):

| Branch | Ahead | Contents | Verdict |
|---|---|---|---|
| `Kinjalk` | 33 | Pre-overhaul UAT-fix era: aggressive-user handling, proactive handover, gpt-4o experiments | Superseded by the June overhaul; mine for ideas only, never merge |
| `bot_prompts` | 16 | Prompt-button UI state preservation, "fixed weird bugs" | Dormant UI work; unreviewed |
| `chat_preserve` | 7 | Session-based chat storage, language-pref localStorage, frontend asset restructure | Dormant; conflicts with current app structure likely |
| `chatbot-ui-overhaul` | 5 | Booking-flow widget refactor, expandable details button | Partially ported to main via `14d7265`/`06cb089`; rest stale |
| `database-interface` | 4 | DB management UI work | Dormant |
| `bot-tone` | 3 | Early tone-softening prompts (`2fa9c27`, `ba9b074`) | Superseded by overhaul + PR #26 tone work |
| `booking-handover-followups` | 2 | Lead-prompt reduction **plan docs** | The actual fix merged via PRs #32/#33; branch is doc residue |
| `feat/toggle_lang` | 1 | Language toggle experiment | Superseded (toggle exists in app) |
| `fix/cache-removal-review` | 1 | Merge commit only | Empty residue of PR #41 |

Merged-and-done (safe to ignore): `er-169-user-led-booking-handover` (PR #30), `er-171-programme-positioning` (PR #31), `fix/chatbot-overhaul`, `chore/openrouter-models` (PR #49), `diana-feature`, `claude/dreamy-lamarr-6ac951`.

**Rule:** resurrect code from a dead branch only after diffing it against current `main` — most of these predate the overhaul and target deleted architecture.

---

## 18. The ten UX defects of the overhaul plan — believed fixed

`docs/chatbot_overhaul_plan.md` documents ten behavioral defects found in user testing of the HF Space deployment (RAG never called; "would you like more details?" loop; profile echoed every turn; cannot positively position programmes; mirroring user input; scope guardian blocking the target audience; single-item lists; substance only after ~10 turns; 100 words of filler; booking widget never appears). The maintainer states all ten are fixed **[maintainer testimony, 2026-07-07]**; the eval/UAT suites cover most behaviors, but the ten were **not individually re-verified** against the plan. If a symptom resembling one of them reappears, read that plan section first — it names root causes and file locations.

**Status:** **fixed-believed**.

---

## When NOT to use this skill

- You need the *current* rules for making a change → `hsg-rag-change-control`.
- You are triaging a *live* symptom right now → `hsg-rag-debugging-playbook` (it links back here for historical traps).
- You want the current architecture and its invariants → `hsg-rag-architecture-contract`.
- You need programme/domain facts → `emba-domain-reference`.
- You want to run/deploy/measure → `hsg-rag-run-and-operate`, `hsg-rag-diagnostics-and-tooling`.
- You are designing *new* experiments → `hsg-rag-research-methodology` / `hsg-rag-research-frontier`; this file only tells you which paths are already fenced off.

## Provenance and maintenance

Compiled 2026-07-07 from: `git log --oneline --all`, `git show` of the cited commits (cache internals read from `git show 0c2eb13~1:src/cache/...`), branch ancestry checks, `AUDIT_LATENCY_HALLUCINATIONS.md`, `docs/chatbot_overhaul_plan.md`, `DEPLOYMENT_CHECKLIST.md`, and maintainer statements of 2026-07-07 (labeled inline). PR-number attributions come from merge-commit subjects (`git log --grep "Merge pull request"`); GitHub PR discussion threads were **not** readable from this environment — entries 1 and 16 reconstruct *rationale* partly from code + testimony.

Re-verification one-liners (run before trusting volatile claims):

```bash
git log --oneline -5                                   # has history moved past 2026-07-07?
git show dd98ea3 --stat | head -20                     # cache removal is real and merged
ls src/cache 2>/dev/null || echo "cache still gone"    # entry 1 still holds
grep -n "tool_calls" src/rag/middleware.py             # entry 8 fix still in place
grep -rn "apertus\|subagent" config.py src/ --include=*.py | grep -vi removed  # entries 3/16
for b in Kinjalk bot_prompts chat_preserve; do git rev-list --count main..$b; done  # entry 17 drift
RUN_LLM_EVAL=1 python -m pytest tests/test_llm_fact_eval.py -q  # gate still 31/31 (paid; interpreter: see hsg-rag-build-and-env)
```

Maintenance rule: when a new investigation ends (fix merged, approach rejected, or revert), append an entry here in the same symptom→root-cause→evidence→status format, and move any entry whose status changed (e.g. `fixed-believed` → `fixed-verified` after re-measurement). One home per fact: link to sibling skills instead of duplicating their content.

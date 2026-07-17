---
name: hsg-rag-conversion-campaign
description: Executable, decision-gated campaign for the project's hardest live problem (as of 2026-07-07) — improving answer quality and the conversion of chats into advisor appointments. Load this when asked to "improve conversion", "get more bookings", "improve answer quality", "measure the funnel", "check the overhaul defects", "tune the booking widget", or to plan any prompt/UX change whose goal is more advisor appointments. Do NOT load for bug triage (hsg-rag-debugging-playbook) or for running tests as such (hsg-rag-validation-and-qa).
---

# HSG-RAG Conversion Campaign

**Goal (north-star metric, set by the maintainer 2026-07-07):** more chats end in a
booked appointment with the right programme advisor, without making the bot pushy.
The 10 UX defects in `docs/chatbot_overhaul_plan.md` are *believed* fixed but have
never been re-verified individually — this campaign starts by measuring, not by editing.

**Prime directive: measurement before optimization.** As of 2026-07-07 there are NO
conversion analytics. Any prompt/UX change made before Phase 0 completes is a guess
and must be rejected in review.

## When NOT to use this skill

- A defect/regression is already confirmed → `hsg-rag-debugging-playbook`.
- You only need to run the eval/UAT suites → `hsg-rag-validation-and-qa`.
- You need the change process itself (gates, PR rules) → `hsg-rag-change-control`.
- You need programme facts/domain language → `emba-domain-reference`.
- You need to contact advisors/web team/IT → `hsg-rag-stakeholder-comms`.

## What "conversion" means here (the funnel)

The bot cannot observe actual Calendly bookings — booking happens inside Calendly
iframes (`src/const/data_consent_constants.py`, `BOOKING_WIDGET_HTML`: a collapsed
`<details>` element below the chat with three advisor buttons that lazy-load Calendly).
The observable funnel today, per session:

| Stage | Source of truth (verified 2026-07-07) |
|---|---|
| 1. Session started + consent | `logs/consent/<session_id>.jsonl` — `{"decision": "accepted"\|"declined", "timestamp", "policy_version"}` |
| 2. Active conversation | `logs/user_profiles/profile_<session_id>_<ts>.json` snapshots (one per extraction event); fields: `suggested_program`, `program_interest`, `user_language`, `handover` (true/false/null) |
| 3. Appointment intent (**pre-gate model flags** — see caveat below) | `logs/logs.log` lines from `agent_chain` (src/rag/agent_chain.py:773-775): `Appointment Requested: True`, `Show Booking Widget: True`, `Relevant Programs: [...]` |
| 4. Actual Calendly booking | **NOT observable in this repo.** Requires advisor/Calendly cooperation — route via `hsg-rag-stakeholder-comms` |

Log line format (src/utils/logging.py): `(%Y.%m.%d %H:%M:%S) <logger-name>\t LEVEL: message`.
**Constraint:** `logs.log` lines carry NO session id, so concurrent sessions interleave;
use logs.log only for aggregate counts, and consent+profile files (which carry
`session_id`) for per-session funnel joins.

**Pre-gate vs post-gate flags (do not conflate):** the `:773-775` lines log the
model's RAW `structured_response` flags, BEFORE the post-processing gate at
`src/rag/agent_chain.py:833-872` (commit `55fa853`) computes the FINAL flags the
UI receives. The gate can suppress booking state ("Suppressed booking state
because no programme match or booking intent was detected."), grant it
proactively ("Proactive booking offer triggered ..."), or force the widget when
the answer text commits to showing it
(`_response_commits_to_showing_booking_widget`). The final flag values are NOT
logged unconditionally (verified 2026-07-08) — so the countable stage-3 metric
is **pre-gate model intent**, not "widget shown to the user".
`scripts/funnel_report.py` additionally counts the two conditional post-gate
lines above as correction signals. If you need the true widget-shown rate,
first add an unconditional post-gate log line (a code change via
`hsg-rag-change-control`).

**GDPR constraints (do not violate):**
- `logs/user_profiles/` has a 30-day deletion cron on the prod host — longitudinal
  analysis beyond 30 days is impossible by design; snapshot aggregates weekly.
- Log/profile content is personal data. Aggregate on the host or locally; never paste
  raw profiles or query text into PRs, issues, or external tools. Report only counts/rates.
- Query wording no longer appears in logs (`chatbot_app`'s 100-char leak was
  closed in `413dd1f`); still treat `logs.log` conservatively as personal data
  when excerpting.

---

## Phase 0 — Establish the baseline (no product changes allowed)

1. Pull one week of funnel data from the prod host (maintainers have SSH alias
   `hsg-rag-prod`; logs live in `/opt/hsg-rag/logs/`). Copy `scripts/funnel_report.py`
   from this skill to the host or run it over an rsynced copy of `logs/`:

```bash
python3 scripts/funnel_report.py /opt/hsg-rag/logs
```

   It reports: consent accepted/declined counts, sessions with ≥1 profile snapshot,
   sessions with `handover: true`, per-programme `suggested_program` distribution,
   aggregate `Show Booking Widget: True` / `Appointment Requested: True` counts
   from `logs.log` (pre-gate model intent — see the caveat above), and the two
   post-gate correction-line counts (proactive offers, suppressions).

2. Record the numbers in the campaign log (a dated section in the PR that will carry
   your eventual change — see `hsg-rag-docs-and-writing` for house style).

**GATE 0 — you have a baseline when** you can state, over ≥1 week of production logs:
(a) consent-acceptance rate, (b) widget-flag rate (pre-gate) per accepted session, (c)
appointment-flag rate (pre-gate) per accepted session. If traffic is too low to compute
these (the bot is not yet embedded in the EMBA site as of 2026-07-07), STOP and
report that the campaign is blocked on the iframe go-live — optimizing without
traffic is unfalsifiable.

## Phase 1 — Re-verify the 10 overhaul defects (audit, still no changes)

`docs/chatbot_overhaul_plan.md` lists 10 defects (§"The Ten Problems"). For each,
run the discriminating probe against production via the Gradio API
(pattern verified 2026-07-07; the venv has `gradio_client`):

```python
from gradio_client import Client
c = Client("https://chatbot.emba.unisg.ch/", verbose=False)
c.predict(api_name="/on_accept")                       # consent
r = c.predict(message="<probe>", api_name="/_chat")    # returns final answer
```

| # | Defect (short) | Probe | Pass criterion |
|---|---|---|---|
| 1 | RAG never called | "Was macht die HSG besonders?" | Specific retrieved facts (network sizes, course names), not generic prose |
| 2 | "More details?" loop | "Nenne mir drei Gründe für den EMBA" | All three reasons in ONE answer, no dangling offer |
| 3 | Profile echoed each turn | 3-turn convo after stating background | Background mentioned ≤1× after first use |
| 4 | No positive positioning | "Ist der EMBA gut für Tech-Führungskräfte?" | Answer-first, then concrete value framing |
| 5 | Mirrors input before answering | Any question | Answer does not restate the question |
| 6 | Scope guard blocks target users | "Ich führe seit 12 Jahren ein Team, was passt zu mir?" | Substantive recommendation, not a scope rejection |
| 7 | One-item lists | "Vorteile des IEMBA?" | Lists have ≥2 items or use prose |
| 8 | Substance only after ~10 turns | Turn 1–2 informational questions | Substance immediately |
| 9 | 100 words of filler | Any answer | Word budget spent on facts (MAX_RESPONSE_WORDS_LEAD=100, config.py:185) |
| 10 | Widget never appears | "Ich möchte einen Termin mit einer Beraterin" | Answer names advisor + widget flag True |

**GATE 1:** all 10 pass → Phase 2. Any failure → this is a *regression*, not a
conversion experiment: switch to `hsg-rag-debugging-playbook`, fix under normal
change control, then re-run Phase 0/1. Do not blend regression fixes into
conversion experiments — you will not be able to attribute metric movement.

## Phase 2 — Ranked solution menu (one experiment at a time)

Booking is deliberately **user-led** (src/rag/prompts.py:141-146): flags turn on only
when (a) the user explicitly asks to book, or (b) a programme is clearly identified
AND the user signals readiness ("is this right for me?"). Routine turns keep both
flags `False`. This rule embodies the maintainer's trust posture — experiments may
sharpen condition (b), never abolish the user-led principle.

Note: those prompt rules only shape the model's RAW flags. The runtime gate at
`src/rag/agent_chain.py:833-872` (suppression / proactive offer /
text-commitment override, commit `55fa853`) post-processes them into the final
UI flags — a prompt-only change may therefore not move the logged/final flags
as expected. Treat the gate as a second lever and a confounder when
interpreting Phase-0 numbers.

Before running ANY option: write the hypothesis with a **predicted number**
("widget-show rate x% → y% because …"). No prediction, no experiment.

Ranked by expected value ÷ risk:

1. **Readiness-signal tuning (prompt, low risk).** Sharpen rule (b) examples in
   `src/rag/prompts.py` for readiness phrasings observed in Phase 0 logs that did
   NOT trigger the widget. Obligation: full eval battery (below) + Phase-1 probes
   #3/#5/#10 (guard against pushiness regressions).
2. **Soft-handover copy quality (prompt, low risk).** The "clear contact path"
   turn (prompts.py:140) is the pre-widget conversion moment; improve its
   concreteness per stage. Same obligations.
3. **Widget discoverability (UI, medium risk).** The widget is a *collapsed*
   `<details>` below the chat (`BOOKING_WIDGET_HTML`); when the bot says "slots are
   shown below", a collapsed element may be missed. Options: auto-expand only on
   `show_booking_widget=True` turns, or visual affordance. Obligation: manual UI
   check on desktop + narrow viewport (iframe embed!), plus Phase-1 probe #10.
4. **Stage-sensitive positioning depth (prompt, medium risk).** prompts.py:157
   already mandates stage matching; experiment with richer expressed-interest
   framing. Watch UAT tone scores — hype destroys credibility (prompt bans
   "best/world-class/perfect/guaranteed").
5. **First-token latency (infra, high effort, unproven link).** ~4 s to first token
   (2026-07-07; baseline numbers owned by `hsg-rag-debugging-playbook` § Healthy
   baselines). No evidence yet that this affects conversion here; only attempt
   with a Phase-0-observed drop-off signal. See `hsg-rag-diagnostics-and-tooling`.

**Eval battery for every option** (see `hsg-rag-validation-and-qa` for details):

```bash
python -m pytest -q                                   # offline suite
RUN_LLM_EVAL=1 python -m pytest tests/test_llm_fact_eval.py -v   # must be 31/31
RUN_UAT_LLM_JUDGE=1 python -m pytest tests/test_uat_llm_judge.py -v -s
# UAT gate: average ≥ 8.5 AND every case ≥ 8.0
#   (UAT_AVERAGE_MIN_SCORE / UAT_CASE_MIN_SCORE; thresholds owned by hsg-rag-validation-and-qa)
```

(Interpreter choice is machine-specific — see `hsg-rag-build-and-env`; on the
maintainer's Mac pytest runs via `/opt/anaconda3/bin/python -m pytest`, the repo
venv lacks pytest. Keys: the fact eval needs `OPEN_ROUTER_API_KEY` +
`WEAVIATE_*`; only the UAT judge needs `OPENAI_API_KEY` — see
`hsg-rag-validation-and-qa`.)

## Fenced-off wrong paths — do not reopen

| Path | Why it is fenced |
|---|---|
| Request-path caching (response/semantic caches) | **The costliest failure in project history** (maintainer, 2026-07-07): cache layers made behavior non-deterministic and untrustworthy; removed in PR #41 (`src/cache/` no longer exists). Never reintroduce caching on the request path. |
| Programme sub-agents | Removed in the June 2026 overhaul (`AUDIT_LATENCY_HALLUCINATIONS.md`): doubled LLM calls, added latency, no quality gain. |
| Growing the lead prompt with more content | Overhaul Problem 1 root cause: prompt bloat made the model answer from the prompt and skip retrieval. Add rules only with matching deletions; keep facts in `programme_facts.json`/retrieval. |
| Auto-showing/opening the widget on every turn | Violates the user-led booking rule; historically flagged as patronising behavior (overhaul Problems 3/10 context). Pushiness is a conversion killer for this audience. |
| Hand-editing `data/database/programme_facts.json` | Auto-generated daily; edits are overwritten and page the team. |

## Validation and promotion protocol

A/B testing is infeasible: one host, one container, no experiment framework.
Use **before/after windows**:

1. Fixed-length baseline window (≥1 week of prod logs, Phase 0 numbers).
2. Ship exactly ONE experiment via normal change control (`hsg-rag-change-control`:
   PR, maintainer OK, merge to `main` auto-deploys).
3. Equal-length after-window; rerun `scripts/funnel_report.py`; compare against the
   prediction you wrote down BEFORE shipping.
4. Promote (keep + document in the campaign log) only if the metric moved as
   predicted AND the eval battery stayed green. Otherwise revert and record the
   negative result — a documented dead end is a deliverable, not a failure.

Success is never judged by eye. "The answers feel better" is not evidence here.

## Provenance and maintenance

Written 2026-07-07 against `main` @ d76d050. Facts verified against:
`src/rag/agent_chain.py:772-775` (pre-gate funnel log lines) and `:833-872`
(post-processing gate, commit `55fa853`), `src/rag/prompts.py:138-149`
(user-led booking rule), `src/apps/chat/app.py` (consent logging, query logging),
`src/utils/logging.py` (log format), `config.py:23,174,182,185`,
`tests/test_uat_llm_judge.py:50` (UAT threshold), `docs/chatbot_overhaul_plan.md`
(the 10 defects), live prod logs (2026-07-07 format samples).

Re-verify before trusting:

```bash
grep -n "Appointment Requested\|Show Booking Widget" src/rag/agent_chain.py
grep -n "Suppressed booking state\|Proactive booking offer" src/rag/agent_chain.py  # post-gate lines
grep -n "show_booking_widget=True" src/rag/prompts.py
grep -n "MAX_RESPONSE_WORDS_LEAD\|TOP_K_RETRIEVAL" config.py
grep -n "UAT_AVERAGE_MIN_SCORE" tests/test_uat_llm_judge.py
ls logs/consent logs/user_profiles | head   # data layout drift
```

Volatile: latency numbers, traffic assumptions, and the "not yet embedded" status
are as of 2026-07-07 — recheck the deployment checklist before quoting them.

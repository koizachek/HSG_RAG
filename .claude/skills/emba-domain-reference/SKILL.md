---
name: emba-domain-reference
description: >
  Domain knowledge pack for the HSG Executive MBA advisory chatbot. Load this
  when a task touches programme facts (EMBA HSG / IEMBA HSG / emba X), tuition
  or deadline logic, advisors and Calendly booking, the admissions/conversion
  funnel and its structured-response flags (appointment_requested,
  show_booking_widget, relevant_programs), language/naming rules (bare "EMBA",
  British English, "HSG" usage), positioning and tone rules, or GDPR-relevant
  data flows (consent, user profiles, log masking, US processing). Also load it
  before editing prompts, response schemas, or any test that asserts programme
  facts.
---

# EMBA Domain Reference

The domain semantics behind this repo: what the three programmes are, how money
and deadlines work, what "conversion" means, and which rules about language and
positioning are load-bearing. A mid-level engineer who knows RAG but not this
business will break things without this file.

**Volatile numbers below are dated examples (as of 2026-07-07).** The live
source of truth is `data/database/programme_facts.json` — auto-regenerated
daily from official sources. Teach yourself the structure here; always re-read
the JSON for current values. **Never hand-edit that file** (see
`hsg-rag-change-control`).

## When NOT to use this skill

| You need… | Use instead |
|---|---|
| How to change/gate/review code | `hsg-rag-change-control` |
| Why the system is built this way | `hsg-rag-architecture-contract` |
| A bug triage path | `hsg-rag-debugging-playbook` |
| Running/deploying the app | `hsg-rag-run-and-operate` |
| Test/eval discipline | `hsg-rag-validation-and-qa` |
| Improving conversion (the live campaign) | `hsg-rag-conversion-campaign` |

## 1. The three programmes are three distinct products

Never blur them. The LLM eval suite has contamination guards: quoting an IEMBA
price in an EMBA answer is a release blocker.

| | **EMBA HSG** | **IEMBA HSG** | **emba X** |
|---|---|---|---|
| Official name | Executive MBA HSG | International Executive MBA HSG | EMBA ETH HSG ("emba X") |
| JSON key (`programmes.*`) | `emba` | `iemba` | `emba_x` |
| Language of instruction | German | English | English |
| Positioning | German-language, DACH-focused; "leading German-language postgraduate business programme" | International (Tokyo, Beijing, UC Berkeley, UC Irvine, …) | Joint ETH Zürich + HSG; tech / innovation / transformation |
| Cohort naming (2026-07-07) | EMBA 71 | IEMBA 14 | emba X6 |
| Duration | 18 months (extendable to max 48) | 18 months | 18 months |
| ECTS | 75 | 75 | 75 |
| Advisor | Cyra von Müller | Kristin Fuchs | Teyuna Giger |

Cohort names appear in official PDFs and page copy (`Neuer-Dataplan-EMBA71…`,
`IEMBA-14-info-sheet…`); the facts pipeline tracks the current cohort in
`programmes.<key>.current_cohort`.

**Programme language ≠ UI language.** The chat UI runs in `de` or `en`
(user-selectable); each programme has its own language of instruction stored
under `programmes.<key>.language` with *both* a `de` and `en` rendering (e.g.
IEMBA's is `"de": "Englisch"`, `"en": "English"`). Do not infer programme
choice from UI language alone — see the routing heuristic in §5.

## 2. Deadline-based tuition mechanics

Every programme has two application deadlines with two fees in
`programmes.<key>.tuition_chf`:

```json
"tuition_chf": {
  "first_deadline": { "deadline": "2026-06-29", "fee": 72500 },   // reduced
  "final_deadline": { "deadline": "2026-08-10", "fee": 77500 },   // full
  "note": { "de": "...", "en": "..." }
}
```

Dated example (2026-07-07): EMBA 72'500→77'500 CHF, IEMBA 80'000→85'000 CHF,
emba X 99'000→110'000 CHF. **Re-read the JSON before asserting any number.**

The load-bearing rule — since `413dd1f` (2026-07-08), `src/rag/verified_facts.py`
serves the model a **precomputed deadline state** instead of a prose date rule
(`_deadline_passed`, `_render_programme`; same-day = not passed):

- each deadline line is tagged `[EXPIRED]`/`[ABGELAUFEN]` or
  `[applies today]`/`[gilt heute]`, so the model never does date arithmetic;
- when the **final** deadline has passed, the block appends `APPLICATIONS
  CLOSED` / `BEWERBUNG GESCHLOSSEN`: no fee may be presented as currently
  available; interested users are referred to the advisor for the next cohort.

Implications for engineers:

- The bot's correctness is **date-relative**. A test asserting "the fee is
  72'500" is wrong the day after `first_deadline` passes. Tests must compute
  expected values from the JSON + today's date (the eval suite does this —
  commit `ca11dec` made a hard-facts test date-independent after it went stale).
- `VerifiedFacts` caches the JSON **in process memory** on first load
  (`_data` classvar). A running container does not see file changes; facts
  updates reach production only via the rebuild+redeploy pipeline
  (`hsg-rag-run-and-operate`).

## 3. Source-of-truth chain for volatile facts

```
Official pages/PDFs (emba.unisg.ch, embax.ch, es.unisg.ch, fee PDFs)
  → .github/workflows/update_programme_facts.yml   (daily 06:23 UTC)
    → src/pipeline/update_programme_facts.py       (scrape → LLM extract → diff)
      → data/database/programme_facts.json         (committed by the action)
        → src/rag/verified_facts.py                (renders DE/EN prompt block)
          → lead agent system prompt               (authoritative for volatile facts)
```

Material diffs (fees, deadlines, starts) dispatch an email + Slack alert before
the corrected file is committed. Retrieval (Weaviate) covers everything *else*:
USPs, structure details, rankings, alumni network. Volatile facts come from the
prompt block, never from retrieved chunks — that separation is the 2026-06
hallucination fix (`hsg-rag-failure-archaeology`).

## 4. The admissions funnel and conversion

The business north-star metric (stated by the maintainer, 2026-07-07): **conversion
to booked advisory appointments with the programme advisors.** The funnel:

```
anonymous visitor → consent → informational Q&A → programme fit emerges
  → advisory appointment booked (Calendly)  ← THE conversion event
    → application (handled by humans, outside the bot)
```

### Structured-response flags (the conversion levers)

Defined in `StructuredAgentResponse` (`src/rag/utilclasses.py:28`):

| Field | Semantics | Funnel role |
|---|---|---|
| `response` | Main answer text | Information stage |
| `additional_details` | Optional expandable section. **Critical facts (tuition, duration, deadlines, eligibility, direct answers) must NOT be moved here** | Keeps main answer scannable |
| `appointment_requested` | `True` ONLY on explicit booking intent or acceptance of a consultation offer | Intent detection |
| `show_booking_widget` | `True` ONLY when `appointment_requested` is `True` and the widget should appear now | Conversion trigger |
| `relevant_programs` | Subset of `['emba','iemba','emba_x']`; empty if undecided | Routes to the right advisor |

The lead prompt (`src/rag/prompts.py`, BOOKING & APPOINTMENTS block) allows the
flags to go `True` in exactly two cases: **(a)** the user explicitly asks to
book/schedule/see slots/speak with admissions or accepts a prior offer, or
**(b)** a programme is clearly identified AND the user signals readiness for a
personal consultation ("is this right for me?", commitment after a
recommendation). Routine pricing/comparison/fit questions keep both flags
`False` — booking is **user-led**, the bot must not push the widget.

Note: those prompt rules govern the model's RAW flags. The runtime
post-processes them before the UI sees them (suppression / proactive-offer /
text-commitment gate, `src/rag/agent_chain.py` around `:960-1035`; locate with
`grep -n "booking_flow_requested" src/rag/agent_chain.py`); the per-turn log
lines (`Appointment Requested:` / `Show Booking Widget:`, around `:920`) show
the pre-gate values — see `hsg-rag-conversion-campaign` for the measurement
caveat.

### Booking surface

- The widget is Gradio HTML (`BOOKING_WIDGET_HTML` in
  `src/const/data_consent_constants.py`): a collapsible section with one button
  per advisor that loads their **Calendly inline embed** in a nested 520 px
  iframe, with params `?hide_gdpr_banner=1&embed_type=Inline&embed_domain=chatbot.emba.unisg.ch&hide_event_type_details=1`
  (as of PR #76, 2026-07-12). Do NOT add `primary_color` — any custom value
  makes Calendly's available days unreadable; see
  `hsg-rag-failure-archaeology` ("Calendly primary_color theming").
- Advisors (also in `programmes.<key>.advisor` and `ADVISOR_CONTACTS`):

| Programme | Advisor | Email | Phone | Calendly (as of 2026-07-07) |
|---|---|---|---|---|
| EMBA | Cyra von Müller | cyra.vonmueller@unisg.ch | +41 71 224 27 12 | calendly.com/cyra-vonmueller/beratungsgespraech-emba-hsg |
| IEMBA | Kristin Fuchs | kristin.fuchs@unisg.ch | +41 71 224 75 46 | calendly.com/kristin-fuchs-unisg/iemba-online-personal-consultation |
| emba X | Teyuna Giger | teyuna.giger@unisg.ch | +41 71 224 77 65 | calendly.com/teyuna-giger-unisg |

- **Wrong-advisor routing is a serious defect** — a Kristin Fuchs booking for
  an EMBA prospect wastes both parties' time and loses the lead.
- The bot must never fabricate booking URLs or buttons ("Do not generate URLs
  or fake buttons. Never say you cannot book appointments."). Soft handovers
  (no explicit booking ask) use the general contact: **emba@unisg.ch /
  +41 71 224 27 02**.
- No-fit users get HSG cross-sell only (mba.unisg.ch, op.unisg.ch) — never
  external programmes. Visa/permit questions → redirect to admissions.

## 5. Language and naming rules (each has a history)

1. **Bare "EMBA" means EMBA HSG.** "der EMBA", "the EMBA", "the programme" →
   answer with EMBA HSG verified facts directly; **never ask which programme is
   meant**. IEMBA/emba X enter only when the user names them or asks for a
   comparison. (Prompt AMBIGUITY block; fixed in commit `230eaa7` after the bot
   annoyed users with clarification counter-questions.)
2. **Pitch questions are not ambiguity.** "Why HSG?" / "was macht die HSG
   besonders?" → retrieval by language heuristic, no clarification question.
3. **Routing heuristic when no programme is named** (single-programme answers
   only): German + DACH focus → EMBA HSG; English + international focus →
   IEMBA; tech/innovation/transformation focus or tech background → emba X.
   Broad discovery / cross-programme comparison → cover all three; never narrow
   to EMBA just because the query is German.
4. **"HSG" only inside official programme names** ("EMBA HSG"); the institution
   is referred to by its full name (template var `{university_name}`).
5. **English persona speaks professional British English**; complete sentences,
   university-level tone, no casual phrasing ("Great to meet you").
6. Language selection/locking happens **before** the agent (local heuristic in
   `src/rag/language_detection.py`); the agent must obey the injected
   response-language instruction and never reclassify.

## 6. Positioning discipline

From the prompt POSITIONING/ELIGIBILITY blocks (`src/rag/prompts.py`):

- **Stage-sensitive framing:** early discovery → balanced and factual;
  expressed interest in one programme → answer the question first, then add
  positive value framing for that programme (specific retrieved facts, not
  generic praise).
- **Hype ban:** "best", "world-class", "world-leading", "perfect",
  "guaranteed" are forbidden unless retrieved source material explicitly
  supports them. Credibility is the product.
- **No profile-parroting:** use profile data to shape answers, never to repeat
  the user's situation back at them (an original overhaul defect,
  `docs/chatbot_overhaul_plan.md` Problem 3).
- Eligibility verdicts belong to admissions: state published criteria, note the
  final decision is made by admissions, offer a contact path when borderline.

## 7. GDPR data flows in plain terms

Full document: `docs/datenschutz_deployment.md` (draft, pending sign-off by
the data protection officer — DSB/Datenschutzbeauftragte:r, also called DPO —
as of 2026-07-07). What an engineer must know:

- **Consent gate:** no chat until the user accepts the privacy notice
  (`PRIVACY_NOTICE` in `src/const/data_consent_constants.py`; UI logic in
  `src/apps/chat/app.py`). Decline → static message with `emba@unisg.ch`.
  Consent events are logged to `logs/consent/` (kept indefinitely as proof).
- **User profiles** (`logs/user_profiles/*.json`, flag `TRACK_USER_PROFILE`):
  session ID, optionally name, experience/leadership years, field, interests,
  programme interest, language. Deleted after **30 days** by a host cron.
- **Log masking:** user inputs are redacted in application logs (length only,
  no wording) since 2026-07-06; the last known gap — `src/apps/chat/app.py`
  logging the first 100 chars of each raw query — was closed in `413dd1f`
  (2026-07-08). Masking is complete as of that commit (see
  `hsg-rag-architecture-contract` I5 for the re-verify command). Do not add
  any new raw-text logging.
- **Third parties:** OpenRouter (**US** — user messages are sent there for LLM
  processing; conscious-decision documentation still open), Weaviate Cloud
  (EU; only search queries, no profiles), LangSmith (disabled in production),
  Hetzner (DE; host + 7-day backup rotation).
- **Deletion path:** `wipe_session_data` implements in-UI withdrawal; backups
  cap effective post-deletion retention at 7 days.

## Provenance and maintenance

Written 2026-07-07 against commit `d76d050`. Everything volatile is
re-verifiable in seconds:

```bash
# Current fees/deadlines/cohorts/advisors (THE source of truth):
jq '.generated_at, (.programmes | map_values({current_cohort, tuition_chf, advisor}))' \
  data/database/programme_facts.json

# Advisors + Calendly URLs used by the booking widget:
grep -A6 "ADVISOR_CONTACTS" src/const/data_consent_constants.py | head -30

# Structured-response flag semantics:
sed -n '/class StructuredAgentResponse/,/^class /p' src/rag/utilclasses.py

# Deadline-state labels (expired / applies today / closed):
grep -n "applies_today\|APPLICATIONS CLOSED" src/rag/verified_facts.py

# Bare-EMBA ambiguity rule:
grep -n 'der EMBA' src/rag/prompts.py

# GDPR retention table:
sed -n '/## 2. Welche Daten/,/## 3./p' docs/datenschutz_deployment.md
```

If any command returns nothing, the underlying fact has moved — update this
skill before trusting it again.

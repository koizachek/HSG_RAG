# Chatbot Overhaul Plan

## Context

User testing of the deployed chatbot at https://huggingface.co/spaces/Pygmales/hsg_rag_eea surfaced ten distinct behavioural and structural defects. Individually each is small. Combined they undermine the credibility of the whole product: an MBA programme that markets innovation and tech-led leadership cannot be represented by a chatbot that talks down to candidates, withholds substance, and fails to convert clear interest into advisor bookings.

The fix spans four files. It is not a system-prompt patch.

## The Ten Problems

### Problem 1 — RAG never gets called
The lead agent answers from the system prompt and almost never invokes `call_emba_agent`, `call_iemba_agent`, or `call_embax_agent`. Because the lead prompt carries full pricing, programme-snapshot, USP, and recommendation content, the model has everything it needs to answer locally. Result: high latency and generic answers that ignore retrieved content from Weaviate.

Root cause: the lead prompt has accumulated sub-agent responsibilities. It mixes orchestration, static facts, and content generation in one always-on context.

Location: `src/rag/prompts.py` `_LEAD_SYSTEM_PROMPT` (~190 lines).

### Problem 2 — "Would you like more details?" loop
The bot offers more details and never delivers them. Asked for three reasons, it returns one or two and ends with "Would you like me to continue?". On follow-up it repeats or adds a single point. The promise is structurally unfulfillable.

Root cause: two prompt rules combine destructively:
- `_BASE_PROGRAM_PROMPT`: *"If response would exceed 100 words, provide most relevant info and offer more details"*
- Multiple prompts: *"Maximum 100 words per response"*

The model truncates the list to fit the budget, offers continuation, and on the next turn applies the same budget. The list never completes.

Location: `src/rag/prompts.py` (both `_LEAD_SYSTEM_PROMPT` response format and `_BASE_PROGRAM_PROMPT` response format).

### Problem 3 — User profile echoed in every response
The bot prefixes responses with the user's own profile data: *"For your situation (20 years in manufacturing, South Africa, being asked to take over a department)..."*. The user already knows this. Mentioning it once when introducing a recommendation is useful. Repeating it on every turn is patronising and consumes the response budget.

Root cause: positioning rules in the lead prompt incentivise demonstrating attentiveness with no explicit cap on how often profile context is restated.

Location: `src/rag/prompts.py` `_LEAD_SYSTEM_PROMPT` positioning and tone rules.

### Problem 4 — Cannot positively position the programmes
Asked *"why should I choose HSG?"* or *"what is special about it?"* the bot either misclassifies as off-topic ("I am here to help with questions about EMBA programmes...") or returns generic bullets that any school could claim. Concrete differentiators that exist in the scraped RAG content — FT ranking position, alumni network, programme USPs — never appear.

Root cause: combination of Problem 1 (RAG not called), Problem 6 (scope guardian over-blocks), and the response-format rules that force generic compression.

Location: `src/rag/prompts.py` (lead + sub-agent prompts), `src/rag/scope_guardian.py`.

### Problem 5 — Mirroring the user's input before answering
Responses begin with paraphrased validation of the user's previous message: *"You are absolutely right to be critical — 'we have several programmes' is not a reason to choose any school."* This adds nothing the user does not already know and consumes the response budget.

Root cause: tone rules in the lead prompt include phrasing examples like *"Thank you for your interest"* that the model generalises into mirroring patterns.

Location: `src/rag/prompts.py` `_LEAD_SYSTEM_PROMPT` tone rules.

### Problem 6 — Scope guardian blocks the target audience
A user mentioning a medical or healthcare background — *"Ich habe bereits einen Doktor in Medizin"*, *"ich komme aus der medizin"*, *"I'm a doctor"* — gets the off-topic redirect. Healthcare and medical professionals are a primary target audience for executive education. They are being filtered out at the scope-check stage.

Root cause: `OFF_TOPIC_KEYWORDS` includes `'health'`, `'medical'`, `'gesundheit'`, `'medizin'` ([scope_guardian.py:17](../src/rag/scope_guardian.py:17)). The keyword check matches these as off-topic regardless of context.

Secondary code bug at [scope_guardian.py:67](../src/rag/scope_guardian.py:67): multi-word keywords are split and matched per individual word, so `"payment plan"` matches any message containing the word `"plan"`.

Location: `src/rag/scope_guardian.py`.

### Problem 7 — Single-item bullet points and numbered lists
Responses contain a single bulleted or numbered item. Lists imply more content is coming. A single point should be prose.

Root cause: response-format rule says "use bullet points or short paragraphs" without a minimum-items rule.

Location: `src/rag/prompts.py` response format rules.

### Problem 8 — Substantive content only after ~10 turns
The agent eventually surfaces meaningful differentiators ("Strength in managing complexity, not just theory", concrete integrations of strategy/operations) but only after many turns of progressive prompting. By that point a real prospect has left.

Root cause: cascade of Problem 2 (drip mechanism), Problem 4 (no early substantive positioning), and stage-sensitive positioning rules that bias the early conversation toward conservative/balanced answers when the user is actively asking to be sold to.

Location: `src/rag/prompts.py`.

### Problem 9 — 100 words used for filler, not substance
The 100-word limit is not too low for a chat. It is appropriate. The defect is that responses spend ~50% of the budget on filler: opening validations, profile echoes, "would you like to continue" closers. Less than half the budget reaches actual content.

Root cause: prompt-level filler patterns documented in Problems 2, 3, 5. No change to the 100-word limit needed; remove the filler and the budget becomes sufficient.

Location: `src/rag/prompts.py` and `config.py` (config stays unchanged).

### Problem 10 — Booking widget never appears
The booking widget exists in code and is wired through `LeadAgentQueryResponse.show_booking_widget`, but in user testing it never fires. The chatbot's primary conversion goal — handing a qualified user to an advisor — does not happen.

Root cause: in [agent_chain.py:947](../src/rag/agent_chain.py:947), `booking_flow_requested` requires `explicit_booking_intent` or `booking_preference_follow_up`. The user has to explicitly request booking. Soft offers never escalate to a visible widget. The earlier "user-led booking" change ([commit 0061f41](https://github.com/koizachek/HSG_RAG/commit/0061f41)) was correct in spirit but tuned too strict.

A proper trigger uses the assessment that already exists in the code:
- `_conversation_state['suggested_program']` set by `_determine_suggested_program()` ([agent_chain.py:577](../src/rag/agent_chain.py:577))
- `structured_response.relevant_programs` returned by the lead model

When a programme match exists in this assessment AND the model signals readiness (`show_booking_widget=True`), the widget should appear without requiring the user to explicitly ask.

Location: `src/rag/agent_chain.py` and `src/rag/prompts.py` booking policy section.

## Files Changed

| File | Problems addressed |
|------|---------------------|
| `src/rag/scope_guardian.py` | 6, partial 4 |
| `src/rag/agent_chain.py` | 10 |
| `src/rag/prompts.py` (`_LEAD_SYSTEM_PROMPT`) | 1, 2, 3, 5, 7, 8, 9, 10 |
| `src/rag/prompts.py` (`_BASE_PROGRAM_PROMPT`, `_PROGRAM_DEFINITIONS`) | 4, 2, 7 |
| `config.py` | (no change — Problem 9 fixed via prompt) |

## Plan

### Step 1 — `src/rag/scope_guardian.py`

- Remove `'health'`, `'medical'`, `'gesundheit'`, `'medizin'` from `OFF_TOPIC_KEYWORDS`.
- Fix the multi-word keyword bug. Replace the per-word `in words_list` check with a substring/whole-phrase check against the lowercased message.
- No structural changes beyond these two fixes.

### Step 2 — `src/rag/agent_chain.py` booking trigger

In `_query_lead`, replace the strict trigger with one that uses the existing assessment:

```python
clear_programme_match = (
    self._conversation_state.get('suggested_program') is not None
    or bool(structured_response.relevant_programs)
)
proactive_booking_offer = (
    clear_programme_match
    and structured_response.show_booking_widget
)
booking_flow_requested = (
    explicit_booking_intent
    or booking_preference_follow_up
    or proactive_booking_offer
)
```

The `clear_programme_match` gate is the safety: the model can suggest the widget, but the code only honours it when the assessment chain has actually identified a programme.

### Step 3 — `src/rag/prompts.py` shared response-format rules

These rules apply to both lead and sub-agent prompts.

Remove:
- *"If response would exceed 100 words, provide most relevant info and offer more details"*
- Tone phrasing examples that encourage opening validations (`"Thank you for your interest"`, `"Your profile appears to align well"`).

Add:
- Explicit ban on opening with paraphrased restatement of the user's previous message ("You are absolutely right…", "Thank you for sharing…", "For your situation, X years in Y…" as a recurring opener).
- Profile data is used to inform the answer, not narrated back. Reference profile context at most once per recommendation, not per turn.
- Lists require ≥2 items. A single point is written as a sentence.
- If the user requests N items, all N are delivered in the same response. Do not truncate and offer continuation.
- "Would you like me to continue with more details?" and equivalents are forbidden. Either complete the answer or state the limit upfront.
- 100-word limit is a substance budget. Filler counts against it.

### Step 4 — `src/rag/prompts.py` `_LEAD_SYSTEM_PROMPT` rewrite

Target length: ~50 lines, down from ~190. Keep:
- Branding/naming (compact).
- Concise tone rules (the negatives from Step 3, plus the British-English/professional baseline).
- One stage-sensitive positioning rule (not three paragraphs of examples).
- One consolidated booking-policy block: when to set `show_booking_widget=True`. Allow the model to set it once a programme is matched and the user signals consultation interest ("is this right for me?", "would HSG suit me?", "does this fit my profile?"). The code gate (`clear_programme_match`) prevents misfires.
- Ambiguity rule (generic "the EMBA" → ask which one).
- Tool routing — explicit and mandatory: for any substantive question about a specific programme (USPs, ranking, fit, structure beyond the basic snapshot), call the relevant sub-agent. The lead does not answer programme-specific content from its own prompt.

Remove from the lead prompt:
- AUTHORITATIVE TUITION FIGURES block (sub-agents own this).
- AUTHORITATIVE PROGRAMME SNAPSHOT block (sub-agents own this).
- TECH BACKGROUND HANDLING (becomes a one-line routing note).
- IEMBA VS. EMBA X RECOMMENDATION HANDLING block (becomes a one-line routing note; detail moves to sub-agents).
- EMBA X USP HANDLING block (moves to emba X sub-agent).
- CROSS-SELLING RULES large block (compress to: "Out-of-scope alternative requests → mention https://op.unisg.ch/en/").
- DIAGNOSTIC & RECOMMENDATION LOGIC decision tree (compress to a 3-line routing heuristic; detail moves to sub-agents).
- Repeated accommodation/inclusion reminders (sub-agents have this).

### Step 5 — `src/rag/prompts.py` sub-agent prompts

`_BASE_PROGRAM_PROMPT`:
- Apply the shared response-format rules from Step 3.
- Add an explicit instruction: when the user asks about distinctiveness, USPs, ranking, "what is special", or "why this programme", ground the answer in concrete facts from `retrieve_context()` — name specific rankings, alumni network attributes, programme features. Do not paraphrase into generic phrasing.

`_PROGRAM_DEFINITIONS`:
- Keep the authoritative programme facts that already live here (tuition, eligibility, format, locations).
- Per-programme positioning hints stay short — they orient the agent, but factual selling content (rankings, alumni network size, recent achievements) comes from RAG, not from hardcoded text.

## Verification

Manual verification against the user-testing scenarios captured in screenshots. Tests are not the success bar.

| Problem | Acceptance criterion |
|---------|----------------------|
| 1 | Logs show `call_*_agent` invocations on substantive questions ("what is special", "why HSG", "tell me more about emba X"). Lead prompt under ~60 lines. |
| 2 | "Give me 3 reasons" returns 3 complete reasons in one response. No "Would you like to continue?". |
| 3 | After turn 2, profile data is not echoed verbatim ("For your situation, 20 years in manufacturing…"). |
| 4 | "Why HSG?" / "What is special?" returns a substantive answer with concrete facts retrieved from RAG. |
| 5 | No opening with paraphrased validation of the user's last message. |
| 6 | "Ich komme aus der Medizin" / "I'm a doctor" routes as on-topic. |
| 7 | A response with one item is prose, not a numbered or bulleted list. |
| 8 | Strongest programme differentiators appear in turns 2–3 of substantive engagement, not turn 10. |
| 9 | The 100-word budget is filled with content, not filler — visibly higher information density. |
| 10 | After a clear programme match plus user readiness signal, the booking widget appears without an explicit "book" command. |

## Order Of Execution

1. `scope_guardian.py` — small, isolated, reversible.
2. `agent_chain.py` — booking trigger change, contained diff.
3. `prompts.py` — shared response-format rules.
4. `prompts.py` — lead prompt rewrite.
5. `prompts.py` — sub-agent prompt adjustments.
6. Manual verification against screenshot scenarios.

Each step is a separate commit on `fix/chatbot-overhaul`.

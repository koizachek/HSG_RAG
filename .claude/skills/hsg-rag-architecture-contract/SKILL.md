---
name: hsg-rag-architecture-contract
description: Load-bearing design decisions, system invariants, and known weak points of the HSG_RAG chatbot. Load BEFORE changing anything in src/rag/ or src/apps/chat/, before adding caching/sub-agents/routers/new LLM roles, when asking "why is there no X here", when tracing the request path end to end, or when a change might violate an invariant (fact contamination, consent gate, streaming, log redaction). Explains WHY the architecture is shaped this way so you don't reintroduce a removed failure.
---

# HSG_RAG Architecture Contract

The one-paragraph system: a **single lead agent** (gpt-4.1 via OpenRouter,
structured output) answers advisory questions about three St.Gallen executive
programmes. Volatile facts (prices, deadlines, starts, advisors) are **injected
into the system prompt** from an auto-generated facts file; everything else
comes from **one retrieval tool** against Weaviate Cloud (EU). Responses
stream token-by-token through an incremental JSON parser into a Gradio UI that
sits behind a consent gate, served by Caddy on a single EU host.

This skill is the contract: what the architecture guarantees, why it is shaped
this way, and where it is known to be weak. **If your change violates a
decision or invariant below, stop and route through `hsg-rag-change-control`.**

## When NOT to use this skill

| You want to… | Use instead |
|---|---|
| Classify/gate/review a concrete change | `hsg-rag-change-control` |
| Debug a live symptom (latency, wrong answer, 500s) | `hsg-rag-debugging-playbook` |
| Learn what was tried and abandoned, with evidence | `hsg-rag-failure-archaeology` |
| Understand the three programmes, fees, advisors | `emba-domain-reference` |
| Look up a config knob or add one | `hsg-rag-config-and-flags` |
| Set up an environment or run/deploy the app | `hsg-rag-build-and-env`, `hsg-rag-run-and-operate` |
| Measure instead of reason (timing, counts, evals) | `hsg-rag-diagnostics-and-tooling` |

## 1. Request path (verified 2026-07-07)

```
Browser ──HTTPS──> Caddy (TLS, reverse proxy, CSP frame-ancestors)   deploy/Caddyfile
                     └─> container port 7860 (host-mapped 127.0.0.1 only, deploy.yml)
  Gradio/FastAPI app  src/apps/chat/app.py
    consent gate: chat UI hidden until Accept        app.py:77 (consent_screen), :149 (on_accept)
    per-session agent: ExecutiveAgentChain created
      on Accept, held in gr.State                    app.py:99 (initialize_agent)
    _chat generator: worker thread runs agent.query,
      main thread yields streamed deltas to the UI   app.py:264
  Agent chain          src/rag/agent_chain.py
    preprocessing: local language detection, scope
      check, input validation                        query() at :558, [timing] logs :722/:727
    _query → _invoke_streaming (agent.stream) with
      blocking agent.invoke as fallback              :1042 / :1010
    middleware wraps every model + tool call         src/rag/middleware.py:56, :117
    retrieval tool 'retrieve_context' → Weaviate,
      TOP_K_RETRIEVAL=8, empty result returns
      explicit NO_CONTEXT_FOUND (never "")           agent_chain.py:104, :148
  Stream parser        src/rag/stream_parser.py
    extracts the `response` JSON field live from the
    structured-output token stream (ResponseFieldStreamParser)
```

Deployment context: the container binds 0.0.0.0:7860 internally
(app.py:381) but is published only on the host loopback
(`-p 127.0.0.1:7860:7860`, .github/workflows/deploy.yml:75). The only public
entry is Caddy on 443.

## 2. Load-bearing decisions and WHY

Each of these replaced something that failed in production. The rationale is
the contract — do not undo one without reading its history in
`hsg-rag-failure-archaeology` and `AUDIT_LATENCY_HALLUCINATIONS.md` (repo root).

| Decision | Rationale (the failure it prevents) |
|---|---|
| **Single lead agent — NO sub-agents** | Programme-specific sub-agents doubled LLM calls and let the lead answer from its own bloated prompt instead of retrieving. Deleted June 2026. Multi-agent exists only offline (facts extraction pipeline). |
| **NO regex/keyword fact routers** | ~2,000 lines of regex fact extraction assigned prices to the wrong programme — deterministic bugs indistinguishable from hallucinations. Deleted June 2026. |
| **NO caching in the request path** | `src/cache/` made answers stale and unsafe (the project's costliest failure class; removed via PR #41). Correctness beats latency here. Do not add response/retrieval caches. |
| **NO blocking quality-eval call** | A post-hoc LLM scoring call added seconds per turn and could not detect hallucinations (it never saw the retrieval context). `ENABLE_EVALUATE_RESPONSE_QUALITY = False` in config.py stays False. |
| **Verified-facts prompt injection** | Volatile facts (fees, deadlines, starts, advisors) come from `data/database/programme_facts.json`, auto-generated daily from official sources, rendered into the system prompt (`VerifiedFacts.render_prompt_block`, src/rag/verified_facts.py:153, injected at src/rag/prompts.py:240). Retrieval chunks are NOT trusted for these numbers. The facts pipeline is the **sole writer** of that file — never hand-edit it. |
| **Retrieval for everything else** | One tool, `retrieve_context`, chunks carry `[programme \| source]` metadata headers; empty context returns explicit `NO_CONTEXT_FOUND` so the model cannot silently fill gaps from world knowledge. |
| **Local-first language detection** | Stopword/script heuristics in src/rag/language_detection.py; the LLM detector (gpt-4o-mini) is a lazy fallback for genuine ambiguity only. Replaced a per-turn LLM call. |
| **Streaming with blocking fallback** | Perceived latency = time-to-first-token, not the full pipeline (current numbers: `hsg-rag-debugging-playbook` § Healthy baselines). The fallback to `agent.invoke` exists for robustness but firing it is a **regression** (see invariant I4). |
| **Bounded everything** | `MAX_HISTORY_MESSAGES = 16`, `MODEL_MAX_RETRIES = 2`, exactly one fallback model (`gpt-4o-mini`), short timeouts (config.py:38–42, :174–182). Unbounded history and retry×fallback multiplication caused 15–40 s turns pre-overhaul. |
| **Single host behind Caddy** | Deliberate simplicity: one Hetzner EU host, Docker, Caddy for TLS + CSP. GDPR-motivated EU hosting. Merge to `main` auto-deploys (see `hsg-rag-run-and-operate`). |

## 3. Invariants — MUST hold at all times

Violating any of these is a release blocker, regardless of how the change
otherwise scores.

- **I1 — No cross-programme fact contamination.** An EMBA HSG answer must never
  contain IEMBA or emba X fees/deadlines and vice versa. Enforced by prompt
  design and by explicit contamination guards in the LLM eval suite
  (`tests/test_llm_fact_eval.py`, 31 cases, release gate 31/31).
- **I2 — Bare "EMBA" means EMBA HSG.** "der EMBA" / "the EMBA" is answered
  directly with EMBA HSG facts — the bot must NOT ask which programme is meant
  (prompt rule in src/rag/prompts.py; regression fixed in PR #59 after the bot
  counter-questioned).
- **I3 — Consent precedes chat.** No agent is constructed and no user text is
  processed before the user accepts the privacy notice (app.py: chat screen
  hidden, agent created in `on_accept`). Decline shows a contact hint and keeps
  chat locked.
- **I4 — Retrieval turns stream.** `_invoke_streaming` must yield deltas for
  tool-using turns. Log lines `Model returned an empty response` or
  `falling back to blocking invoke` mean streaming is broken again (incident
  2026-07-07, fixed in PR #67 — full mechanism and story:
  `hsg-rag-failure-archaeology` #8). Watch for it after any langchain/
  OpenRouter/model change.
- **I5 — User text in logs must be redacted.** Every log statement touching
  user text goes through `_redact_user_text` (src/rag/agent_chain.py:43);
  never add new raw-text logging. The last known gap — `src/apps/chat/app.py`
  logging the first 100 chars of each raw query — was closed in `413dd1f`
  (2026-07-08); `Processing user query:` is redacted too. Masking is complete
  as of that commit; re-verify with
  `grep -rn "message\[:" src/` before repeating that claim to the DSB (see
  `hsg-rag-stakeholder-comms` §3, `hsg-rag-run-and-operate` §7).
- **I6 — Empty retrieval is explicit.** `retrieve_context` returns
  `NO_CONTEXT_FOUND: ...` sentinel text, never an empty string
  (agent_chain.py:148).
- **I7 — Port 7860 is never publicly exposed.** Only Caddy (443) faces the
  internet; the container port is mapped to 127.0.0.1 on the host.

## 4. Known weak points (as of 2026-07-07) — stated plainly

Do not "discover" these; they are known. Improving one is welcome but routes
through change control.

| Weak point | Status |
|---|---|
| `programme_facts.json` is **baked into the Docker image** and cached in process memory. Facts changes reach production only via a rebuild+redeploy. Mitigated (not eliminated) by the auto-deploy after every successful nightly facts run. | Accepted, mitigated |
| **EN collection is smaller than DE** (144 vs 227 objects at last count). embax.ch is English-only (0 DE objects from it); German emba X content arrives via emba.unisg.ch articles. EN answers may have thinner retrieval grounding. | Open, monitor |
| **User inputs are processed in the US** (OpenRouter; embeddings likewise). The documented GDPR decision / EU-hosting alternative is an open item in DEPLOYMENT_CHECKLIST.md §2. Do not claim EU-only processing anywhere. | Open decision |
| **Serial first-token latency on retrieval turns**: tool-decision call → Weaviate query → answer call run serially; facts-only turns are markedly faster (current numbers: `hsg-rag-debugging-playbook` § Healthy baselines). Known trade-off; candidate optimizations exist but none adopted. | Accepted |
| **Single host, no HA, no external uptime monitoring** on `/health` yet (checklist §10 open). An outage is currently noticed by users first. | Open |
| **Answer quality / booking conversion** is the current hardest problem (not correctness or latency). See `hsg-rag-conversion-campaign`. | Active work |

## Provenance and maintenance

Written 2026-07-07 against `main` @ d76d050. All file:line anchors verified on
that commit. Re-verify before trusting:

- Anchors drift: `grep -n "_invoke_streaming\|def query" src/rag/agent_chain.py`
  and `grep -n "tool_calls" src/rag/middleware.py`
- Config values: `grep -n "MAX_HISTORY\|TOP_K\|FALLBACK\|MODEL_MAX_RETRIES" config.py`
- Facts injection point: `grep -n "render_prompt_block" src/rag/prompts.py src/rag/verified_facts.py`
- Collection counts (weak point 2): re-run an aggregate count against both
  Weaviate collections before quoting numbers.
- CSP/domains: `cat deploy/Caddyfile`
- Port mapping: `grep -n "127.0.0.1" .github/workflows/deploy.yml`
- Streaming invariant: `ssh hsg-rag-prod 'grep -c "falling back to blocking" /opt/hsg-rag/logs/logs.log'`
  (count must not grow; alias is maintainer-local — any SSH access to the host works)

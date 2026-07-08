# AGENTS.md — Working on HSG_RAG as an AI Agent

Guidance for AI coding agents (Claude Code sessions, subagents, other assistants)
working in this repository. Humans: see [README.md](README.md) first.
Deep-dive runbooks live in `.claude/skills/` — load the skill whose description
matches your task before improvising.

## What this is

A German/English RAG chatbot advising prospective students on three University
of St.Gallen executive programmes: **EMBA HSG** (German-language), **IEMBA HSG**
(English-language), and **emba X** (joint ETH/HSG). Production runs at
`https://chatbot.emba.unisg.ch` on a dedicated Hetzner EU host, embedded as an
iframe on `emba.unisg.ch`. This is a **live production system serving real
prospective students** — treat `main` accordingly.

## Non-negotiables

1. **Merging to `main` deploys to production.** `.github/workflows/deploy.yml`
   runs on every push to `main` (doc-only changes excluded): rsync → image build →
   container recreate → health checks. Never merge anything you would not deploy.
2. **Propose before you edit.** The maintainer expects a short justification and
   an explicit OK before code changes are made. Diagnose freely; edit after approval.
3. **No AI co-author trailers.** Do not add `Co-Authored-By: Claude ...` (or
   similar) to commits or PR bodies.
4. **Never hand-edit `data/database/programme_facts.json`.** It is auto-generated
   daily by `.github/workflows/update_programme_facts.yml` from official sources
   and any manual edit will be overwritten (and, if materially wrong, will page
   the team via email/Slack). The only sanctioned manual edit is a deliberate
   alert-chain test, which the workflow self-heals.
5. **Programme facts must never cross-contaminate.** A question about the EMBA
   must never be answered with IEMBA or emba X prices/deadlines. The LLM eval
   suite has explicit contamination guards; treat any such mix-up as a release
   blocker. Also: a bare "EMBA" in German always means EMBA HSG — the bot must
   not ask which programme is meant.
6. **Secrets stay out of the repo and out of logs.** Runtime secrets live only
   in `.env` (local) and `/opt/hsg-rag/.env` on the host (chmod 600). User inputs
   are masked in logs (GDPR); keep it that way.
7. **PR-based flow.** Branch from `main`, open a PR, the maintainer merges.
   Direct pushes to `main` only when a procedure requires it (e.g. alert-chain test).

## Environment and commands

Two Python interpreters are in play — this trips up every new session:

| Purpose | Interpreter |
|---|---|
| Run the app / scripts | `venv/bin/python` (repo venv, Python 3.13) |
| Run pytest | `/opt/anaconda3/bin/python -m pytest` (venv lacks pytest) |

```bash
venv/bin/python main.py --app de              # chat UI (German), FastAPI+Gradio on :7860
venv/bin/python main.py --weaviate checkhealth
venv/bin/python main.py --scrape full         # full scrape + import (slow, hits live sites)

/opt/anaconda3/bin/python -m pytest -q        # offline suite (default: no network/integration)
RUN_LLM_EVAL=1 /opt/anaconda3/bin/python -m pytest tests/test_llm_fact_eval.py -v
                                              # 31 LLM eval cases — release gate: 31/31
RUN_UAT_LLM_JUDGE=1 ... tests/test_uat_llm_judge.py   # UAT judge suite (opt-in, paid)
```

The opt-in suites call paid LLM APIs and need keys from `.env` /
`.env.example`. `OPENAI_API_KEY` is **test-only**; runtime uses exclusively
`OPEN_ROUTER_API_KEY` (all LLM roles + embeddings) plus `WEAVIATE_*`.

## Architecture in one breath

Single lead agent (gpt-4.1 via OpenRouter, structured output) with one
retrieval tool against Weaviate Cloud (EU). Volatile facts (prices, deadlines,
starts, advisors) are injected into the system prompt from
`programme_facts.json` — retrieval covers everything else. Token streaming via
an incremental JSON field parser (`src/rag/stream_parser.py`). There are **no
sub-agents and no regex fact routers** — both were deliberately removed in the
June 2026 overhaul after causing latency and wrong-price hallucinations
(see `AUDIT_LATENCY_HALLUCINATIONS.md` before reintroducing anything similar).

Key paths: `src/rag/agent_chain.py` (chain + timing logs),
`src/rag/middleware.py` (model/tool call wrappers — careful: streaming
aggregates chunk metadata, `finish_reason` strings can concatenate),
`src/rag/prompts.py`, `src/apps/chat/app.py` (Gradio UI + consent flow),
`src/pipeline/update_programme_facts.py` (facts scraper/differ/alerter),
`deploy/Caddyfile` (TLS, CSP `frame-ancestors`).

## Operations quick reference

- Health: `GET https://chatbot.emba.unisg.ch/health` → `{"status":"ok","weaviate":true}`
- Latency: `grep "\[timing\]" logs/logs.log` on the host (`/opt/hsg-rag/logs/`).
  Healthy: facts turns 2–3 s, retrieval turns ~6 s, first token ~4 s.
  Red flags: `empty response` / `falling back to blocking` → streaming is broken again.
- Rollback: previous image is tagged `hsg-rag:previous` on the host.
- Caddy runs on the host via systemd, untouched by app deploys; after editing
  `deploy/Caddyfile`, copy it to the host and `systemctl reload caddy`.
- Host access: maintainers use an SSH alias (`hsg-rag-prod`, root@178.105.196.130).

## Domain language

Answer the maintainer in German when addressed in German; write code, commits,
and PRs in English. The three programmes are distinct products with distinct
advisors (EMBA: Cyra von Müller, IEMBA: Kristin Fuchs, emba X: Teyuna Giger) —
booking handovers must route to the right one.

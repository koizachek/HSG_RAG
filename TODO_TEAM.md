# Team To-dos After the Chatbot Overhaul

Status: 2026-06-11 · Base: branch `master` · Context: `AUDIT_LATENCY_HALLUCINATIONS.md`

## This Week

- [ ] **Review and merge PR `master → main`** — description is in the PR; review focus: `agent_chain.py` (new lean path), `verified_facts.py`, `stream_parser.py`
- [ ] **Deploy to the production server** — new state; check `.env`: `OPENAI_API_KEY`, Weaviate credentials, SMTP/Slack variables (now required for fact-change alerts)
- [ ] **Set up cron on the server** (not just on the dev Mac):
      `0 6 * * * cd <repo> && ./venv/bin/python -m src.pipeline.update_programme_facts >> logs/fact_update.log 2>&1`
- [ ] **Test the alert chain once**: temporarily change a price in `data/programme_facts.json` → `python -m src.pipeline.update_programme_facts` → email/Slack alert must arrive → revert the change
- [ ] **UAT**: 5–10 test dialogues DE/EN by 2–3 people — specifically prices, deadlines, programme comparison, booking flow; file anomalies as issues with the chat transcript

## Weeks 1–2 in Production (monitor)

- [ ] **Latency**: `grep "\[timing\]" logs/rag_chatbot.log` — target ~6s total turn; outliers >10s become issues
- [ ] **Retrieval stability**: count BM25 fallback warnings (`grep "Falling back to BM25"`) — frequent hits = pull the embedding switch forward (see backlog)
- [ ] **Fact updates**: check `logs/fact_update.log` weekly — are the cron runs completing? Are diffs plausible?
- [ ] **Before every release**: `RUN_LLM_EVAL=1 pytest tests/test_llm_fact_eval.py -v` — must be 31/31. Offline tests (`pytest tests/test_verified_facts.py tests/test_stream_parser.py`) on every commit

## Backlog (prioritised)

- [ ] **Move embeddings off the HF Inference API** (OpenAI `text-embedding-3-small` or local) + **re-chunking** 200 → 512–1024 tokens; requires rebuilding the Weaviate collection + re-import. Trigger: frequent BM25 fallbacks or weak long-tail answers
- [ ] **LLM eval as CI gate** (GitHub Action with `RUN_LLM_EVAL=1` on PRs against `main`; secret for the API key budget)
- [ ] **Rework or remove the cache** — currently exact query match per session (hit rate ~0); either normalised/semantic keys or delete the code
- [ ] **Simplify booking logic further** — replace the remaining keyword heuristics in `_query_lead` (explicit booking intent, preference follow-up) with pure structured-output flags
- [ ] **Update the README** — bring architecture sections that still describe subagents/the old pipeline up to date (adopt the diagram from `AUDIT_LATENCY_HALLUCINATIONS.md` §3)
- [ ] Delete `scripts/remove_legacy_code.py` (spent one-shot script, if still present)

## Ground Rules (do not change without discussion)

- **Never hardcode facts** — prices/deadlines/start dates come exclusively from `data/programme_facts.json` (auto-generated). Prompt changes containing numbers get rejected in review.
- **No second LLM call in the request path** (quality evals, classifiers etc. run offline/async)
- **Keep the eval green** — new features get new eval cases in `tests/test_llm_fact_eval.py`

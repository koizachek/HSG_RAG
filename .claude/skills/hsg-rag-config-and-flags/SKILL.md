---
name: hsg-rag-config-and-flags
description: Catalog of every configuration axis in HSG_RAG — model/provider settings, chain knobs (TOP_K, history cap, word budgets), scraping parameters, Weaviate timeouts, notification toggles, environment variables, and GitHub Actions secrets. Load this when you need to know what a config value does, what its real default is, whether it is production-active or legacy, how config.py / env var / code-default precedence works, or how to add a new config axis. Also covers the env-var precedence trap that silently ignores NOTIFY_* overrides.
---

# HSG_RAG Configuration and Flags

All facts verified against the repo on **2026-07-07**. Re-verify with the
one-liners at the bottom before trusting anything volatile.

## The configuration system in 60 seconds

Three layers, resolved by `_get()` in `src/config/configs.py:8`:

1. **`config.py`** (repo root) — the primary source. If a name is defined here, it **wins**.
2. **Environment variable / `.env`** — consulted **only if** the name is absent
   from `config.py` **and** the `_get()` call site passes no non-None default.
3. **Call-site default** in `src/config/configs.py` — used last.

Access pattern everywhere in code: `from src.config import config` then
`config.chain.TOP_K_RETRIEVAL`, `config.llm.MAIN_AGENT_MODEL`, etc. Extra
values not wrapped in a subconfig are read via `config.get('NAME')`, which
reads `config.py` directly (`src/config/__init__.py:20`).

### ⚠️ The precedence trap (costs real debugging time)

```python
value = getattr(config, param, default)   # config.py, else call-site default
if value is None:
    value = os.getenv(param)              # env is ONLY read if that was None
```

Consequences, all verified:

- You **cannot override anything defined in `config.py` via env var**. E.g.
  `NOTIFY_ENABLE_SLACK_ALERTS=false` in the environment is ignored because
  `config.py:200` defines it `True`. The `vars.NOTIFY_ENABLE_SLACK_ALERTS`
  passed by `.github/workflows/update_programme_facts.yml` is therefore a
  **no-op** today.
- You cannot override via env var when the call site has a non-None default:
  `NOTIFY_SMTP_PORT` env var is ignored (call site default `587`), and
  `NOTIFY_SMTP_USE_TLS` env var is ignored (call site default `"True"`).
- Env vars **do** work for names absent from `config.py` with `None` defaults:
  `OPEN_ROUTER_API_KEY`, `WEAVIATE_API_KEY`, `WEAVIATE_CLUSTER_URL`,
  `NOTIFY_SMTP_HOST/USER/PASSWORD`, `NOTIFY_FROM_EMAIL`, `NOTIFY_TO_EMAIL`,
  `NOTIFY_SLACK_WEBHOOK_URL`, `EMBEDDING_API_KEY`.

To change a `config.py` value in production you must **edit `config.py` and
deploy** (merge to `main` → auto-deploy). There is no runtime override.

## LLM / provider axes (`config.llm`, defined in `config.py:33-49`)

All roles run through OpenRouter; the app has no runtime OpenAI dependency.
Model tuples are `('<provider>:<subprovider>', '<model-id>')`.

| Name | Default (config.py) | Gates | Status |
|---|---|---|---|
| `MAIN_AGENT_MODEL` | `('open_router:openai', 'openai/gpt-4.1')` | The single lead agent (`src/rag/models.py:73`) | **Production** |
| `FALLBACK_MODELS` | `[('open_router:openai', 'openai/gpt-4o-mini')]` | Runtime fallback chain (`src/rag/models.py:101`) — deliberately ONE model (latency: retries × fallbacks multiply) | **Production** |
| `LANGUAGE_DETECTION_MODEL` | `('open_router:openai', 'openai/gpt-4o-mini')` | LLM fallback for ambiguous language only; primary detection is a local heuristic (`src/utils/lang.py`) | **Production** (rarely invoked) |
| `CONFIDENCE_SCORING_MODEL` | `('open_router:openai', 'openai/gpt-4o-mini')` | Quality-eval model — dead path while `ENABLE_EVALUATE_RESPONSE_QUALITY=False` | Legacy-parked |
| `SUMMARIZATION_MODEL` | `('open_router:openai', 'openai/gpt-4.1')` | History summarization model (`src/rag/models.py:54`) | Production |
| `LLM_PROVIDER`, `OPENAI_MODEL` | `'openai'`, `'gpt-4.1'` | Compatibility shims for old callers | Legacy |
| `MODEL_MAX_RETRIES` | `2` | Retry loop in `src/rag/middleware.py` (`config.chain.MAX_RETRIES`) — reduced from 3 as a latency fix | **Production** |

**Do not confuse the two `get_fallback_models`:** the runtime one is
`src/rag/models.py:88` (reads `FALLBACK_MODELS`). The classmethod
`LLMConfig.get_fallback_models` in `src/config/configs.py:198` (with its
gpt-oss / tongyi / polaris list) has **no runtime callers** — it is part of the
stale block flagged `#TODO: Clean this configuration (outdated)` at
`src/config/configs.py:131`. Also stale/unused at runtime: `GROQ_*`,
`OLLAMA_*`, `GPT_OSS_ENABLED`, `OPEN_ROUTER_MODEL`
(`meituan/longcat-flash-chat:free`), `HUGGING_FACE_API_KEY`. They are only
reachable via lazy provider imports in `src/rag/models.py` if someone
reconfigures a non-OpenRouter provider — the matching `langchain-*` packages
are intentionally NOT in requirements.txt.

## Agent chain axes (`config.chain`, `config.py:154-195`)

| Name | Default | Gates | Status |
|---|---|---|---|
| `TOP_K_RETRIEVAL` | `8` | Chunks per retrieval query (`src/rag/agent_chain.py:123`). Raised from 4 as a hallucination fix (~800 tokens was too little grounding) | **Production** |
| `MAX_HISTORY_MESSAGES` | `16` | Cap on history sent per turn; `0` = uncapped (latency fix) | **Production** |
| `MAX_RESPONSE_WORDS_LEAD` | `100` (config.py wins over the `350` fallback in configs.py) | Lead answer word budget, used in prompts and `src/rag/response_formatter.py` | **Production** |
| `MAX_RESPONSE_WORDS_SUBAGENT` | `200` | Only feeds prompt templates; subagents themselves were removed | Legacy-parked |
| `ENABLE_RESPONSE_CHUNKING` | `False` | Multi-turn splitting of long answers — disabled: each "continue" turn was a full LLM round-trip | Legacy kill-switch, keep `False` |
| `ENABLE_EVALUATE_RESPONSE_QUALITY` | `False` (the "Defaults to True" comment in config.py is stale) | Blocking post-answer quality eval (`src/rag/agent_chain.py:56,802`) — removed from request path in the June 2026 overhaul. Re-enable only as async/offline eval | Legacy kill-switch, keep `False` |
| `CONFIDENCE_THRESHOLD` | `0.6` | Quality-eval acceptance bar — dead while the flag above is `False` | Legacy-parked |

## Conversation state (`config.convstate`, `config.py:19-31`; `AVAILABLE_LANGUAGES` sits at `config.py:9`)

| Name | Default | Gates |
|---|---|---|
| `TRACK_USER_PROFILE` | `True` | User-preference collection during conversation (profiles land in `logs/user_profiles/`, 30-day deletion on the prod host — GDPR-relevant, see hsg-rag-run-and-operate) |
| `LOCK_LANGUAGE_AFTER_N_MESSAGES` | `3` | Language lock after N user messages; `0` = never lock (`src/rag/agent_chain.py:642`) |
| `MAX_CONVERSATION_TURNS` | `20` | Hard conversation end (`src/rag/agent_chain.py:576`) |
| `AVAILABLE_LANGUAGES` | `['en', 'de']` | Collection naming, chunk routing, UI languages. Adding a language means new Weaviate collection + scrape + prompts — not a one-liner |

## Embeddings and processing (`config.processing`, `config.py:103-122`)

| Name | Default | Notes |
|---|---|---|
| `EMBEDDING_MODEL` | `openai/text-embedding-3-small` | Via OpenRouter; vectors are app-generated and stored in Weaviate |
| `EMBEDDING_BASE_URL` | `https://openrouter.ai/api/v1` | |
| `EMBEDDING_DIMENSIONS` | `1536` | ⚠️ Changing model/dimensions requires `--weaviate redo` + full re-import |
| `EMBEDDING_BATCH_SIZE` | `32` | |
| `EMBEDDING_VECTOR_NAME` | `hsg_rag_embeddings` | Named-vector key in collections |
| `LANG_AMBIGUITY_THRESHOLD` | `0.6` | Below this DE-confidence, detector returns EN (`src/utils/lang.py:47`) |
| `MAX_TOKENS` / `CHUNK_OVERLAP` | `512` / `100` | Chunking geometry; changing them only affects future imports |

## Weaviate axes (`config.weaviate`, `config.py:51-101`)

| Name | Default | Notes |
|---|---|---|
| `WEAVIATE_COLLECTION_BASENAME` | `hsg_rag_content` | Collections are `<basename>_<lang>`: `hsg_rag_content_de` / `_en` |
| `WEAVIATE_REPLICATION_FACTOR` | `3` | Paid HA clusters can require ≥3 |
| `WEAVIATE_INIT_TIMEOUT` / `QUERY_TIMEOUT` / `INSERT_TIMEOUT` | `90` / `60` / `600` s | |
| `WEAVIATE_KEEP_WARM_ENABLED` | `True` | Background idle-query loop (`src/database/weavservice.py:90`) |
| `WEAVIATE_KEEP_WARM_INTERVAL` | `180` s | Was 30 s; raised to cut idle queries 6× |
| `WEAVIATE_CLIENT_IDLE_TIMEOUT` | `1500` s (25 min) | Proactive reconnect of stale clients |
| `WEAVIATE_BACKUP_METHOD` | `'manual'` | Allowed: `manual`, `filesystem`, `s3` |
| `BACKUPS_PATH` / `PROPERTIES_PATH` / `STRATEGIES_PATH` | `data/database/backups` / `data/database` / `src/database/strategies` | |

## Scraping axes (`config.scraping`, `config.py:125-152`)

| Name | Default | Notes |
|---|---|---|
| `SCRAPING_TARGET_URLS` | `emba.unisg.ch`, `embax.ch` | Scrape roots. embax.ch is English-only — 0 DE objects from it is **expected** |
| `SCRAPING_TIMEOUT` | `30` s | |
| `SCRAPING_MAX_RETRIES` | `3` | |
| `SCRAPING_CRAWL_DELAY` | `1` s | Server-sent delays override it |
| `SCRAPING_BACKOFF_RATE` | `1.25` (config.py wins over the `2` fallback in configs.py) | Exponential backoff base |
| `SCRAPING_PRIO_INTERVAL` | high 1 / medium 7 / low 30 days | Re-scrape cadence per priority |

## Paths (`config.paths`, `config.py:5-17`)

`DATA_PATH='data'`, `LOGS_PATH='logs'`; derived outputs `data/urls`,
`data/chunks`, `data/temp_chunks`, `data/scraping`, `data/raw_text`,
`data/raw_html`, `data/metadata`, `data/extracted_text`. On the prod host only
`logs/` is volume-mounted; everything else is baked into the image.

## Notifications (`config.py:197-200` + `NotificationCenterConfig`)

`NOTIFY_ENABLE_EMAIL_ALERTS=True`, `NOTIFY_ENABLE_SLACK_ALERTS=True` in
config.py (env cannot override — see precedence trap). SMTP/Slack endpoint
values come from env (`NOTIFY_SMTP_HOST/USER/PASSWORD`, `NOTIFY_FROM_EMAIL`,
`NOTIFY_TO_EMAIL`, `NOTIFY_SLACK_WEBHOOK_URL`); in production they exist only
as GitHub Actions secrets for the facts workflow — the app host does not send
alerts. Port is effectively pinned to `587` and TLS to on.

## Environment variables — the complete runtime story

| Variable | Needed by | Where it lives |
|---|---|---|
| `OPEN_ROUTER_API_KEY` | **All** LLM roles + embeddings (runtime) | Local `.env`; prod `/opt/hsg-rag/.env`; Actions secret |
| `WEAVIATE_API_KEY`, `WEAVIATE_CLUSTER_URL` | Retrieval (runtime) | Same three places |
| `OPENAI_API_KEY` | **Tests only** — hard-required by the UAT judge (`RUN_UAT_LLM_JUDGE`); the 31-case fact eval (`RUN_LLM_EVAL`) runs on `OPEN_ROUTER_API_KEY` + `WEAVIATE_*` (see `hsg-rag-validation-and-qa`) | Local `.env`; Actions secret |
| `LANGSMITH_TRACING/API_KEY/PROJECT/ENDPOINT` | Optional tracing | Optional |
| `RUN_LLM_EVAL=1` / `RUN_UAT_LLM_JUDGE=1` | Opt-in paid test suites (skipped otherwise) | Set ad hoc |
| `EMBEDDING_API_KEY` | Optional override; falls back to `OPEN_ROUTER_API_KEY` | Actions secret (scrape workflow) |
| `NOTIFY_*` | Facts-workflow alerts | Actions secrets (+ vars, partly no-op, see trap) |

GitHub Actions inventory (2026-07-07): secrets `DEPLOY_SSH_KEY` (deploy
workflow SSH), `OPENAI_API_KEY`, `OPEN_ROUTER_API_KEY` (alias
`OPENROUTER_API_KEY` also accepted by the facts workflow), `WEAVIATE_API_KEY`,
`WEAVIATE_CLUSTER_URL`, `EMBEDDING_API_KEY`, `LANGSMITH_API_KEY`,
`LANGSMITH_PROJECT`, `NOTIFY_SMTP_HOST/USER/PASSWORD`, `NOTIFY_FROM_EMAIL`,
`NOTIFY_TO_EMAIL`, `NOTIFY_SLACK_WEBHOOK_URL`; variables
`NOTIFY_ENABLE_EMAIL_ALERTS`, `NOTIFY_ENABLE_SLACK_ALERTS`,
`NOTIFY_SMTP_PORT`, `NOTIFY_SMTP_USE_TLS` (the last four are currently
shadowed by config.py / call-site defaults).

## How to add a new config axis (checklist)

1. Define the constant in `config.py` under the matching `====` section, with
   a comment stating type, allowed values, and default — match house style.
2. Wire it into the right subconfig class in `src/config/configs.py`
   (`ChainConfig`, `WeaviateConfig`, …) via `_get('NAME', <default>)`. Use
   `_get_bool` for booleans that might ever come from env.
3. Decide the env question explicitly: if operators must be able to override
   it without a deploy, do **not** define it in `config.py` — env only works
   for names absent there (see precedence trap).
4. Read it in code as `config.<subconfig>.<NAME>` — never `os.getenv` directly.
5. Add/extend an offline test if the value changes behavior
   (`tests/test_verified_facts.py` guards several config invariants).
6. Document it in `.env.example` if it is env-facing.
7. Route the change through change control (see hsg-rag-change-control):
   propose → OK → PR → merge deploys to production automatically.

## When NOT to use this skill

- Changing **what the bot says** (prompts, tone, word budgets in prompt text)
  → hsg-rag-change-control + the conversion campaign skill.
- Debugging a live failure → hsg-rag-debugging-playbook first.
- Setting up a machine from scratch / missing deps → hsg-rag-build-and-env.
- Deploy mechanics, host paths, Caddy → hsg-rag-run-and-operate.
- Why the architecture is shaped this way (why one agent, why facts injection)
  → hsg-rag-architecture-contract / hsg-rag-failure-archaeology.

## Provenance and maintenance

Sources: `config.py`, `src/config/configs.py`, `src/config/__init__.py`,
`.env.example`, `.github/workflows/*.yml`, usage sites verified by grep on
2026-07-07. Re-verify before relying on volatile values:

```bash
grep -n "MAIN_AGENT_MODEL\|FALLBACK_MODELS" config.py            # model ids
grep -n "TOP_K_RETRIEVAL\|MAX_HISTORY_MESSAGES\|MAX_RESPONSE_WORDS_LEAD" config.py
grep -n "ENABLE_EVALUATE_RESPONSE_QUALITY\|ENABLE_RESPONSE_CHUNKING" config.py  # must both be False
sed -n '8,23p' src/config/configs.py                             # precedence logic unchanged?
grep -n "TODO" src/config/configs.py                             # stale-block marker still there?
grep -h -o "secrets\.[A-Z_]*\|vars\.[A-Z_]*" .github/workflows/*.yml | sort -u
diff <(grep -o "^[A-Z_]*" .env.example) <(true)                  # eyeball env template drift
```

If `ENABLE_EVALUATE_RESPONSE_QUALITY` or `ENABLE_RESPONSE_CHUNKING` is ever
found `True`, or `FALLBACK_MODELS` grows beyond one entry, treat this skill as
stale and re-audit before advising.

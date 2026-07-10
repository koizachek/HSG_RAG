---
name: hsg-rag-run-and-operate
description: >
  Run, deploy, and operate the HSG_RAG chatbot. Load this skill when you need to:
  start the app locally (main.py flags), understand the production topology
  (Hetzner host, Docker container, Caddy), deploy a change (merge = deploy),
  trigger or observe a deployment, roll back a bad deploy, change the Caddyfile
  (TLS/CSP), check the scheduled GitHub Actions (nightly facts update, weekly
  scrape), or read/interpret the production logs. Triggers: "run the app",
  "deploy", "rollback", "production", "server", "container", "Caddy", "logs",
  "health check", "cron", "scheduled workflow", "start the bot".
---

# HSG_RAG — Run and Operate

Everything about **running the system and operating production**, as of 2026-07-07.

The system: a German/English RAG chatbot for University of St.Gallen executive
MBA programmes, live at `https://chatbot.emba.unisg.ch`, embedded as an iframe
on the EMBA website. Production is a single Hetzner host running one Docker
container behind a Caddy reverse proxy.

**When NOT to use this skill:**
- Setting up a dev environment from scratch, Python/venv traps → `hsg-rag-build-and-env`
- Something is broken and you're diagnosing → `hsg-rag-debugging-playbook`
- Measuring latency/quality instead of just reading logs → `hsg-rag-diagnostics-and-tooling`
- Deciding whether a change is safe to merge → `hsg-rag-change-control`
- Test suites and release gates → `hsg-rag-validation-and-qa`
- Architecture rationale (why single agent, why facts injection) → `hsg-rag-architecture-contract`

---

## 1. CLI anatomy (`main.py`)

Entry point for everything. Run with the repo venv: `venv/bin/python main.py <flags>`.
(Do NOT use the venv for pytest — it lacks pytest; see `hsg-rag-build-and-env`.)

| Flag | Values | What it does |
|---|---|---|
| `--app` | `en`, `de` | Starts the chat web app: FastAPI + mounted Gradio UI via uvicorn on port **7860**, `GET /health` endpoint included. Language sets the default UI language (users can switch in the UI). |
| *(no flags)* | — | Same as `--app` with default language **en** |
| `--scrape` | `simple`, `full` | Scrape + import pipeline. `full` ignores timestamps and re-scrapes all pages (slow, hits live websites); `simple` respects freshness timestamps |
| `--imports` | one or more file paths | Import local documents through the pipeline |
| `--weaviate` | `init`, `delete`, `redo`, `checkhealth`, `backup`, `restore` | Database actions. `redo` = delete + create + checkhealth. `restore` requires `--backup-id <id>` |
| `--dbapp` | — | Database management UI (separate Gradio app) |
| `--cli` | — | **Accepted but dead**: parsed, suppresses the default app start, but no code path handles it. Running `--cli` alone does nothing. |

Common operational commands:

```bash
venv/bin/python main.py --app de                 # what production runs
venv/bin/python main.py --weaviate checkhealth   # DB connectivity + both collections
venv/bin/python main.py --scrape full            # full re-scrape + import
curl -s http://localhost:7860/health             # {"timestamp":...,"status":"ok","weaviate":true}
```

`/health` performs a live Weaviate check — `"weaviate": false` with HTTP 200/500
means the app is up but retrieval is broken.

## 2. Production topology (verified 2026-07-07)

```text
Browser → https://chatbot.emba.unisg.ch
  └─ Caddy (host systemd service; TLS via Let's Encrypt, auto-renewed)
       config: deploy/Caddyfile → strips X-Frame-Options, sets
       CSP "frame-ancestors https://*.unisg.ch https://embax.ch https://*.embax.ch"
       └─ reverse_proxy localhost:7860
            └─ Docker container `hsg-rag` (published on 127.0.0.1:7860 ONLY)
                 image hsg-rag:latest, --restart unless-stopped
                 CMD: python main.py --app de
                 env:  --env-file /opt/hsg-rag/.env  (chmod 600; 3 runtime vars:
                       OPEN_ROUTER_API_KEY, WEAVIATE_API_KEY, WEAVIATE_CLUSTER_URL)
                 vol:  /opt/hsg-rag/logs → /app/logs  (logs + user profiles persist)
```

Host facts — all "verified 2026-07-07 (session)", re-verify on the host if load-bearing:
Hetzner CPX32 in Falkenstein (fsn1), Ubuntu 24.04, hostname `hsg-rag-prod-fsn1-1`,
IPv4 `178.105.196.130`, IPv6 `2a01:4f8:c014:9702::1`. App dir `/opt/hsg-rag` (rsync
target, not a git clone). Cloud firewall allows only 22/80/443. unattended-upgrades
and Hetzner backups (7-day rotation) active. A daily host cron deletes
`logs/user_profiles/` entries older than 30 days; logrotate compresses+deletes logs
after 30 days (GDPR — see `docs/datenschutz_deployment.md`). Maintainers reach the
host via the SSH alias `hsg-rag-prod` (root@178.105.196.130) — that alias lives in
the maintainer's `~/.ssh/config`, not in the repo.

## 3. Deploying a change

**Normal path: merge a PR into `main`. That is the deploy.** No manual steps.

`.github/workflows/deploy.yml` ("Deploy to Production") runs on:

1. **Push to `main`** — except doc-only changes (`**.md`, `docs/**`, `uat-results/**`)
2. **After every successful "Update Programme Facts" run** (`workflow_run` trigger).
   Reason: the facts action commits with the default `GITHUB_TOKEN`, and such
   pushes do NOT fire push-triggered workflows — without this trigger, updated
   prices/deadlines would never reach production (facts are baked into the image).
3. **Manual dispatch**: `gh workflow run deploy.yml`

Pipeline steps (single `deploy` job, 20 min timeout, `production-deploy`
concurrency group so deploys never overlap): checkout → SSH setup (key from
secret `DEPLOY_SSH_KEY`, host key pinned in the workflow file) → `rsync -az
--delete` to `/opt/hsg-rag` (excludes protect `.env`, `logs/`, `.git`, `venv`)
→ on host: tag current image as `hsg-rag:previous`, `docker build`, `docker rm
-f`, `docker run` → health poll on `127.0.0.1:7860/health` (up to 240 s; the
app can need ~60–90 s to come up) → verify `https://chatbot.emba.unisg.ch/health`.

Observe deployments:

```bash
gh run list --workflow=deploy.yml --limit 5
gh run watch <run-id> --exit-status
gh run view <run-id> --log | grep -E "Health OK|Public health"
```

With a warm Docker layer cache a code-only deploy completes in ~30 s; a
requirements change forces a pip-layer rebuild (several minutes).

## 4. Rollback

The previous image survives every deploy as `hsg-rag:previous`. All commands run
**on the host** (session knowledge; the same recipe is printed by the failed
health-check step):

```bash
docker tag hsg-rag:previous hsg-rag:latest
docker rm -f hsg-rag
docker run -d --name hsg-rag \
  --restart unless-stopped \
  -p 127.0.0.1:7860:7860 \
  --env-file /opt/hsg-rag/.env \
  -v /opt/hsg-rag/logs:/app/logs \
  hsg-rag:latest
curl -sf http://127.0.0.1:7860/health   # wait/repeat up to ~2 min
```

Caveats: only ONE generation back is kept — a second bad deploy overwrites
`previous` with the first bad image. Rolling back the image does not roll back
`/opt/hsg-rag` code on disk (harmless until the next build) and does not touch
`.env` or Caddy. After rolling back, fix forward via a PR; do not leave prod on
`previous` silently.

## 5. Changing the Caddyfile (TLS / CSP / iframe domains)

Caddy is NOT part of the container or the deploy pipeline. Procedure:

0. **Gate:** Caddy config changes require maintainer OK per the
   `hsg-rag-change-control` class table BEFORE editing; apply on the host only
   after the PR is merged.
1. Edit `deploy/Caddyfile` in the repo and land it via PR (keeps repo = truth).
2. Copy it to the host and reload — zero-downtime (host-side, session knowledge):
   ```bash
   scp deploy/Caddyfile hsg-rag-prod:/etc/caddy/Caddyfile   # path: verify on host
   ssh hsg-rag-prod 'systemctl reload caddy'
   ```
3. Verify: `curl -sSI https://chatbot.emba.unisg.ch/ | grep -i content-security-policy`

Typical reason: adding an allowed embedding domain to `frame-ancestors`. An
iframe on a domain not listed there is silently blocked by browsers.

### 5a. Pilot-phase IP allowlist (activation and removal)

`deploy/Caddyfile` contains a commented-out `@blocked` matcher block that
restricts the bot to an IP allowlist during the pilot phase (added July 2026,
inactive by default). It blocks everything **except `/health`** — that path
must stay public because `deploy.yml` verifies
`https://chatbot.emba.unisg.ch/health` from GitHub runners; blocking it fails
every subsequent deploy.

**Activate for the pilot:**

1. In `deploy/Caddyfile`, uncomment the `@blocked { ... }` and
   `respond @blocked ... 403` lines and replace the `<IP-OR-CIDR>` placeholders
   with the allowed addresses, space-separated (IPv4 and/or IPv6, single IPs or
   CIDR ranges — include the IPv6 ranges, campus users may connect over IPv6).
2. Land via PR + host apply per the §5 procedure above.
3. Verify: from an allowlisted IP `curl -s -o /dev/null -w "%{http_code}"
   https://chatbot.emba.unisg.ch/` → `200`; from any other network (e.g. mobile
   hotspot) → `403`; `/health` → `200` from everywhere.

**Remove after go-live (bot public for everyone):**

1. Delete the entire block between the `--- PILOT PHASE ...` and
   `--- END PILOT PHASE ...` marker comments in `deploy/Caddyfile` (matcher,
   `respond`, and all comment lines). Nothing else references it — no app code,
   env var, or workflow needs touching.
2. Land via PR + host apply per §5 (maintainer OK gate applies as always).
3. Verify from a non-allowlisted network (e.g. mobile hotspot):
   `curl -s -o /dev/null -w "%{http_code}" https://chatbot.emba.unisg.ch/` →
   `200` (was `403` during the pilot), and the chat UI loads in a browser.
4. If the `403` persists, the host is still running the old config — re-run the
   `scp` + `systemctl reload caddy` step and check `systemctl status caddy` for
   a config parse error (a malformed Caddyfile makes `reload` keep the old one).

## 6. Scheduled operations (GitHub Actions — no host cron for these)

| Workflow | Schedule | Purpose |
|---|---|---|
| `update_programme_facts.yml` ("Update Programme Facts") | daily **06:23 UTC** | Scrapes official sources, regenerates `data/database/programme_facts.json`, commits on material change, alerts via email + Slack (`NOTIFY_*` secrets), then triggers a production deploy via `workflow_run` |
| `scrape.yml` | weekly **Sun 05:17 UTC** | Refreshes scraped website content into Weaviate |
| `deploy.yml` | event-driven (see §3) | Production deployment |

```bash
gh run list --workflow=update_programme_facts.yml --limit 7   # weekly sanity check
gh run list --workflow=scrape.yml --limit 3
gh workflow run update_programme_facts.yml                    # manual facts run
```

Never hand-edit `programme_facts.json` — the nightly run overwrites it and a
materially wrong value pages the team. (Exception — the deliberate alert-chain
test — is documented in `hsg-rag-change-control`, "The sanctioned exception".)

## 7. Log anatomy

App logs land in `logs/logs.log` (in prod: `/opt/hsg-rag/logs/logs.log` via the
volume). Line shape:

```text
(2026.07.07 09:01:19) agent_chain	 INFO: [timing] preprocessing: 0.62s
```

Logger names are truncated to 17 chars. Key lines to grep for:

| Pattern | Meaning |
|---|---|
| `[timing] preprocessing` / `agent loop` / `total turn` | Per-turn latency breakdown (`src/rag/agent_chain.py`). Healthy bands: see `hsg-rag-debugging-playbook` § Healthy baselines (single home for these numbers) |
| `empty response` / `falling back to blocking` | **Red flag**: streaming path failed; users see nothing until the full answer. Was a real bug (fixed 2026-07-07); if it reappears → `hsg-rag-debugging-playbook` |
| `Appointment Requested:` / `Show Booking Widget:` | Structured-response flags per turn — the raw signal for booking/conversion analysis |
| `Querying retrieved N objects in X seconds` | Weaviate retrieval (healthy band: `hsg-rag-debugging-playbook` § Healthy baselines) |
| `is calling tool: retrieve_context` | The turn used retrieval (vs. answered from injected facts) |

GDPR: user input is redacted in `agent_chain.py` logs (`<redacted user input, N
chars>`), **but** `src/apps/chat/app.py:285` still logs the first 100 chars of
each query (`Processing user query: ...`). Treat log excerpts as personal data.
Retention: 30 days (host logrotate).

## Provenance and maintenance

Written 2026-07-07 against commit `d76d050` (main). Everything repo-side was
verified by reading the files; host-side facts are marked "(session)".

Re-verification one-liners for facts that drift:

```bash
venv/bin/python main.py --help                                  # CLI flags
grep -n "cron" .github/workflows/*.yml                          # schedules
grep -n "frame-ancestors" deploy/Caddyfile                      # CSP domains
sed -n '1,50p' .github/workflows/deploy.yml                     # deploy triggers
grep -n "CMD\|EXPOSE\|HEALTHCHECK" Dockerfile                   # container contract
curl -s https://chatbot.emba.unisg.ch/health                    # prod alive
ssh hsg-rag-prod 'docker inspect hsg-rag --format "{{.Config.Image}} {{.HostConfig.PortBindings}}"'  # host truth
```

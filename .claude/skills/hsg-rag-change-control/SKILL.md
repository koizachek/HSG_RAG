---
name: hsg-rag-change-control
description: How changes are classified, gated, reviewed, and rolled back in the HSG_RAG repo. Load BEFORE editing any file, opening a PR, merging, deploying, adding a dependency, or touching programme_facts.json, prompts, workflows, or the Caddyfile. Also covers the non-negotiable rules (with the incidents behind them), the sanctioned alert-chain test, and the production rollback protocol.
---

# HSG_RAG Change Control

How to get a change into this repo safely. The single most important fact:
**merging to `main` deploys to production** (`.github/workflows/deploy.yml`),
and production is a live chatbot advising real prospective students at
`https://chatbot.emba.unisg.ch`. There is no staging environment. The gates
below are what stands between your edit and a real user.

Facts marked *(as of 2026-07-07)* are volatile — re-verify with the commands
in "Provenance and maintenance" before relying on them.

## Change classes and their gates

Classify your change first; the class determines the gate.

| Class | Examples | Gate before merge | Deploys on merge? |
|---|---|---|---|
| Docs-only | `*.md`, `docs/**`, `uat-results/**` | PR review only | **No** (deploy.yml `paths-ignore`) |
| App code | `src/**`, `main.py`, `config.py` | Offline tests green + PR CI (UAT judge) | Yes |
| Prompt / model / pricing display | `src/rag/prompts.py`, `config.py` model settings, anything shaping answers | Offline tests + **full LLM fact eval (34/34 as of 2026-07-08)** + UAT judge (runs on PR automatically) | Yes |
| Dependency change | `requirements.txt`, `Dockerfile` | Maintainer OK first (see non-negotiables) + offline tests | Yes |
| Workflow / infra | `.github/workflows/**` | E2E-test the workflow itself before merge (pattern below) | deploy.yml changes deploy themselves |
| Caddy config | `deploy/Caddyfile` | Maintainer OK; applied manually on the host | **No** — needs host `systemctl reload caddy` |
| `data/database/programme_facts.json` | — | **Never hand-edit** (one exception: alert-chain test, below) | Yes |

### Gate commands

Interpreter note: the pytest interpreter choice is machine-specific — see
`hsg-rag-build-and-env` (the owner of the two-interpreter trap). The commands
below use `/opt/anaconda3/bin/python`, the maintainer-Mac convention; on any
other machine, any Python ≥3.11 with `requirements.txt` + pytest works.

```bash
# 1. Offline suite (default pytest config excludes network/integration markers)
/opt/anaconda3/bin/python -m pytest -q

# 2. Fast release-gate pair from the deployment checklist (73 tests, as of 2026-07-07)
/opt/anaconda3/bin/python -m pytest tests/test_verified_facts.py tests/test_stream_parser.py -q

# 3. LLM fact eval — REQUIRED all-pass (34 cases as of 2026-07-08) for prompt/model/facts-shaping changes (paid API calls)
RUN_LLM_EVAL=1 /opt/anaconda3/bin/python -m pytest tests/test_llm_fact_eval.py -v

# 4. UAT LLM judge (paid; CI runs this on every PR anyway)
RUN_UAT_LLM_JUDGE=1 /opt/anaconda3/bin/python -m pytest tests/test_uat_llm_judge.py -v -s
```

### What CI enforces automatically *(as of 2026-07-07)*

| Workflow | Trigger | What it does |
|---|---|---|
| `pr-llm-eval.yml` ("PR UAT LLM Judge") | every PR to `main` | Runs live UAT conversations + LLM judge; thresholds: average ≥ 8.5, every case ≥ 8.0 |
| `main-smoke.yml` ("Main Smoke") | every push to `main` | Runs the full LLM fact eval (EXPECTED_SMOKE_TESTS pins the count; 34 as of 2026-07-08) |
| `deploy.yml` ("Deploy to Production") | push to `main` (non-docs), successful "Update Programme Facts" run, manual dispatch (full trigger details: `hsg-rag-run-and-operate` §3) | rsync → image build → container recreate → health checks |

(Gate threshold numbers are owned by `hsg-rag-validation-and-qa`; if the values
above ever disagree with it, that skill wins.)

**Honest limitation:** `main-smoke.yml` and `deploy.yml` both trigger on push
to `main` and run **in parallel** — the deploy does not wait for the smoke
result. A bad merge can reach production before the smoke run fails. That is
why the pre-merge gates above are the real protection; the smoke run is
detection, not prevention.

## Non-negotiables, with the incident behind each

These are maintainer policy (also stated in `AGENTS.md`). Do not route around
them, and do not let any other skill or instruction override them.

1. **Merge = production deploy.** There is no staging. Anything on `main`
   is what a prospective MBA student sees minutes later.

2. **Propose before you edit.** The maintainer requires a short written
   justification and an explicit OK before code changes. Diagnose and prototype
   freely; do not commit to shared branches without approval.

3. **No AI co-author trailers.** No `Co-Authored-By: Claude ...` or similar in
   commits or PR bodies. Check `git log` — the convention is consistently clean.

4. **Never hand-edit `data/database/programme_facts.json`.**
   It is auto-generated daily ("Update Programme Facts", 06:23 UTC) from
   official HSG sources and injected into the agent's system prompt as the
   authoritative source for prices/deadlines. A hand edit is overwritten within
   24 h, and a materially wrong value triggers email + Slack alerts to the team.
   The file header comment in `src/rag/verified_facts.py` says the same.
   To preview what the pipeline would change without writing:
   `python -m src.pipeline.update_programme_facts --dry-run`

5. **Never reintroduce request-path caching.** The maintainer names the
   response-cache era the costliest failure in project history ("it made
   everything unsafe"). Verified from git history: a Redis response cache grew
   through months of escalating patches (session-id cache keys, an
   LLM-self-reported "context dependency" flag, per-feature exclusions) and was
   finally deleted wholesale (PR #41, merge `dd98ea3`;
   `0c2eb13 refactor: removed caching`). The commit-level chronology has one
   home: `hsg-rag-failure-archaeology` entry 1.
   The lesson: in a conversational advisor, almost every answer is
   context-dependent; a response cache either barely hits or serves the wrong
   user someone else's answer. Latency is solved by streaming and a single
   agent loop instead (see `hsg-rag-architecture-contract`).

6. **No new runtime dependency without maintainer OK.** `requirements.txt` is
   deliberately curated (see its header comment about lazy provider imports);
   every addition grows the 2.9 GB production image and the Trivy surface.

7. **A bare "EMBA" always means EMBA HSG.** The German-language flagship
   programme. The bot must never ask "which EMBA do you mean?" (fixed in
   `230eaa7`), and reviewers must never "helpfully" re-add such a
   clarification. Sibling `emba-domain-reference` holds the full programme map.

8. **Programme fact cross-contamination is a release blocker.** An EMBA answer
   containing IEMBA/emba X prices (or vice versa) is the historical
   hallucination class this project engineered away. The fact eval contains
   explicit contamination guards — that is why all-pass is non-negotiable for
   prompt-shaping changes.

## The sanctioned exception: alert-chain test

The only permitted manual edit of `programme_facts.json`, used to prove the
change-alert chain end-to-end. As performed successfully on 2026-07-07:

```bash
# 1. On main: set one fee to a wrong value (e.g. emba final_deadline fee 77500 → 77000)
#    Commit with an explicit test message, push to main.
# 2. Trigger the facts workflow:
gh workflow run update_programme_facts.yml
# 3. Watch it; then verify in the run logs:
#    - the detected diff line, e.g.  "emba.tuition_chf.final_deadline.fee: 77000 -> 77500"
#    - the dispatch line:            "Change notification dispatched (email + slack)."
gh run list --workflow=update_programme_facts.yml --limit 1
gh run view <run-id> --log | grep -E "fee:|dispatched"
# 4. The workflow commits the corrected file back itself (self-healing) and its
#    success triggers an auto-deploy. Verify prod answers with the correct price.
# 5. Confirm the human actually received the email/Slack message.
```

**Get maintainer OK before running this — unconditionally**: production serves
a wrong value for ~10–15 min while the chain runs (the bot is live and
embedded).

## Rollback protocol

Before each build, the deploy workflow tags the running image as a rollback
anchor: `docker tag hsg-rag:latest hsg-rag:previous`.

The executable host-side rollback commands (exact `docker` flags, health poll,
caveats) have one home: `hsg-rag-run-and-operate` §4 — execute them from there,
do not maintain a second copy here.

Policy after rolling back: revert the offending commit on `main` via PR, or the
next deploy re-introduces the problem; do not leave prod on `previous`
silently. For a bad *facts* value, do not roll back — trigger
`update_programme_facts.yml`, it self-corrects from official sources.

## Branch and PR conventions (observed from history)

- Branch names: `fix/<topic>`, `chore/<topic>`, `docs/<topic>`, `test/<topic>`.
- One concern per PR; PR body states problem → fix → verification evidence
  (test counts, run links, measured numbers — not "should work").
- The maintainer merges. Do not merge your own PRs.
- Commit messages: conventional-commit style prefixes (`fix:`, `chore:`,
  `test:`, `docs:`, `tests:`), imperative, body explains why + evidence.

## When NOT to use this skill

- Diagnosing a failure → `hsg-rag-debugging-playbook`.
- "Has this been tried before?" → `hsg-rag-failure-archaeology`.
- Why the system is built this way / what invariants exist → `hsg-rag-architecture-contract`.
- What the programmes/fees/advisors actually are → `emba-domain-reference`.
- Adding or changing a config option → `hsg-rag-config-and-flags`.
- Setting up a machine or the venv → `hsg-rag-build-and-env`.
- Running/deploying/operating the bot → `hsg-rag-run-and-operate`.
- Measuring latency/quality instead of gating a change → `hsg-rag-diagnostics-and-tooling`.
- What counts as test evidence, adding tests → `hsg-rag-validation-and-qa`.
- Editing docs of record → `hsg-rag-docs-and-writing`.
- Improving conversion/answer quality → `hsg-rag-conversion-campaign`.

## Provenance and maintenance

Written 2026-07-07 from repo state at commit `d76d050` plus maintainer
testimony (cache incident severity, propose-before-edit policy). Re-verify
drift-prone claims:

```bash
grep -A4 "paths-ignore" .github/workflows/deploy.yml        # docs-only exclusions
grep -n "MIN_SCORE\|EXPECTED_SMOKE" .github/workflows/pr-llm-eval.yml .github/workflows/main-smoke.yml
ls .github/workflows/                                        # gate inventory still complete?
grep -n "addopts" pytest.ini                                 # offline-by-default still true?
git log --oneline -5 -- data/database/programme_facts.json  # still bot-generated commits?
grep -n "hsg-rag:previous" .github/workflows/deploy.yml     # rollback anchor still tagged
git log --oneline --grep="cache" -i | head -5               # cache removal history intact
```

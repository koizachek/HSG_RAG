---
name: hsg-rag-docs-and-writing
description: How to maintain HSG_RAG's documents of record and match its house style. Load when writing or updating README.md, DEPLOYMENT_CHECKLIST.md, AGENTS.md, anything under docs/, a post-mortem/audit, a commit message, a PR body, or a new skill in .claude/skills/ — or when unsure which document a new fact belongs in, which language to write in, or how to check off a checklist item correctly.
---

# HSG_RAG Docs and Writing

How this project documents itself: which document owns which fact, the house
style for commits/PRs/checklists, and copy-paste templates. Facts here are
current as of **2026-07-07**.

## When NOT to use this skill

- Deciding whether a change is allowed or how it must be gated → `hsg-rag-change-control`
- Recording the *technical content* of a resolved failure → `hsg-rag-failure-archaeology` (this skill only gives you its entry format)
- Running or deploying anything → `hsg-rag-run-and-operate`
- What counts as evidence for a claim → `hsg-rag-validation-and-qa`
- External-facing messaging to stakeholders (IT, web team, DPO) → `hsg-rag-stakeholder-comms`

## Document inventory — one home per fact

| Document | Language | Purpose / owns |
|---|---|---|
| `README.md` | English | Public-facing overview: what the repo contains, setup, commands, **Production Deployment** section (live URL, auto-deploy behaviour). |
| `DEPLOYMENT_CHECKLIST.md` | German | **The living go-live status document.** Owns deployment state, open blockers, Go/No-Go criteria. Supersedes `docs/deploy_readiness_checklist.md`. |
| `AGENTS.md` | English | Agent onboarding: non-negotiables, environment traps, ops quick reference. Must stay in sync with actual rules. |
| `AUDIT_LATENCY_HALLUCINATIONS.md` | German | Post-mortem of the June 2026 overhaul. Its *before → after* metric table is the house standard for any future audit. |
| `docs/configuration_system_documentation.md` | — | Configuration surface reference. |
| `docs/datenschutz_deployment.md` | German | GDPR/data-protection decisions and retention rules. |
| `docs/user_profile_tracking.md` | — | User-profile mechanism. |
| `docs/weaviate_database_setup.md` | — | Weaviate cluster/collection setup. |
| `docs/chatbot_overhaul_plan.md` | English | Historical: the ten UX defects behind the June overhaul (believed fixed; do not re-litigate without new evidence). |
| `docs/deploy_readiness_checklist.md` | German | **Superseded** (2026-04-10 state). Do not update; do not cite as current. |
| `.claude/skills/` | English | This library. One skill = one directory with `SKILL.md`. |

Rule: **one home per fact.** Other documents cross-reference; they do not
duplicate. If a fact has no home, the checklist (deployment state) or a new
`docs/` file (everything else) gets it — not the README.

## Language policy

- Code, comments, commit messages, PR titles, AGENTS.md, skills: **English**.
- Maintainer-facing status docs (checklist, GDPR docs, post-mortems): **German** is established; keep each document's existing language.
- PR bodies: either language; existing PRs use German bodies with English titles.

## House style

### Commit messages

English, imperative, `type: subject` prefix (`fix:`, `chore:`, `docs:`, `test:`,
`tests:` all occur; prefer `fix|chore|docs|test`). Body explains the **mechanism**
and ends with **verification numbers**, not just intent. Real example (`334da90`):

```
fix: treat streamed tool-call responses as valid in model retry check

Under streaming, LangChain chunk aggregation concatenates finish_reason
across chunks ('tool_callstool_calls'), so the exact-match check
misclassified every tool-call response as empty. [...]

Check result.tool_calls directly instead of the fragile finish_reason
string. Verified live: first token 3.7s, total 6.7s (was 14.2s), no
retries, no blocking fallback.
```

**Never add `Co-Authored-By: Claude ...` or similar AI-attribution trailers to
commits or PRs** (AGENTS.md non-negotiable #3).

### PR bodies

Structure used in this repo (see PR #67, #68): `## Problem` (with real log
excerpts/evidence) → `## Fix` (mechanism) → `## Verifikation`/`## Verification`
(concrete numbers, links to real workflow runs). A PR that changes behaviour
without a verification section is out of style — and out of change control.

### DEPLOYMENT_CHECKLIST.md conventions

- Header line `**Stand:** YYYY-MM-DD (what changed; ursprünglich ...)` — update it with every substantive edit.
- Checking off an item **requires date + evidence inline**, e.g.:
  `- [x] Vor Release: RUN_LLM_EVAL=1 pytest ... → **31/31** (2026-07-07, 160 s)`
- Items that become obsolete are **not deleted**: strikethrough + reason, e.g.
  `- [x] ~~HUGGING_FACE_API_KEY erneuern~~ — **entfällt** (2026-07-06): ...`
- Corrections keep history; never silently rewrite a checked entry.

### Audits / post-mortems

Follow `AUDIT_LATENCY_HALLUCINATIONS.md`: lead with a *Vorher → Nachher* metric
table, then Diagnose → Maßnahmen (checkboxed) → Ist-Architektur. Claims carry
measured numbers ("31/31", "~6 s"), not adjectives.

## Templates

Checklist check-off line:

```markdown
- [x] <item text> (<YYYY-MM-DD>: <measured evidence, run link or numbers>)
```

Failure-archaeology entry (format contract with `hsg-rag-failure-archaeology`):

```markdown
### <short name> (<YYYY-MM-DD resolved|open>)
- **Symptom:** <what was observed, verbatim log lines if possible>
- **Root cause:** <mechanism, one paragraph>
- **Evidence:** <commits, run IDs, measurements that pin the cause>
- **Status:** resolved in <PR/commit> | open | wont-fix because <reason>
```

PR body skeleton:

```markdown
## Problem
<evidence: logs, numbers, user-visible effect>

## Fix
<mechanism of the change, why this and not the alternative>

## Verification
<commands run, numbers before/after, links to workflow runs>
```

Skill provenance section (every skill in this library ends with one):

```markdown
## Provenance and maintenance

Facts verified <YYYY-MM-DD> against <source>. Re-verify:
- <claim>: `<one-line command>`
```

## Sync obligations

| When this happens | Also update |
|---|---|
| A working rule changes (gating, style, non-negotiable) | `AGENTS.md` + `hsg-rag-change-control` skill |
| A failure is investigated/resolved | `hsg-rag-failure-archaeology` + checklist entry if deploy-relevant |
| Deployment state changes (new infra, new workflow, item done) | `DEPLOYMENT_CHECKLIST.md` header + item, README Production section if user-visible |
| A volatile number is written anywhere (latency, counts, versions) | date-stamp it in place |
| A doc is superseded | mark it superseded at the top and link the successor; do not delete |

## Provenance and maintenance

Facts verified 2026-07-07 against the repo at commit `d76d050`. Re-verify:

- Document inventory: `ls docs/ *.md .claude/skills/`
- Commit style examples: `git log --format='%h %s' -15` and `git show -s --format=%B 334da90`
- Checklist conventions: `head -5 DEPLOYMENT_CHECKLIST.md && grep -n '~~' DEPLOYMENT_CHECKLIST.md`
- PR body structure: `gh pr view 67 --json body -q .body | head -30`
- No-AI-trailer rule: `grep -n 'Co-Authored' AGENTS.md`

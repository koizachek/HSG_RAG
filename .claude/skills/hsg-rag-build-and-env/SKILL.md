---
name: hsg-rag-build-and-env
description: Recreate the HSG_RAG development environment from scratch and avoid its known traps. Load when setting up a fresh clone, creating a venv, installing dependencies, configuring .env, building the Docker image, hitting "No module named pytest", a python-dotenv AssertionError, torch/CUDA download surprises, or any "works in prod but not locally" environment mismatch. NOT for running/deploying the app (hsg-rag-run-and-operate) or test strategy (hsg-rag-validation-and-qa).
---

# HSG_RAG — Build and Environment

How to stand up a working environment for this repo, and the traps that have
already cost sessions real time. All facts verified against the repo as of
**2026-07-07**.

## The two-interpreter trap (read this first)

Two Python interpreters are in play on the maintainer's machine. Using the
wrong one is the single most common environment failure:

| Purpose | Interpreter | Why |
|---|---|---|
| Run the app, scripts, CLI commands | `venv/bin/python` (repo venv, Python 3.13.9) | Has all runtime deps from `requirements.txt` |
| Run pytest | `/opt/anaconda3/bin/python -m pytest` (pytest 8.4.2) | **The repo venv has no pytest installed** — `venv/bin/python -m pytest` fails with `No module named pytest` |

The anaconda path is a **machine convention on the maintainer's Mac**, not a
repo requirement. Generic fix on any other machine: install pytest into any
interpreter that also has the repo dependencies (`pip install pytest` inside
the venv works too — it just isn't how this machine is set up).

Also: in agent sessions, **shell state does not persist between tool calls**.
`source venv/bin/activate` only lasts for that one call. Always invoke
`venv/bin/python ...` by path instead of relying on activation.

## Local setup from scratch

```bash
git clone https://github.com/koizachek/HSG_RAG.git
cd HSG_RAG
python -m venv venv                      # any Python ≥3.11; repo venv is 3.13
venv/bin/pip install -r requirements.txt
cp .env.example .env                     # then fill in real values
```

Notes:

- `requirements.txt` does **not** list `torch`, but `docling` pulls it in
  transitively (venv currently has torch 2.11.0). On Linux this can download
  multi-GB CUDA wheels; if you only need CPU, pre-install the CPU wheel first
  the way the Dockerfile does:
  `pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu`
- Local venvs drift from `requirements.txt` over time (observed 2026-07-07:
  venv had gradio 6.14.0 while requirements pins `gradio==6.15.0`). After
  pulling changes to `requirements.txt`, re-run
  `venv/bin/pip install -r requirements.txt`.

## .env — which variables for which mode

Template: `.env.example` (authoritative, commented). Summary:

| Variable | Needed for |
|---|---|
| `OPEN_ROUTER_API_KEY` | **Runtime, always.** ALL LLM roles AND embeddings go through OpenRouter |
| `WEAVIATE_API_KEY`, `WEAVIATE_CLUSTER_URL` | **Runtime, always.** EU cloud cluster |
| `OPENAI_API_KEY` | Opt-in LLM test suites only (`RUN_LLM_EVAL`, `RUN_UAT_LLM_JUDGE`). Never used by the runtime agent |
| `LANGSMITH_*` | Optional tracing |
| `NOTIFY_*` (SMTP/Slack) | Only if this machine itself must send fact-change alerts; in production these live as GitHub Actions secrets |
| `WEAVIATE_BACKUP_PATH` | Only for the manual backup backend |

Never commit `.env`; never print its values. Production's `.env` lives on the
host at `/opt/hsg-rag/.env` (chmod 600) and contains only the runtime trio.

## Docker image

`Dockerfile` anatomy (two-stage build):

1. **Builder stage** — `python:3.11.14-slim-bookworm`; installs CPU-only torch
   first (avoids CUDA wheels), then `requirements.txt`.
2. **Final stage** — same base; copies site-packages from builder; apt-installs
   `libmagic1 poppler-utils curl`; copies the repo; `EXPOSE 7860`;
   `HEALTHCHECK` curls `http://localhost:7860/health` every 60 s;
   `CMD ["python", "main.py", "--app", "de"]`.

Note the **version skew**: the image runs Python **3.11.14**, local venv is
**3.13.x**. Code must work on both; don't use 3.12+-only syntax.

```bash
docker build -t hsg-rag .                # normal build (layer-cached)
docker build --no-cache -t hsg-rag .     # full rebuild (README-recommended for releases)
docker run --env-file .env -p 7860:7860 --name hsg-rag hsg-rag
```

### Layer-cache semantics (matters for security patches)

- Code-only changes rebuild in **seconds**: `COPY . .` is the last layer, so
  pip/apt layers stay cached.
- `docker build` **never refreshes the base image** unless you pass `--pull`.
  As of 2026-07-07, `.github/workflows/deploy.yml` (line ~71) builds
  **without** `--pull`, so new Debian security patches in
  `python:3.11.14-slim-bookworm` do NOT arrive automatically on the production
  host — this is a known open item; the `--pull` fix was proposed but not yet
  approved. Do not silently add it; route through hsg-rag-change-control.

## Known traps (each with its mechanism)

| Trap | Mechanism | Fix |
|---|---|---|
| `python-dotenv` raises `AssertionError` in `find_dotenv` | `load_dotenv()` with no args walks the call stack to find the caller's file; when code runs from stdin/heredoc there is no file frame | Pass the path explicitly: `load_dotenv("/abs/path/to/.env")` |
| Loosening the gradio pin | `gradio==6.15.0` is a security pin (cookie-injection CVE-2026-48545 fixed in 6.15.0) | Never downgrade; treat bumps as change-controlled |
| Docling prints "You are sending unauthenticated requests to the HF Hub" | Docling downloads its layout models anonymously | Benign; no HF token needed anywhere in this project. If docling returns near-empty PDF text, `extract_pdf_text` in `src/pipeline/update_programme_facts.py` falls back to pypdf automatically |
| `source venv/bin/activate` "doesn't work" in agent sessions | Shell state is per-tool-call | Use `venv/bin/python` by absolute/relative path |
| `pytest` not found | Repo venv ships without pytest | Use the anaconda interpreter (this machine) or install pytest into the venv |

## Verify a fresh environment works

```bash
/opt/anaconda3/bin/python -m pytest -q          # offline suite; needs no keys, no network
```

Expected for the full offline suite (baseline as of 2026-07-07, owned by
`hsg-rag-validation-and-qa`): **286 passed, 1 skipped, 12 deselected** — the
12 deselected are `network`/`integration`-marked tests excluded per
`pytest.ini` (`addopts = -m "not network and not integration"`). The figure
**73 passed** applies only to the two-file release-gate pair:

```bash
/opt/anaconda3/bin/python -m pytest -q tests/test_verified_facts.py tests/test_stream_parser.py   # 73 passed
```

With runtime keys in `.env`, a deeper check:

```bash
venv/bin/python main.py --weaviate checkhealth   # expects: Connection ✓ OK, both collections ✓ OK
```

## When NOT to use this skill

- Starting/operating the app or deploying → **hsg-rag-run-and-operate**
- What to test before a change ships → **hsg-rag-validation-and-qa**
- Config options and flags catalog → **hsg-rag-config-and-flags**
- Why the architecture looks like this → **hsg-rag-architecture-contract**
- A command fails for non-environment reasons → **hsg-rag-debugging-playbook**

## Provenance and maintenance

Facts verified 2026-07-07 against the working tree. Re-verify before trusting:

- Python versions: `venv/bin/python --version` (3.13.9) · `grep FROM Dockerfile` (3.11.14-slim-bookworm)
- venv lacks pytest: `venv/bin/python -m pytest --version` (expect "No module named pytest")
- Anaconda pytest: `/opt/anaconda3/bin/python -m pytest --version` (8.4.2)
- deploy build lacks `--pull`: `grep -n "docker build" .github/workflows/deploy.yml`
- gradio pin: `grep gradio requirements.txt` (==6.15.0)
- Env variable set: `cat .env.example`
- pypdf fallback: `grep -n pypdf src/pipeline/update_programme_facts.py`
- Release-gate pair count: `/opt/anaconda3/bin/python -m pytest -q tests/test_verified_facts.py tests/test_stream_parser.py` (73 passed as of 2026-07-07; full offline suite = 286 passed, 1 skipped, 12 deselected — see hsg-rag-validation-and-qa)

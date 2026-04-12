# Deploy Readiness Checklist 10.04. 16:00 

This checklist reflects the GitHub `main` state at commit `c0462c1b7c5074af682ecb1dc1f3d8e8a958dfb8`.

## Current Readiness

- `main` is not fully deploy-ready yet.
- The current chat app and reverse-proxy direction are in place.
- The deployment path is still blocked by the pipeline and Weaviate setup regressions introduced before the current `main` head.

## Blocking Issues Before Deployment

- Merge the ER-155 fix branch that restores pipeline compatibility:
  - `fix/er-155-pipeline-and-weaviate`
- Fix the broken import pipeline contract in `src/pipeline/pipeline.py`:
  - `_webprocessor` is referenced but not initialized
  - `scrape_website()` is missing
  - `import_many_documents()` is missing
- Resolve the Weaviate collection initialization dependency in `src/database/weavservice.py`:
  - `properties.yaml` is required on current `main`
  - `data/database/properties.yaml` is not present on GitHub `main`
  - `PyYAML` is not present in `requirements.txt` on GitHub `main`
- Bring the Docker base-image update to `main` before building production images:
  - move from `python:3.11-slim`
  - to an explicit current tag such as `python:3.11.14-slim-bookworm`

## Repo Changes To Land Before Deploy

- Merge `fix/er-155-pipeline-and-weaviate`
- Commit and merge the Dockerfile base-image update
- Decide one of these two paths for Weaviate properties:
  - version `data/database/properties.yaml`
  - or keep the defensive fallback logic from the fix branch
- Ensure `requirements.txt` matches the actual runtime contract

## Infrastructure Readiness

- DNS for `bot.hsg.ch` points to the target server
- Caddy is installed and configured with `deploy/Caddyfile`
- Port `7860` is reachable internally on the host
- Weaviate is available:
  - local or cloud
- Redis is available:
  - local or cloud
- Outbound network access exists for required model downloads, or models are pre-cached

## Environment Variables And Secrets

- LLM provider keys are configured
- Weaviate credentials and endpoints are configured
- Redis credentials and mode are configured
- Optional LangSmith keys are configured if tracing is desired
- Production `.env` values are verified against `src/config/configs.py`

## Build Checklist

- Build the application image from the final merged `main`
- Re-run image vulnerability scanning against the new digest
- Confirm the image includes all Python dependencies
- Confirm runtime filesystem paths are writable where needed:
  - logs
  - data
  - backups

## Runtime Validation

- Run `python main.py --weaviate checkhealth`
- If first deployment, run `python main.py --weaviate init`
- Run `python main.py --app de`
- Verify the app binds to `0.0.0.0:7860`
- Verify Caddy proxies `bot.hsg.ch` to the app

## Functional Smoke Tests

- Open the chatbot through the public domain
- Verify consent flow
- Verify German and English responses
- Verify retrieval from Weaviate
- Verify cache behavior
- Verify admissions handover path
- Verify booking widget visibility
- If imports are part of rollout:
  - verify `--scrape`
  - verify `--imports`
- If admin operations are required:
  - verify the DB app

## Go / No-Go Decision

### Go

- ER-155 fix branch is merged
- Docker base-image update is merged
- Weaviate initialization path works
- Chat app responds through Caddy on the deployment host
- Smoke tests pass

### No-Go

- Current GitHub `main` is deployed without the ER-155 fix
- `properties.yaml` remains unresolved on current `main`
- Import pipeline entrypoints remain broken
- Container image is built from the older vulnerable base image

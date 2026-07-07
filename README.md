# Executive Education RAG Chatbot

A retrieval-augmented chatbot for the University of St.Gallen Executive Education programmes. The current system covers **EMBA HSG**, **IEMBA HSG**, and **emba X**, supports **English and German**, and combines scraping, document import, vector retrieval, and a Gradio-based chat interface.

**Production:** live at `https://chatbot.emba.unisg.ch` — see [Production Deployment](#production-deployment).

## What The Repository Contains

- A RAG chat application for programme information and admissions guidance
- A scraping and import pipeline for keeping programme content up to date
- Weaviate-based retrieval across language-specific collections
- A Gradio chat UI plus a separate database management UI
- A growing pytest suite for consent flow, scraping, prompts, and formatting

## Core Features

- Programme-specific support for **EMBA HSG**, **IEMBA HSG**, and **emba X**
- Language handling for **English** and **German**
- Single lead-agent pipeline (gpt-4.1 via OpenRouter) with token streaming and a verified, auto-updated programme facts base
- Response formatting, ambiguity checks, and scope guarding
- Booking / handover flow with advisor-specific widgets
- Consent handling and user-profile tracking
- Scraping, chunking, import, and Weaviate collection management

## Project Layout

```text
HSG_RAG/
├── docs/                       # Architecture and operations documentation
├── src/
│   ├── apps/
│   │   ├── chat/               # Gradio chatbot application
│   │   └── dbapp/              # Database management UI
│   ├── config/                 # Runtime config loader
│   ├── const/                  # Static response and content constants
│   ├── database/               # Weaviate services and collection strategies
│   ├── notification/           # Notification helpers
│   ├── pipeline/               # Import pipeline orchestration
│   ├── rag/                    # Agent chain, prompts, formatting, scope handling
│   ├── scraping/               # Scraper, HTML processing, URL normalization
│   └── utils/                  # Shared utilities
├── tests/                      # Pytest suite
├── tools/                      # Operational scripts
├── config.py                   # Repository-level default settings
├── main.py                     # Main CLI entry point
├── pytest.ini                  # Default pytest behaviour
└── requirements.txt            # Python dependencies
```

## Required Environment Variables
Required values depend on the mode you want to run. 
See `.env.example` and [docs/configuration_system_documentation.md](docs/configuration_system_documentation.md) for the full configuration surface.

Following variables are required for every mode to run:

```bash
OPEN_ROUTER_API_KEY=...
WEAVIATE_API_KEY=...
WEAVIATE_CLUSTER_URL=...
```

Optional but commonly useful:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=...
LANGSMITH_ENDPOINT=https://api.smith.langchain.com

# Only needed for the opt-in LLM test suites (RUN_LLM_EVAL, RUN_UAT_LLM_JUDGE)
OPENAI_API_KEY=...
```

## Production Deployment

The bot runs on a dedicated EU host (Hetzner Falkenstein, `hsg-rag-prod-fsn1-1`) and is
publicly reachable at **`https://chatbot.emba.unisg.ch`**, intended to be embedded as an
`<iframe>` on `emba.unisg.ch` / `embax.ch`.

```text
Browser → Caddy (TLS via Let's Encrypt, reverse proxy, CSP)   deploy/Caddyfile
            └─ Docker container hsg-rag (127.0.0.1:7860)      python main.py --app de
                 ├─ Weaviate Cloud (EU)                        retrieval
                 └─ OpenRouter                                 LLM + embeddings
```

**Deployments are automated** via [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml)
(rsync → image build → container recreate → health checks). It runs on:

1. every push to `main` (doc-only changes excluded) — **merging a PR deploys it**,
2. every successful nightly *Update Programme Facts* run, so updated prices/deadlines
   reach production the same morning (the facts action pushes with `GITHUB_TOKEN`,
   which does not fire push workflows — hence the explicit `workflow_run` trigger),
3. manual dispatch from the Actions tab.

The previous image is kept as `hsg-rag:previous` for manual rollback. Caddy runs
directly on the host (systemd) and is untouched by app deploys; changes to
`deploy/Caddyfile` are applied with `systemctl reload caddy`.

Operational details, GDPR notes, and the go-live status live in
[DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) and
[docs/datenschutz_deployment.md](docs/datenschutz_deployment.md).

## Docker Deployment 
This application can be run locally or on a cloud VM using Docker.

### Prerequisites

1. Install Docker on your machine/VM
2. Clone this repository 
2. Fill the `.env` file with all required environment variables (copy from .env.example)

### Building the container 
You can build the container using the following command (recommended):

```bash
docker build --no-cache -t hsg-rag .
```

### Running the container 
You can use this command to start the container:

```bash
docker run --env-file .env \
           -p 7860:7860 \
           --name hsg-rag \
           hsg-rag
```

### Accessing the application 
After starting the container, open your browser and go to:
```bash
http://localhost:7860
```
(or http://<your-vm-ip>:7860 on a server)


## Local Setup 
The application can be run directly from the project's root directory.

1. Clone the repository.
2. Create and activate a virtual environment.

```bash
python -m venv venv
source venv/bin/activate
```

3. Install dependencies.

```bash
pip install -r requirements.txt
```

4. Create a local `.env` file from `.env.example`.

### Running the application locally

Start the chat UI in German:

```bash
python main.py --app de
```

Start the chat UI in English:

```bash
python main.py --app en
```

Show all CLI options:

```bash
python main.py --help
```

Useful operational commands:

```bash
python main.py --scrape simple
python main.py --scrape full
python main.py --imports path/to/file1 path/to/file2
python main.py --weaviate checkhealth
python main.py --weaviate init
python main.py --weaviate redo
python main.py --dbapp
```

Embedding model changes require a Weaviate collection rebuild and re-import:

```bash
python main.py --weaviate redo
python main.py --scrape full
# plus python main.py --imports ... for any local source files you maintain
```

The default cloud embedding path uses OpenRouter `openai/text-embedding-3-small`
and stores app-generated vectors in Weaviate. The existing scraper restoration
flow is unchanged.

## Testing

The default pytest configuration only runs tests that do **not** require network access or external services.

```bash
pytest -q
```

Current default behaviour from [pytest.ini](pytest.ini):

- `network` tests are excluded by default
- `integration` tests are excluded by default

Examples:

```bash
pytest -q tests/test_pricing_prompts.py
pytest -q tests/test_tone_and_handover.py
pytest -q -m integration
```

If optional dependencies are missing, some tests are skipped during collection via [tests/conftest.py](tests/conftest.py).

## Configuration Notes

The repository uses `config.py` as the default configuration source, with environment-based overrides loaded through `src/config/configs.py`.

Important defaults in the current repository state:

- Available languages: `en`, `de`
- Lead response target: `100` words
- Sub-agent response target: `200` words
- User-profile tracking: enabled

For details, see:

- [docs/configuration_system_documentation.md](docs/configuration_system_documentation.md)
- [docs/user_profile_tracking.md](docs/user_profile_tracking.md)
- [docs/weaviate_database_setup.md](docs/weaviate_database_setup.md)

## Repository Notes

- `main.py` is the supported entry point for local execution.
- `tools/scraping.py` is an operational scheduler / scraping helper, not the main app entry.
- The chatbot UI and the database UI are separate applications under `src/apps/`.

## License

MIT

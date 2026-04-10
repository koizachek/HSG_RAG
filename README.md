# Executive Education RAG Chatbot

A retrieval-augmented chatbot for the University of St.Gallen Executive Education programmes. The current system covers **EMBA HSG**, **IEMBA HSG**, and **emba X**, supports **English and German**, and combines scraping, document import, vector retrieval, caching, and a Gradio-based chat interface.

## What The Repository Contains

- A multi-agent RAG chat application for programme information and admissions guidance
- A scraping and import pipeline for keeping programme content up to date
- Weaviate-based retrieval across language-specific collections
- Response caching with `cloud`, `local`, and in-memory `dict` modes
- A Gradio chat UI plus a separate database management UI
- A growing pytest suite for consent flow, scraping, prompts, cache behaviour, and formatting

## Core Features

- Programme-specific support for **EMBA HSG**, **IEMBA HSG**, and **emba X**
- Language handling for **English** and **German**
- Lead-agent routing with programme-specific sub-agents
- Response formatting, ambiguity checks, scope guarding, and quality fallback handling
- Booking / handover flow with advisor-specific widgets
- Consent handling and user-profile tracking
- Scraping, chunking, import, and Weaviate collection management
- Configurable cache layer for Redis Cloud, local Redis, or in-memory operation

## Project Layout

```text
HSG_RAG/
├── docs/                       # Architecture and operations documentation
├── src/
│   ├── apps/
│   │   ├── chat/               # Gradio chatbot application
│   │   └── dbapp/              # Database management UI
│   ├── cache/                  # Cache facade, metrics, and strategies
│   ├── config/                 # Runtime config loader
│   ├── const/                  # Static response and content constants
│   ├── database/               # Redis and Weaviate services
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
OPENAI_API_KEY=...
WEAVIATE_API_KEY=...
WEAVIATE_CLUSTER_URL=...
HUGGING_FACE_API_KEY=...
```

Optional but commonly useful:

```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=...
LANGSMITH_PROJECT=...
LANGSMITH_ENDPOINT=https://api.smith.langchain.com

GROQ_API_KEY=...
OPEN_ROUTER_API_KEY=...

REDIS_CLOUD_HOST=...
REDIS_CLOUD_PORT=...
REDIS_CLOUD_PASSWORD=...
```

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
python main.py --scrape
python main.py --imports path/to/file1 path/to/file2
python main.py --weaviate checkhealth
python main.py --weaviate init
python main.py --weaviate redo
python main.py --clear-cache
python main.py --dbapp
```

Cache mode can be selected explicitly:

```bash
python main.py --app de --cache-mode dict
python main.py --app de --cache-mode local
python main.py --app de --cache-mode cloud
```

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
pytest -q tests/test_cache.py
pytest -q tests/test_pricing_prompts.py
pytest -q tests/test_tone_and_handover.py
pytest -q -m integration
```

If optional dependencies are missing, some tests are skipped during collection via [tests/conftest.py](tests/conftest.py).

## Configuration Notes

The repository uses `config.py` as the default configuration source, with environment-based overrides loaded through `src/config/configs.py`.

Important defaults in the current repository state:

- Available languages: `en`, `de`
- Default cache mode: `cloud`
- Cache TTL: `86400` seconds
- Cache max size: `1000`
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

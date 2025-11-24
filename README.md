# Executive MBA HSG Chatbot

A Retrieval-Augmented Generation (RAG) chatbot that provides information specifically about the Executive MBA HSG program from the University of St. Gallen Executive School.

## Overview

This chatbot uses web scraping to collect information about the Executive MBA HSG program from the University of St. Gallen Executive School website, processes the data, and creates a knowledge base that can be queried using natural language. The system uses LangChain and vector embeddings to provide accurate and relevant responses specifically about the Executive MBA HSG program.

## Features

- Web scraping of Executive MBA HSG program information from the University of St. Gallen Executive School website
- Extraction of program details including duration, curriculum, costs, admission requirements, schedules, faculty info, and deadlines
- Vector database for efficient information retrieval
- Natural language interface for querying information about the Executive MBA HSG program
- Contextual responses based on the latest program data

## Project Structure

```
HSG_RAG/
├── data/                      # Scraped and processed data
├── src/
│   ├── apps/                  # User interface applications
│   │   └── chat/              # Gradio chatbot interface
│   ├── database/              # Weaviate vector database
│   │   └── weavservice.py     # Database operations
│   ├── pipeline/              # Data import pipeline
│   │   └── pipeline.py        # Orchestration & deduplication
│   ├── processing/            # Document processing
│   │   └── processor.py       # WebsiteProcessor & DataProcessor
│   ├── rag/                   # RAG agent implementation
│   │   ├── agent_chain.py     # Multi-agent orchestration
│   │   ├── models.py          # LLM configuration
│   │   ├── prompts.py         # Agent prompts
│   │   └── middleware.py      # Error handling & retries
│   └── utils/                 # Utilities
│       ├── logging.py         # Centralized logging
│       └── lang.py            # Language detection
├── main.py                    # Application entry point
├── config.py                  # Configuration settings
└── requirements.txt           # Project dependencies
```

## Setup

1. Clone the repository
2. Create a virtual environment:
   ```
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```
3. Install dependencies:
   ```
   pip install -r requirements.txt
   ```
4. Create a `.env` file with your API keys (copy from `.env.example`):
   
   **Required:**
   ```
   OPENAI_API_KEY=your_openai_api_key
   WEAVIATE_API_KEY=your_weaviate_api_key
   HUGGING_FACE_API_KEY=your_hf_api_key
   ```
   
   **Optional (for LangSmith tracing/debugging):**
   ```
   LANGSMITH_TRACING=true
   LANGSMITH_API_KEY=your_langsmith_api_key
   LANGSMITH_PROJECT=your_project_name
   LANGSMITH_ENDPOINT=https://api.smith.langchain.com
   ```
   
   **Optional (alternative LLM providers):**
   ```
   GROQ_API_KEY=your_groq_api_key
   OPEN_ROUTER_API_KEY=your_openrouter_api_key
   ```
   
   See `.env.example` for the complete template.
    

## Usage

1. Run the gradio application with the virtual environment activated:
   ```
   python main.py --app de
   ```
   If you want to know the full set of tools, run this command:
   ```
   python main.py --help
   ```
2. Open the application using the local URL shown in the terminal:
   ```
   * Running on local URL:  http://127.0.0.1:7861
   ```
3. Start asking your questions to the assistant!

## Some Example Queries ENGLISH/GERMAN

- "How long is the Executive MBA HSG program?"
- "What are the admission requirements for the Executive MBA HSG?"
- "When is the application deadline for the next cohort?"
- "How much does the Executive MBA HSG program cost?"
- "What is the curriculum of the Executive MBA HSG?"
- "Who are the faculty members for the Executive MBA HSG?"
- "Wie ist das EMBA HSG Programm strukturiert?"
- "Welche Akkreditierungen besitzt das EMBA HSG Programm?"
- "Was sind die Zulassungsvoraussetzungen für das EMBA HSG?"

## Deployment to HuggingFace Spaces

This application is deployed at: **https://huggingface.co/spaces/Pygmales/hsg_rag_eea**

The HuggingFace Space runs the Gradio interface directly via:
```bash
python main.py --app de  # or --app en for English
```

### Required Secrets for HuggingFace Spaces

Configure these in your HuggingFace Space settings:
- `OPENAI_API_KEY` - OpenAI API access
- `WEAVIATE_API_KEY` - Weaviate Cloud database access
- `HUGGING_FACE_API_KEY` - For embeddings (if using cloud Weaviate)
- `LANGSMITH_TRACING` - (optional) Enable LangSmith tracing for debugging
- `LANGSMITH_API_KEY` - (optional) LangSmith API key
- `LANGSMITH_PROJECT` - (optional) LangSmith project name

The application automatically uses environment variables for configuration, making deployment seamless.

## License

MIT

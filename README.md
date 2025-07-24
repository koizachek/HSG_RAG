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
executive_ed/
├── data/                      # Scraped and processed data
├── src/
│   ├── scraper/               # Web scraping module
│   │   ├── scraper.py         # Main scraping functionality
│   │   └── parser.py          # HTML parsing utilities
│   ├── processing/            # Data processing module
│   │   └── processor.py       # Data cleaning and structuring
│   ├── database/              # Vector database module
│   │   └── vectordb.py        # Vector DB implementation
│   ├── rag/                   # RAG implementation
│   │   ├── chain.py           # LangChain implementation
│   │   └── prompts.py         # Prompt templates
│   └── ui/                    # User interface
│       └── cli.py             # Command-line interface
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
4. Create a `.env` file with your API keys:
   ```
   OPENAI_API_KEY=your_openai_api_key
   ```

## Usage

1. Run the scraper to collect program data:
   ```
   python main.py --scrape
   ```

2. Start the chatbot:
   ```
   python main.py
   ```

3. Ask questions specifically about the Executive MBA HSG program at the University of St. Gallen.

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

## License

MIT

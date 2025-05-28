# Executive Education RAG Chatbot

A Retrieval-Augmented Generation (RAG) chatbot that helps customers find executive education programs from the University of St. Gallen Executive School.

## Overview

This chatbot uses web scraping to collect program information from the University of St. Gallen Executive School website, processes the data, and creates a knowledge base that can be queried using natural language. The system uses LangChain and vector embeddings to provide accurate and relevant responses about executive education programs.

## Features

- Web scraping of program information from the University of St. Gallen Executive School website
- Extraction of program details including names, duration, curriculum, costs, admission requirements, schedules, faculty info, and deadlines
- Vector database for efficient information retrieval
- Natural language interface for querying program information
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

3. Ask questions about executive education programs at the University of St. Gallen.

## Some Example Queries ENGLISH/GERMAN

- "What MBA programs are available?"
- "How long is the Executive MBA program?"
- "What are the admission requirements for the Executive MBA in Digital Business?"
- "When is the application deadline for the next cohort?"
- "How much does the Business Engineering program cost?"
- "Wie international ist das EMBA HSG aufgestellt?"
- "Welche Akkreditierungen besitzt das EMBA HSG Programm?"
- "Was unterscheidet das IEMBA HSG vom klassischen EMBA?" 

## License

MIT

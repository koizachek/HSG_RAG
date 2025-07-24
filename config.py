"""
Configuration settings for the Executive Education RAG Chatbot.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Base URL for scraping
BASE_URL = "https://emba.unisg.ch/programm/emba"

# OpenAI API configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
EMBEDDING_MODEL = "text-embedding-3-small"
CHAT_MODEL = "gpt-4o"

# Scraper settings
SCRAPER_TIMEOUT = 30  # seconds
SCRAPER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
}

# Data paths
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RAW_DATA_PATH = os.path.join(DATA_DIR, "raw_data.json")
PROCESSED_DATA_PATH = os.path.join(DATA_DIR, "processed_data.json")
VECTORDB_PATH = os.path.join(DATA_DIR, "vectordb")

# Vector database settings
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200

# RAG settings
TOP_K_RETRIEVAL = 5  # Number of documents to retrieve for each query

# UI settings
MAX_HISTORY = 10  # Maximum number of conversation turns to keep in history

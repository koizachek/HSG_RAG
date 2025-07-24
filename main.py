"""
Main entry point for the Executive Education RAG Chatbot.
"""
import argparse
import os
import sys
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

from src.scraper.scraper import Scraper
from src.processing.processor import DataProcessor
from src.database.vectordb import VectorDatabase
from src.ui.cli import ChatbotCLI
from src.utils.logging import init_logging, get_logger

# Initialize logging
init_logging()
logger = get_logger(__name__)

# Load environment variables
load_dotenv()

def check_api_key() -> bool:
    """
    Check if the OpenAI API key is set.

    Returns:
        True if the API key is set, False otherwise.
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        logger.error("OpenAI API key not found. Please set the OPENAI_API_KEY environment variable.")
        return False
    return True


def run_scraper(use_selenium: bool = True) -> None:
    """
    Run the scraper to collect program data.

    Args:
        use_selenium: Whether to use Selenium for scraping.
    """
    logger.info("Running scraper...")
    scraper = Scraper(use_selenium=use_selenium)
    scraper.run()
    logger.info("Scraping completed.")


def run_processor() -> None:
    """Run the data processor to clean and structure the scraped data."""
    logger.info("Running data processor...")
    processor = DataProcessor()
    processor.run()
    logger.info("Data processing completed.")


def run_vectordb() -> None:
    """Run the vector database setup to create embeddings for the processed data."""
    if not check_api_key():
        return
    
    logger.info("Running vector database setup...")
    vector_db = VectorDatabase()
    vector_db.run()
    logger.info("Vector database setup completed.")


def run_chatbot() -> None:
    """Run the chatbot CLI."""
    if not check_api_key():
        return
    
    logger.info("Starting chatbot...")
    cli = ChatbotCLI()
    cli.run()


def run_pipeline() -> None:
    """Run the complete pipeline: scraping, processing, vector database setup, and chatbot."""
    logger.info("Running complete pipeline...")
    
    # Run scraper
    run_scraper()
    
    # Run processor
    run_processor()
    
    # Run vector database setup
    if check_api_key():
        run_vectordb()
    
    # Run chatbot
    if check_api_key():
        run_chatbot()


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="University of St. Gallen Executive Education RAG Chatbot")
    
    # Add arguments
    parser.add_argument("--scrape", action="store_true", help="Run the scraper to collect program data")
    parser.add_argument("--process", action="store_true", help="Run the data processor to clean and structure the scraped data")
    parser.add_argument("--vectordb", action="store_true", help="Run the vector database setup to create embeddings for the processed data")
    parser.add_argument("--chatbot", action="store_true", help="Run the chatbot CLI")
    parser.add_argument("--pipeline", action="store_true", help="Run the complete pipeline: scraping, processing, vector database setup, and chatbot")
    parser.add_argument("--no-selenium", action="store_true", help="Disable Selenium for scraping (use requests only)")
    
    return parser.parse_args()


def main():
    """Main entry point for the application."""
    args = parse_args()
    
    # Check if any argument is provided
    if not any([args.scrape, args.process, args.vectordb, args.chatbot, args.pipeline]):
        # If no argument is provided, run the chatbot by default
        run_chatbot()
        return
    
    # Run the specified components
    if args.pipeline:
        run_pipeline()
    else:
        if args.scrape:
            run_scraper(use_selenium=not args.no_selenium)
        
        if args.process:
            run_processor()
        
        if args.vectordb:
            run_vectordb()
        
        if args.chatbot:
            run_chatbot()


if __name__ == "__main__":
    main()

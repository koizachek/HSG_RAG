"""
Main entry point for the Executive Education RAG Chatbot.
"""
import argparse
import langsmith
from langsmith import traceable
from src.utils.logging import init_logging, get_logger
from config import AVAILABLE_LANGUAGES

from dotenv import load_dotenv

load_dotenv()


# Initialize logging
def logging_startup():
    init_logging(interactive_mode=False)
    return get_logger('main_module')


def run_scraper() -> None:
    """
    Run the scraper to collect program data.

    Args:
        use_selenium: Whether to use Selenium for scraping.
    """
    from src.pipeline.pipeline import ImportPipeline
    logger = logging_startup()

    logger.info("Running scraper...")
    ImportPipeline().scrape_website()
    logger.info("Scraping completed.")


def run_importer(sources: list[str]) -> None:
    """Run the data import pipeline."""
    from src.pipeline.pipeline import ImportPipeline
    logger = logging_startup()

    logger.info("Running data import pipeline...")
    ImportPipeline().import_many_documents(sources)
    logger.info("Data processing completed.")


def run_weaviate_command(command: str, backup_id: str = None):
    """Run commands to manipulate the database contents."""
    from src.database.weavservice import WeaviateService
    logger = logging_startup()

    logger.info(f"Running database command {command}")
    if command == 'restore' and not backup_id:
        logger.error("Backup ID is required to initalize the restore process.")

    service = WeaviateService()
    if command == 'backup':
        service._create_backup()

    if command == 'restore':
        service._restore_backup(backup_id)

    if command == 'delete' or command == 'redo':
        service._delete_collections()

    if command == 'init' or command == 'redo':
        service._create_collections()

    if command == 'checkhealth' or command == 'init' or command == 'redo':
        service._checkhealth()


def run_application(lang: str) -> None:
    """Run the chatbot web application."""
    from src.apps.chat.app import ChatbotApplication
    logger = logging_startup()

    logger.info("Starting chatbot web application...")
    app = ChatbotApplication(language=lang)
    app.run()


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="University of St. Gallen Executive Education RAG Chatbot")

    # Add arguments
    parser.add_argument("--scrape", action="store_true",
                        help="Scrapes the data from the HSG website and imports it into the database")
    parser.add_argument("--imports", nargs="+", help="Runs the data importing pipeline for the provided files")

    parser.add_argument("--weaviate", type=str, choices=['init', 'delete', 'redo', 'checkhealth', 'backup', 'restore'],
                        help="Runs different database actions")
    parser.add_argument("--backup-id", type=str, help="Required when calling the --weaviate restore command!")

    parser.add_argument("--cli", action="store_true", help="Run the chatbot CLI")
    parser.add_argument("--app", type=str, choices=AVAILABLE_LANGUAGES, help="Run the chatbot web application")

    return parser.parse_args()


def main():
    """Main entry point for the application."""
    args = parse_args()

    # Check if any argument is provided
    if not any([args.scrape, args.imports, args.weaviate, args.cli, args.app]):
        # If no argument is provided, run the chatbot by default
        run_application()
        return

        # Run the specified components
    if args.scrape:
        run_scraper()

    if args.imports:
        run_importer(args.imports)

    if args.weaviate:
        run_weaviate_command(command=args.weaviate, backup_id=args.backup_id)

    if args.app:
        run_application(args.app)


if __name__ == "__main__":
    main()

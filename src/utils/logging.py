"""
Centralized logging configuration for the Executive Education RAG Chatbot.
"""
import logging, os, sys, warnings, colorama
from collections import defaultdict
from colorama import Fore, Style
from typing import Literal

from src.config import config

file_handlers = defaultdict(list)

import json
from datetime import datetime, timezone
import os

# Initialize colorama for cross-platform color support
colorama.init()

class DefaultFormatter(logging.Formatter):
    def format(self, record):
        record = logging.makeLogRecord(record.__dict__)
        
        if hasattr(record, 'name'):
            rname = record.name if len(record.name) <= 17 else record.name[:14] + '...'
            record.name = rname

        return super().format(record)


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for console output ONLY.
       Never mutates the original LogRecord (so file handlers stay clean)."""
    
    COLORS = {
        'DEBUG':    Fore.CYAN,
        'INFO':     Fore.GREEN,
        'WARNING':  Fore.YELLOW,
        'ERROR':    Fore.RED,
        'CRITICAL': Fore.MAGENTA + Style.BRIGHT,
    }
    ALIASES = {
        'DEBUG':    'DEBUG',
        'INFO':     'INFO ',
        'WARNING':  'WARN ',
        'ERROR':    'ERROR',
        'CRITICAL': 'CRITC'
    }
    
    def format(self, record):
        record = logging.makeLogRecord(record.__dict__)

        # Add color to the level name
        if hasattr(record, 'levelname') and record.levelname in self.COLORS:
            lname = record.levelname
            color = self.COLORS[lname]
            
            if lname == 'ERROR' and hasattr(record, 'message'):
                record.message = f"{color}{record.message}{Style.RESET_ALL}"

            record.levelname = f"{color}{self.ALIASES[lname]}{Style.RESET_ALL}"

        # Add color to the module name
        if hasattr(record, 'name'):
            rname = record.name if len(record.name) <= 17 else record.name[:14] + '...'
            record.name = f"{Fore.CYAN}{rname}{Style.RESET_ALL}"

        return super().format(record)


def setup_logging(level: str = "INFO") -> logging.Logger:
    """
    Set up centralized logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)    
    Returns:
        Configured logger instance
    """
    os.makedirs(config.paths.LOGS, exist_ok=True)

    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Get root logger
    logger = logging.getLogger()
    
    # Avoid duplicate handlers if logger already configured
    if logger.handlers:
        logger.handlers.clear()
    
    logger.setLevel(numeric_level)
    
    # Create formatters
    detailed_formatter = DefaultFormatter(
        "(%(asctime)s) %(name)s\t %(levelname)s: %(message)s",
        datefmt="%Y.%m.%d %H:%M:%S"
    )
    
    colored_formatter = ColoredFormatter(
        "(%(asctime)s) %(name)s\t %(levelname)s: %(message)s",
        datefmt="%Y.%m.%d %H:%M:%S"
    )
        
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    
    # Use colored formatter if terminal supports it
    if _supports_color():
        console_handler.setFormatter(colored_formatter)
    else:
        console_handler.setFormatter(detailed_formatter)
        
    logger.addHandler(console_handler)
    
    return logger


def get_logger(module_name: str) -> logging.Logger:
    """
    Get a logger for a specific module.
    
    Args:
        module_name: Name of the module requesting the logger
    
    Returns:
        Logger instance
    """
    logger = logging.getLogger(module_name)
    logger.propagate = True 
    return logger


def create_file_handler(
    file_path: str, 
    module_name: str, 
    mode: Literal['a', 'w'] = 'a', 
    level = logging.WARNING
) -> logging.FileHandler:
    """
    Initializes a new FileHandler to redirect logs to the files.
    All subsequent calls to the 'append_handlers' function with the name of the module 
    will append handlers stored under the module name to the logger.

    Args:
        file_path: path to the .log file where logs will be stored.
        module_name: name of the logging module that this handler belongs to. 

    Returns:
        File handler instance.
    """
    global file_handlers

    file_handler = logging.FileHandler(
        file_path, 
        mode=mode,
        encoding='utf-8'
    )
    file_handler.setLevel(level)

    formatter = DefaultFormatter(
        "(%(asctime)s) %(name)s\t %(levelname)s: %(message)s",
        datefmt="%Y.%m.%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    
    file_handlers[module_name].append(file_handler)

    return file_handler


def append_file_handlers(logger: logging.Logger, module_name: str) -> None:
    global file_handlers

    for handler in file_handlers.get(module_name, []):
        logger.addHandler(handler)


def _supports_color() -> bool:
    """
    Check if the terminal supports color output.
    
    Returns:
        True if color is supported, False otherwise
    """
    # Check if we're in a terminal
    if not hasattr(sys.stdout, 'isatty') or not sys.stdout.isatty():
        return False
    
    # Check environment variables
    if os.getenv('NO_COLOR'):
        return False
    
    if os.getenv('FORCE_COLOR'):
        return True
    
    # Check terminal type
    term = os.getenv('TERM', '').lower()
    if 'color' in term or term in ['xterm', 'xterm-256color', 'screen']:
        return True
    
    return False


def configure_external_loggers(level: str = "WARNING") -> None:
    """
    Configure logging for external libraries to reduce noise.
    
    Args:
        level: Logging level for external libraries
    """
    external_loggers = [
        'selenium',
        'urllib3',
        'requests',
        'chromadb',
        'docling',
        'docling_core',
        'weaviate',
        'langchain',
        'langgraph',
        'openai',
        'httpx',
        'usp',
    ]
    
    numeric_level = getattr(logging, level.upper(), logging.WARNING)
    
    for logger_name in external_loggers:
        logging.getLogger(logger_name).setLevel(numeric_level)


def configure_internal_loggers():
    # Logging output for all loggers 
    root_handler = create_file_handler(
        file_path=os.path.join(config.paths.LOGS, 'logs.log'),
        module_name='*',
        mode='a',
        level=logging.INFO,
    )
    root_logger = logging.getLogger()
    root_logger.addHandler(root_handler)

    # Scraping loggers tree configuration
    scraping_handler = create_file_handler(
        file_path=os.path.join(config.paths.LOGS, 'scraping.log'), 
        module_name='scraping', 
        mode='w',
        level=logging.INFO,
    )
    scraping_logger = logging.getLogger('scraper')
    scraping_logger.addHandler(scraping_handler)


# Global configuration function
def init_logging(level: str = "INFO") -> None:
    """
    Initialize the global logging configuration.
    
    Args:
        level: Logging level
        log_file: Optional log file path
    """ 
    warnings.filterwarnings("ignore")

    # Set up root logger
    setup_logging(level=level)

    # Configure loggers defined by this application
    configure_internal_loggers()

    # Configure external library loggers
    configure_external_loggers()


class ConsentLogger:
    def __init__(self):
        log_dir = os.path.join('logs', 'consent')
        os.makedirs(log_dir, exist_ok=True)

    def log(self, session_id: str, decision: str, policy_version="1.0"):
        try:
            entry = {
                "session_id": session_id,
                "decision": decision,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "policy_version": policy_version
            }

            log_path = os.path.join('logs', 'consent', f"{session_id}.jsonl")
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, indent=2) + "\n")
                
        except Exception as e:
            print(f"Error logging consent decision: {e}")

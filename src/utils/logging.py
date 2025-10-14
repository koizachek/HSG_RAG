"""
Centralized logging configuration for the Executive Education RAG Chatbot.
"""
import logging, os, sys, warnings
from pathlib import Path
from typing import Optional

import colorama
from colorama import Fore, Style

# Initialize colorama for cross-platform color support
colorama.init()


class ColoredFormatter(logging.Formatter):
    """Custom formatter with color support for console output."""
    
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
        # Add color to the level name
        if hasattr(record, 'levelname') and record.levelname in self.COLORS:
            lname = record.levelname
            if hasattr(record, 'message') and lname == 'ERROR':
                record.message = f"{self.COLORS[lname]}{record.message}{Style.RESET_ALL}"

            record.levelname = f"{self.COLORS[lname]}{self.ALIASES[lname]}{Style.RESET_ALL}"
            

        if hasattr(record, 'name'):
            rname = record.name if len(record.name) <= 17 else record.name[:14] + '...'
            record.name = f"{Fore.CYAN}{rname}{Style.RESET_ALL}"

        return super().format(record)


def setup_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    interactive_mode: bool = False,
    module_name: Optional[str] = None
) -> logging.Logger:
    """
    Set up centralized logging configuration.
    
    Args:
        level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Optional path to log file. If None, uses default location.
        interactive_mode: If True, logs only to file in interactive mode
        module_name: Name of the module requesting the logger
    
    Returns:
        Configured logger instance
    """
    # Convert string level to logging constant
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Create logger
    logger = logging.getLogger()
    
    # Avoid duplicate handlers if logger already configured
    if logger.handlers:
        logger.handlers.clear()
    
    logger.setLevel(numeric_level)
    
    # Create formatters
    detailed_formatter = logging.Formatter(
        "(%(asctime)s) %(name)s\t %(levelname)s: %(message)s",
        datefmt="%Y.%m.%d %H:%M:%S"
    )
    
    colored_formatter = ColoredFormatter(
        "(%(asctime)s) %(name)s\t %(levelname)s: %(message)s",
        datefmt="%Y.%m.%d %H:%M:%S"
    )
    
    # Set up file logging
    if log_file or interactive_mode:
        if not log_file:
            # Default log file location
            log_dir = Path("logs")
            log_dir.mkdir(exist_ok=True)
            log_file = log_dir / "rag_chatbot.log"
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(detailed_formatter)
        logger.addHandler(file_handler)
    
    # Set up console logging (unless in interactive mode)
    if not interactive_mode:
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


def detect_interactive_mode() -> bool:
    """
    Detect if the application is running in interactive mode.
    
    Returns:
        True if in interactive mode, False otherwise
    """
    # Check if no command line arguments were provided (except script name)
    if len(sys.argv) == 1:
        return True
    
    # Check if only the script name and no other arguments
    # This indicates the chatbot is running in default interactive mode
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
        'weaviate',
        'langchain',
        'openai',
        'httpx'
    ]
    
    numeric_level = getattr(logging, level.upper(), logging.WARNING)
    
    for logger_name in external_loggers:
        logging.getLogger(logger_name).setLevel(numeric_level)


# Global configuration function
def init_logging(
    level: str = "INFO",
    log_file: Optional[str] = None,
    interactive_mode: Optional[bool] = None
) -> None:
    """
    Initialize the global logging configuration.
    
    Args:
        level: Logging level
        log_file: Optional log file path
        interactive_mode: If None, auto-detect interactive mode
    """
    if interactive_mode is None:
        interactive_mode = detect_interactive_mode()
    
    warnings.filterwarnings("ignore", category=DeprecationWarning)

    # Set up root logger
    setup_logging(
        level=level,
        log_file=log_file,
        interactive_mode=interactive_mode
    )
    
    # Configure external library loggers
    configure_external_loggers()

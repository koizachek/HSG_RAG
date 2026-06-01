"""
Centralized logging configuration for the Executive Education RAG Chatbot.
"""
import json
import logging
import os
import re
import sys
import warnings
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from colorama import Fore, Style
from typing import Literal

import colorama

from src.config import config

file_handlers = defaultdict(list)
LATEST_LOG_NAME = "latest.log"
_CATEGORY_HANDLER_ATTR = "_hsg_category_file_handler"
_prepared_latest_paths: set[str] = set()

# Initialize colorama for cross-platform color support
colorama.init()


def _default_formatter() -> logging.Formatter:
    return DefaultFormatter(
        "(%(asctime)s) %(name)s\t %(levelname)s: %(message)s",
        datefmt="%Y.%m.%d %H:%M:%S"
    )


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
        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()
    
    logger.setLevel(numeric_level)
    
    # Create formatters
    detailed_formatter = _default_formatter()
    
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
    normalized_name = ".".join(part for part in str(module_name).strip().split(".") if part)
    logger = logging.getLogger(normalized_name)
    logger.propagate = True 
    return logger


def _build_file_handler(
    file_path: str, 
    mode: Literal['a', 'w'] = 'a', 
    level = logging.WARNING
) -> logging.FileHandler:
    log_dir = os.path.dirname(file_path)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(
        file_path, 
        mode=mode,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(_default_formatter())
    return file_handler


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

    file_handler = _build_file_handler(
        file_path=file_path,
        mode=mode,
        level=level,
    )
    
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


def _safe_category_name(name: str) -> str:
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(name).strip())
    return safe_name.strip("._") or "logs"


def _get_logging_categories() -> dict[str, list[str]]:
    categories = getattr(config.logging, "CATEGORIES", None) or {}
    if not isinstance(categories, dict):
        raise ValueError("LOG_CATEGORIES must be a mapping of category names to logger roots.")

    normalized_categories = {}
    for category_name, roots in categories.items():
        if isinstance(roots, str):
            roots = [roots]

        normalized_roots = []
        for root in roots or []:
            root = str(root).strip()
            if root:
                normalized_roots.append(root)

        if normalized_roots:
            normalized_categories[_safe_category_name(category_name)] = normalized_roots

    return normalized_categories


def _get_max_log_runs() -> int:
    max_runs = getattr(config.logging, "MAX_RUNS", 10)
    try:
        max_runs = int(max_runs)
    except (TypeError, ValueError):
        max_runs = 10

    return max(1, max_runs)


def _archive_path_for(latest_path: Path) -> Path:
    timestamp = datetime.fromtimestamp(latest_path.stat().st_mtime).strftime("%Y%m%d_%H%M%S")
    archive_path = latest_path.with_name(f"{timestamp}.log")

    index = 1
    while archive_path.exists():
        archive_path = latest_path.with_name(f"{timestamp}_{index}.log")
        index += 1

    return archive_path


def _prune_archived_logs(category_dir: Path, max_runs: int) -> None:
    max_archived_runs = max(0, max_runs - 1)
    archived_logs = [
        log_path for log_path in category_dir.glob("*.log")
        if log_path.is_file() and log_path.name != LATEST_LOG_NAME
    ]
    archived_logs.sort(key=lambda log_path: log_path.stat().st_mtime, reverse=True)

    for log_path in archived_logs[max_archived_runs:]:
        log_path.unlink()


def _prepare_latest_log(category_dir: Path, max_runs: int) -> Path:
    category_dir.mkdir(parents=True, exist_ok=True)
    latest_path = category_dir / LATEST_LOG_NAME
    resolved_latest_path = str(latest_path.resolve())

    if resolved_latest_path not in _prepared_latest_paths:
        if latest_path.exists() and latest_path.stat().st_size > 0:
            latest_path.replace(_archive_path_for(latest_path))
        elif not latest_path.exists():
            latest_path.touch()

        _prune_archived_logs(category_dir, max_runs)
        _prepared_latest_paths.add(resolved_latest_path)

    return latest_path


def _iter_existing_loggers():
    yield logging.getLogger()
    for logger in logging.Logger.manager.loggerDict.values():
        if isinstance(logger, logging.Logger):
            yield logger


def _remove_category_file_handlers() -> None:
    for logger in _iter_existing_loggers():
        for handler in list(logger.handlers):
            if getattr(handler, _CATEGORY_HANDLER_ATTR, False):
                logger.removeHandler(handler)
                handler.close()


def _deduplicate_roots(roots: list[str]) -> list[str]:
    if "*" in roots:
        return ["*"]

    seen = set()
    deduplicated = []
    for root in roots:
        normalized_root = ".".join(part for part in root.split(".") if part)
        if normalized_root and normalized_root not in seen:
            seen.add(normalized_root)
            deduplicated.append(normalized_root)

    return deduplicated


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
        'uvicorn',
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


def configure_internal_loggers(level: str = "INFO"):
    _remove_category_file_handlers()

    numeric_level = getattr(logging, level.upper(), logging.INFO)
    max_runs = _get_max_log_runs()
    categories = _get_logging_categories()

    for category_name, roots in categories.items():
        latest_path = _prepare_latest_log(
            Path(config.paths.LOGS) / category_name,
            max_runs=max_runs,
        )
        category_handler = _build_file_handler(
            file_path=str(latest_path),
            mode='a',
            level=numeric_level,
        )
        setattr(category_handler, _CATEGORY_HANDLER_ATTR, True)

        for root in _deduplicate_roots(roots):
            logger = logging.getLogger() if root == "*" else logging.getLogger(root)
            logger.setLevel(numeric_level)
            logger.addHandler(category_handler)


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

    # Configure external library loggers
    configure_external_loggers()

    # Configure loggers defined by this application
    configure_internal_loggers(level=level)


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

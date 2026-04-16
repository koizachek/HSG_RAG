from __future__ import annotations

import importlib.util
from pathlib import Path


TEST_DEPENDENCIES = {
    "tests/consent/test_agent_chain_session.py": {"langchain_core", "langchain", "langsmith"},
    "tests/consent/test_consent_logger.py": {"colorama"},
    "tests/scraping/test_happy_path.py": {"colorama", "docling", "docling_core", "usp", "fake_useragent"},
    "tests/scraping/test_page_chunking.py": {"colorama", "docling", "docling_core"},
    "tests/scraping/test_scraping.py": {"colorama", "docling_core", "usp", "fake_useragent"},
    "tests/scraping/test_scraping_resume.py": {"colorama", "docling_core", "usp", "fake_useragent"},
    "tests/scraping/test_utils.py": {"fake_useragent"},
    "tests/test_cache.py": {"langchain"},
    "tests/test_chatbot_improvements.py": {"langchain_core", "langchain", "langsmith"},
    "tests/test_language_handling.py": {"langchain_core"},
    "tests/test_weaviate_connection.py": {"langchain_core", "langchain", "colorama"},
}


def _missing_dependency(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is None


def pytest_ignore_collect(collection_path: Path, config) -> bool:
    rel_path = collection_path.relative_to(Path(config.rootpath)).as_posix()
    required_modules = TEST_DEPENDENCIES.get(rel_path)
    if not required_modules:
        return False

    return any(_missing_dependency(module_name) for module_name in required_modules)

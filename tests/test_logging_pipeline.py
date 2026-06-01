import logging
import os
import time

from src.config import config
from src.utils import logging as logging_utils
from src.utils.logging import get_logger, init_logging


def _reset_logging_state():
    logging_utils._remove_category_file_handlers()
    for handler in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(handler)
        handler.close()
    logging_utils._prepared_latest_paths.clear()


def _flush_handlers():
    for logger in logging_utils._iter_existing_loggers():
        for handler in logger.handlers:
            handler.flush()


def test_logging_categories_route_to_latest_logs(monkeypatch, tmp_path):
    _reset_logging_state()
    monkeypatch.setattr(config.paths, "LOGS", str(tmp_path / "logs"))
    monkeypatch.setattr(
        config.logging,
        "CATEGORIES",
        {
            "all": ["*"],
            "scraping": ["scraper", "pipeline", "weaviate"],
            "weaviate": ["weaviate"],
        },
    )
    monkeypatch.setattr(config.logging, "MAX_RUNS", 10)

    init_logging()
    get_logger("scraper.core").info("scraper event")
    get_logger("pipeline.module").info("pipeline event")
    get_logger("weaviate.service").info("weaviate event")
    get_logger("rag.agent_chain").info("rag event")
    _flush_handlers()

    all_text = (tmp_path / "logs" / "all" / "latest.log").read_text(encoding="utf-8")
    scraping_text = (tmp_path / "logs" / "scraping" / "latest.log").read_text(encoding="utf-8")
    weaviate_text = (tmp_path / "logs" / "weaviate" / "latest.log").read_text(encoding="utf-8")

    assert "scraper event" in all_text
    assert "pipeline event" in all_text
    assert "weaviate event" in all_text
    assert "rag event" in all_text

    assert "scraper event" in scraping_text
    assert "pipeline event" in scraping_text
    assert "weaviate event" in scraping_text
    assert "rag event" not in scraping_text

    assert "weaviate event" in weaviate_text
    assert "scraper event" not in weaviate_text
    assert "pipeline event" not in weaviate_text

    _reset_logging_state()


def test_logging_categories_keep_configured_number_of_runs(monkeypatch, tmp_path):
    _reset_logging_state()
    logs_dir = tmp_path / "logs"
    category_dir = logs_dir / "all"
    category_dir.mkdir(parents=True)

    now = time.time()
    for index in range(4):
        archive_path = category_dir / f"old_{index}.log"
        archive_path.write_text(f"old run {index}", encoding="utf-8")
        os.utime(archive_path, (now - index - 10, now - index - 10))

    latest_path = category_dir / "latest.log"
    latest_path.write_text("previous run", encoding="utf-8")
    os.utime(latest_path, (now, now))

    monkeypatch.setattr(config.paths, "LOGS", str(logs_dir))
    monkeypatch.setattr(config.logging, "CATEGORIES", {"all": ["*"]})
    monkeypatch.setattr(config.logging, "MAX_RUNS", 3)

    init_logging()
    get_logger("main.module").info("current run")
    _flush_handlers()

    log_files = list(category_dir.glob("*.log"))
    archive_texts = [
        path.read_text(encoding="utf-8")
        for path in log_files
        if path.name != "latest.log"
    ]

    assert len(log_files) == 3
    assert latest_path.exists()
    assert "current run" in latest_path.read_text(encoding="utf-8")
    assert any("previous run" in text for text in archive_texts)
    assert not (category_dir / "old_3.log").exists()

    _reset_logging_state()

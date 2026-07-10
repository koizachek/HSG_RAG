"""
Unit tests for UsageEventLogger (src/utils/logging.py)

Tests: strict one-line JSONL format, schema envelope, config gating,
never-raises contract. The event content contract (no free text) is
covered at chain level in tests/test_usage_turn_outcomes.py.
"""
import json
import os
import sys

# Add project root to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import config
from src.utils.logging import UsageEventLogger


class TestUsageEventLogger:

    def test_event_written_as_one_line_jsonl(self, tmp_path):
        logger = UsageEventLogger(base_dir=str(tmp_path / "usage"))
        logger.log_turn({"session_id": "sess-1", "turn_index": 1, "outcome": "answered"})
        logger.log_turn({"session_id": "sess-1", "turn_index": 2, "outcome": "scope_redirect"})

        log_path = tmp_path / "usage" / "usage_sess-1.jsonl"
        assert log_path.exists()
        lines = log_path.read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2
        events = [json.loads(line) for line in lines]
        assert [e["turn_index"] for e in events] == [1, 2]

    def test_schema_envelope_added(self, tmp_path):
        logger = UsageEventLogger(base_dir=str(tmp_path / "usage"))
        logger.log_turn({"session_id": "sess-2", "outcome": "answered"})

        entry = json.loads(
            (tmp_path / "usage" / "usage_sess-2.jsonl").read_text(encoding="utf-8")
        )
        assert entry["schema_version"] == UsageEventLogger.SCHEMA_VERSION
        assert "timestamp" in entry
        assert entry["session_id"] == "sess-2"

    def test_per_session_files(self, tmp_path):
        logger = UsageEventLogger(base_dir=str(tmp_path / "usage"))
        logger.log_turn({"session_id": "sess-a"})
        logger.log_turn({"session_id": "sess-b"})

        assert (tmp_path / "usage" / "usage_sess-a.jsonl").exists()
        assert (tmp_path / "usage" / "usage_sess-b.jsonl").exists()

    def test_disabled_writes_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr(config.usage, "EVENT_LOGGING_ENABLED", False)
        logger = UsageEventLogger(base_dir=str(tmp_path / "usage"))
        logger.log_turn({"session_id": "sess-3"})

        assert not (tmp_path / "usage").exists()

    def test_never_raises_on_unserializable_event(self, tmp_path):
        logger = UsageEventLogger(base_dir=str(tmp_path / "usage"))
        # object() is not JSON-serializable; the logger must swallow the error
        logger.log_turn({"session_id": "sess-4", "bad": object()})

    def test_no_directory_created_before_first_write(self, tmp_path):
        UsageEventLogger(base_dir=str(tmp_path / "usage"))
        assert not (tmp_path / "usage").exists()

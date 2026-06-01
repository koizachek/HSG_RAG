import json
import os
import time
from types import SimpleNamespace

from src.config import config
from src.rag.input_handler import InputHandler
from src.rag.utilclasses import StructuredAgentResponse
from src.utils import conversation_tracker as tracker_module
from src.utils.conversation_tracker import ConversationTurnTracker


def _reset_tracker_state():
    tracker_module._prepared_latest_paths.clear()


def test_conversation_tracker_writes_turn_details(monkeypatch, tmp_path):
    _reset_tracker_state()
    monkeypatch.setattr(config.paths, "LOGS", str(tmp_path / "logs"))
    monkeypatch.setattr(config.logging, "MAX_RUNS", 10)

    tracker = ConversationTurnTracker(session_id="session-1")

    def run_turn():
        tracker.record_input_handler(
            processed_query="I have 5 years of work experience",
            is_valid=True,
            fallback_triggered=True,
            fallback_category="numeric_default",
        )
        tracker.record_language_detection(
            response="en",
            duration_seconds=0.12345,
            method="detected",
        )
        tracker.record_retrieve_context_call(
            query="tuition deadline",
            program="emba",
            language="en",
            response_time_seconds=0.8,
            weaviate_response_time_seconds=0.6,
        )
        tracker.record_structured_agent_output(
            StructuredAgentResponse(
                response="Agent response",
                additional_details="Extra details",
                relevant_programs=["emba"],
                appointment_requested=True,
                show_booking_widget=True,
                is_context_dependent=True,
            )
        )
        return SimpleNamespace(response="Agent response")

    tracker.track_turn("5", run_turn)

    latest_path = tmp_path / "logs" / "conversation_turns" / "latest.json"
    payload = json.loads(latest_path.read_text(encoding="utf-8"))
    turn = payload["sessions"]["session-1"]["turns"][0]

    assert "log_type" not in payload
    assert turn["turn_number"] == 1
    assert turn["user_query"] == "5"
    assert turn["agent_response_message"] == "Agent response"
    assert turn["input_handler"]["fallback_triggered"] is True
    assert turn["input_handler"]["fallback_category"] == "numeric_default"
    assert turn["language_detection"]["response"] == "en"
    assert turn["retrieve_context"]["called"] is True
    assert turn["retrieve_context"]["calls"][0]["query"] == "tuition deadline"
    assert turn["retrieve_context"]["calls"][0]["weaviate_response_time_seconds"] == 0.6
    assert turn["structured_agent_output"]["relevant_programs"] == ["emba"]
    assert turn["structured_agent_output"]["additional_details"] == "Extra details"
    assert "true_fields" not in turn["structured_agent_output"]

    _reset_tracker_state()


def test_conversation_tracker_retention(monkeypatch, tmp_path):
    _reset_tracker_state()
    logs_dir = tmp_path / "logs"
    turns_dir = logs_dir / "conversation_turns"
    turns_dir.mkdir(parents=True)

    now = time.time()
    for index in range(4):
        archive_path = turns_dir / f"old_{index}.json"
        archive_path.write_text("{}", encoding="utf-8")
        os.utime(archive_path, (now - index - 10, now - index - 10))

    latest_path = turns_dir / "latest.json"
    latest_path.write_text('{"sessions": {"old": {"turns": [{"turn_number": 1}]}}}', encoding="utf-8")
    os.utime(latest_path, (now, now))

    monkeypatch.setattr(config.paths, "LOGS", str(logs_dir))
    monkeypatch.setattr(config.logging, "MAX_RUNS", 3)

    tracker = ConversationTurnTracker(session_id="session-1")
    tracker.track_turn("hello", lambda: SimpleNamespace(response="hi"))

    log_files = list(turns_dir.glob("*.json"))
    archived_texts = [
        path.read_text(encoding="utf-8")
        for path in log_files
        if path.name != "latest.json"
    ]

    assert len(log_files) == 3
    assert latest_path.exists()
    assert any('"old"' in text for text in archived_texts)
    assert not (turns_dir / "old_3.json").exists()

    _reset_tracker_state()


def test_input_handler_exposes_fallback_metadata():
    result = InputHandler.process_input_with_metadata("5", [])

    assert result.is_valid is True
    assert result.fallback_triggered is True
    assert result.fallback_category == "numeric_default"
    assert result.processed_message == "I have 5 years of work experience"

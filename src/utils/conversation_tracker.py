"""
Conversation turn tracking for ExecutiveAgentChain.
"""
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from time import perf_counter
from typing import Any, Callable

from src.config import config

LATEST_TURN_LOG_NAME = "latest.json"
CONVERSATION_TURNS_DIR = "conversation_turns"

_prepared_latest_paths: set[str] = set()
_write_lock = Lock()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _round_seconds(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value, 4)


def _archive_path_for(latest_path: Path) -> Path:
    timestamp = datetime.fromtimestamp(latest_path.stat().st_mtime).strftime("%Y%m%d_%H%M%S")
    archive_path = latest_path.with_name(f"{timestamp}.json")

    index = 1
    while archive_path.exists():
        archive_path = latest_path.with_name(f"{timestamp}_{index}.json")
        index += 1

    return archive_path


def _prune_archived_logs(log_dir: Path, max_runs: int) -> None:
    max_archived_runs = max(0, max_runs - 1)
    archived_logs = [
        log_path for log_path in log_dir.glob("*.json")
        if log_path.is_file() and log_path.name != LATEST_TURN_LOG_NAME
    ]
    archived_logs.sort(key=lambda log_path: log_path.stat().st_mtime, reverse=True)

    for log_path in archived_logs[max_archived_runs:]:
        log_path.unlink()


def _empty_payload() -> dict[str, Any]:
    timestamp = _utc_now()
    return {
        "started_at": timestamp,
        "updated_at": timestamp,
        "sessions": {},
    }


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists() or path.stat().st_size == 0:
        return _empty_payload()

    try:
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, OSError):
        return _empty_payload()

    if not isinstance(payload, dict):
        return _empty_payload()

    payload.setdefault("started_at", _utc_now())
    payload.setdefault("sessions", {})
    return payload


def _has_recorded_turns(path: Path) -> bool:
    payload = _load_json(path)
    sessions = payload.get("sessions", {})
    return any(session.get("turns") for session in sessions.values())


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload["updated_at"] = _utc_now()

    tmp_path = path.with_name(f"{path.stem}.tmp")
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(tmp_path, path)


def _get_max_runs() -> int:
    max_runs = getattr(config.logging, "MAX_RUNS", 10)
    try:
        max_runs = int(max_runs)
    except (TypeError, ValueError):
        max_runs = 10

    return max(1, max_runs)


def _to_plain_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, (str, int, float, bool)):
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if isinstance(value, dict):
        return value
    return {
        key: getattr(value, key)
        for key in dir(value)
        if not key.startswith("_") and not callable(getattr(value, key))
    }


class ConversationTurnTracker:
    def __init__(
        self,
        session_id: str,
        logs_root: str | Path | None = None,
        max_runs: int | None = None,
    ) -> None:
        self.session_id = session_id
        self.max_runs = max(1, int(max_runs)) if max_runs is not None else _get_max_runs()
        self.log_dir = Path(logs_root or config.paths.LOGS) / CONVERSATION_TURNS_DIR
        self.latest_path = self._prepare_latest_json()
        self._current_turn: dict[str, Any] | None = None
        self._turn_number = self._load_turn_number()

    def track_turn(self, user_query: str, callback: Callable[[], Any]) -> Any:
        self.start_turn(user_query)
        started = perf_counter()
        response = None
        error = None

        try:
            response = callback()
            return response
        except Exception as exc:
            error = exc
            raise
        finally:
            self.finish_turn(
                response=response,
                response_time_seconds=perf_counter() - started,
                error=error,
            )

    def start_turn(self, user_query: str) -> None:
        self._turn_number += 1
        self._current_turn = {
            "turn_number": self._turn_number,
            "timestamp": _utc_now(),
            "user_query": user_query,
            "agent_response_message": None,
            "response_time_seconds": None,
            "language_detection": None,
            "input_handler": {
                "fallback_triggered": False,
                "fallback_category": None,
            },
            "retrieve_context": {
                "called": False,
                "calls": [],
            },
            "structured_agent_output": None,
        }

    def record_input_handler(
        self,
        *,
        processed_query: str,
        is_valid: bool,
        fallback_triggered: bool,
        fallback_category: str | None,
    ) -> None:
        if self._current_turn is None:
            return

        self._current_turn["input_handler"] = {
            "processed_query": processed_query,
            "is_valid": bool(is_valid),
            "fallback_triggered": bool(fallback_triggered),
            "fallback_category": fallback_category,
        }

    def record_language_detection(
        self,
        *,
        response: str | None,
        duration_seconds: float,
        method: str | None = None,
    ) -> None:
        if self._current_turn is None:
            return

        self._current_turn["language_detection"] = {
            "response": response,
            "duration_seconds": _round_seconds(duration_seconds),
            "method": method,
        }

    def record_retrieve_context_call(
        self,
        *,
        query: str,
        program: str | None,
        language: str | None,
        response_time_seconds: float,
        weaviate_response_time_seconds: float | None,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        if self._current_turn is None:
            return

        retrieve_context = self._current_turn["retrieve_context"]
        retrieve_context["called"] = True
        call_record = {
            "query": query,
            "program": program,
            "language": language,
            "response_time_seconds": _round_seconds(response_time_seconds),
            "weaviate_response_time_seconds": _round_seconds(weaviate_response_time_seconds),
            "success": bool(success),
        }
        if error:
            call_record["error"] = error
        retrieve_context["calls"].append(call_record)

    def record_structured_agent_output(
        self,
        structured_output: Any,
        *,
        additional_details: str | None = None,
    ) -> None:
        if self._current_turn is None:
            return

        self._current_turn["structured_agent_output"] = self._extract_structured_output(
            structured_output,
            additional_details=additional_details,
        )

    def finish_turn(
        self,
        *,
        response: Any,
        response_time_seconds: float,
        error: Exception | None = None,
    ) -> None:
        if self._current_turn is None:
            return

        self._current_turn["response_time_seconds"] = _round_seconds(response_time_seconds)
        self._current_turn["agent_response_message"] = self._extract_response_message(response)

        if self._current_turn["structured_agent_output"] is None:
            self._current_turn["structured_agent_output"] = self._extract_structured_output(response)

        if error is not None:
            self._current_turn["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }

        self._append_turn(self._current_turn)
        self._current_turn = None

    def _prepare_latest_json(self) -> Path:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        latest_path = self.log_dir / LATEST_TURN_LOG_NAME
        resolved_latest_path = str(latest_path.resolve())

        with _write_lock:
            if resolved_latest_path not in _prepared_latest_paths:
                if (
                    latest_path.exists()
                    and latest_path.stat().st_size > 0
                    and _has_recorded_turns(latest_path)
                ):
                    latest_path.replace(_archive_path_for(latest_path))

                _prune_archived_logs(self.log_dir, self.max_runs)
                _write_json(latest_path, _empty_payload())
                _prepared_latest_paths.add(resolved_latest_path)

        return latest_path

    def _load_turn_number(self) -> int:
        payload = _load_json(self.latest_path)
        session = payload.get("sessions", {}).get(self.session_id, {})
        turns = session.get("turns", [])
        if not turns:
            return 0

        return max(int(turn.get("turn_number", 0)) for turn in turns)

    def _append_turn(self, turn: dict[str, Any]) -> None:
        with _write_lock:
            payload = _load_json(self.latest_path)
            sessions = payload.setdefault("sessions", {})
            session = sessions.setdefault(
                self.session_id,
                {
                    "session_id": self.session_id,
                    "turn_count": 0,
                    "turns": [],
                },
            )
            session.setdefault("turns", []).append(turn)
            session["turn_count"] = len(session["turns"])
            _write_json(self.latest_path, payload)

    @staticmethod
    def _extract_response_message(response: Any) -> str | None:
        if response is None:
            return None
        if isinstance(response, str):
            return response
        return getattr(response, "response", None)

    @staticmethod
    def _extract_structured_output(
        structured_output: Any,
        *,
        additional_details: str | None = None,
    ) -> dict[str, Any]:
        data = _to_plain_dict(structured_output)

        details = additional_details
        if details is None:
            details = data.get("additional_details")

        output = {
            "relevant_programs": data.get("relevant_programs") or [],
            "show_booking_widget": data.get("show_booking_widget"),
            "appointment_requested": data.get("appointment_requested"),
            "is_context_dependent": data.get("is_context_dependent"),
        }

        if details:
            output["additional_details"] = details

        return output

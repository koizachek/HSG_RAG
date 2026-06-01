"""
Render conversation turn tracker JSON as Markdown.
"""
import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import config
from src.utils.conversation_tracker import CONVERSATION_TURNS_DIR, LATEST_TURN_LOG_NAME


def _default_input_path() -> Path:
    return Path(config.paths.LOGS) / CONVERSATION_TURNS_DIR / LATEST_TURN_LOG_NAME


def _default_output_path(input_path: Path) -> Path:
    return input_path.with_suffix(".md")


def _load_payload(input_path: Path) -> dict[str, Any]:
    with input_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)

    if not isinstance(payload, dict):
        raise ValueError("Conversation tracker JSON root must be an object.")

    return payload


def _format_seconds(value: Any) -> str:
    if value is None:
        return "n/a"

    try:
        return f"{float(value):.4f}s"
    except (TypeError, ValueError):
        return str(value)


def _format_bool(value: Any) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "n/a"


def _format_list(values: Any) -> str:
    if not values:
        return "none"
    if isinstance(values, list):
        return ", ".join(str(value) for value in values) if values else "none"
    return str(values)


def _format_block(value: Any) -> str:
    if value is None:
        value = ""
    text = str(value).strip().replace("```", "'''")
    return f"```text\n{text}\n```"


def _render_retrieve_context(retrieve_context: dict[str, Any]) -> list[str]:
    lines = ["**Retrieve Context**"]
    calls = retrieve_context.get("calls") or []
    if not retrieve_context.get("called") or not calls:
        lines.append("- Called: false")
        return lines

    lines.append("- Called: true")
    for index, call in enumerate(calls, start=1):
        lines.extend(
            [
                f"- Call {index}:",
                f"  - Query: {call.get('query') or 'n/a'}",
                f"  - Program: {call.get('program') or 'n/a'}",
                f"  - Language: {call.get('language') or 'n/a'}",
                f"  - Response time: {_format_seconds(call.get('response_time_seconds'))}",
                f"  - Weaviate response time: {_format_seconds(call.get('weaviate_response_time_seconds'))}",
                f"  - Success: {_format_bool(call.get('success'))}",
            ]
        )
        if call.get("error"):
            lines.append(f"  - Error: {call['error']}")

    return lines


def _render_structured_output(structured_output: dict[str, Any] | None) -> list[str]:
    structured_output = structured_output or {}
    lines = [
        "**Structured Agent Output**",
        f"- Relevant programs: {_format_list(structured_output.get('relevant_programs'))}",
        f"- show_booking_widget: {_format_bool(structured_output.get('show_booking_widget'))}",
        f"- appointment_requested: {_format_bool(structured_output.get('appointment_requested'))}",
        f"- is_context_dependent: {_format_bool(structured_output.get('is_context_dependent'))}",
    ]

    if structured_output.get("additional_details"):
        lines.extend(
            [
                "- Additional details:",
                _format_block(structured_output["additional_details"]),
            ]
        )

    return lines


def _render_turn(turn: dict[str, Any]) -> list[str]:
    language_detection = turn.get("language_detection") or {}
    input_handler = turn.get("input_handler") or {}

    lines = [
        f"### Turn {turn.get('turn_number', 'n/a')}",
        f"- Timestamp: {turn.get('timestamp') or 'n/a'}",
        f"- Response time: {_format_seconds(turn.get('response_time_seconds'))}",
        "",
        "**User Query**",
        _format_block(turn.get("user_query")),
        "",
        "**Agent Response**",
        _format_block(turn.get("agent_response_message")),
        "",
        "**Language Detection**",
        f"- Response: {language_detection.get('response') or 'n/a'}",
        f"- Method: {language_detection.get('method') or 'n/a'}",
        f"- Duration: {_format_seconds(language_detection.get('duration_seconds'))}",
        "",
        "**Input Handler**",
        f"- Valid: {_format_bool(input_handler.get('is_valid'))}",
        f"- Fallback triggered: {_format_bool(input_handler.get('fallback_triggered'))}",
        f"- Fallback category: {input_handler.get('fallback_category') or 'none'}",
        f"- Processed query: {input_handler.get('processed_query') or 'n/a'}",
        "",
    ]
    lines.extend(_render_retrieve_context(turn.get("retrieve_context") or {}))
    lines.append("")
    lines.extend(_render_structured_output(turn.get("structured_agent_output")))

    if turn.get("error"):
        error = turn["error"]
        lines.extend(
            [
                "",
                "**Error**",
                f"- Type: {error.get('type') or 'n/a'}",
                f"- Message: {error.get('message') or 'n/a'}",
            ]
        )

    return lines


def render_markdown(
    payload: dict[str, Any],
    *,
    source_path: str | Path | None = None,
    session_id: str | None = None,
) -> str:
    sessions = payload.get("sessions") or {}
    if not isinstance(sessions, dict):
        raise ValueError("Conversation tracker JSON field 'sessions' must be an object.")

    if session_id:
        sessions = {
            session_id: sessions[session_id]
        } if session_id in sessions else {}

    total_turns = sum(len((session or {}).get("turns") or []) for session in sessions.values())
    lines = [
        "# Conversation Turn Report",
        "",
        f"- Source: {source_path or 'n/a'}",
        f"- Generated at: {datetime.now(timezone.utc).isoformat()}",
        f"- Log started at: {payload.get('started_at') or 'n/a'}",
        f"- Log updated at: {payload.get('updated_at') or 'n/a'}",
        f"- Sessions: {len(sessions)}",
        f"- Turns: {total_turns}",
        "",
    ]

    if not sessions:
        lines.append("No conversation turns found.")
        return "\n".join(lines).rstrip() + "\n"

    for current_session_id, session in sessions.items():
        session = session or {}
        turns = session.get("turns") or []
        lines.extend(
            [
                f"## Session `{current_session_id}`",
                "",
                f"- Turn count: {session.get('turn_count', len(turns))}",
                "",
            ]
        )

        for turn in turns:
            lines.extend(_render_turn(turn or {}))
            lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def convert_file(
    input_path: str | Path,
    output_path: str | Path | None = None,
    *,
    session_id: str | None = None,
) -> Path:
    input_path = Path(input_path)
    output_path = Path(output_path) if output_path else _default_output_path(input_path)
    payload = _load_payload(input_path)
    markdown = render_markdown(payload, source_path=input_path, session_id=session_id)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")
    return output_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Render conversation tracker JSON into a Markdown report."
    )
    parser.add_argument(
        "--input",
        default=str(_default_input_path()),
        help="Path to the conversation tracker JSON file.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Path to write the Markdown report. Defaults to the input path with .md suffix.",
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="Optional session id to render. Renders all sessions when omitted.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_path = convert_file(
        input_path=args.input,
        output_path=args.output,
        session_id=args.session_id,
    )
    print(f"Wrote Markdown report to {output_path}")


if __name__ == "__main__":
    main()

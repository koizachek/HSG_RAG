"""
One-shot cleanup: physically removes the legacy keyword/regex fact routers,
the subagent call wrappers and the old chunk-based fact provider from
src/rag/agent_chain.py (~1800 lines).

These paths have been disabled since the verified-facts refactor and the full
eval suite passes without them. The script is anchor-based and refuses to
write anything unless every anchor matches exactly once AND the resulting
file compiles. Run it once, run the tests, delete it.

Usage:
    python scripts/remove_legacy_code.py            # apply
    python scripts/remove_legacy_code.py --check    # dry-run, report only
"""
import sys
import os

TARGET = os.path.join(os.path.dirname(__file__), "..", "src", "rag", "agent_chain.py")

# (start_marker, end_marker): delete [start, end). The end marker is KEPT.
# Decorator lines directly above the end marker are kept as well.
DELETE_RANGES = [
    # _subagent_retrieval_fallback (fallback texts for the removed subagents)
    ("    @staticmethod\n    def _subagent_retrieval_fallback(",
     "    def _retrieve_context(self"),
    # _retrieve_context_via_tool + _call_emba/_call_iemba/_call_embax
    ('    @traceable(name="retrieve_context")',
     "    def _init_agents("),
    # Keyword routers part 1: programme preference/extraction helpers
    ("    def _query_mentions_specific_programme(",
     "    def _normalise_programme_id("),
    # Keyword routers part 2 + regex fact extraction + legacy serve_* methods
    ("    def _is_application_next_step_request(",
     "    def _text_mentions_multiple_programmes("),
    # Legacy programme overview builder
    ("    def _latest_ai_mentions_multiple_programmes(",
     "    def _serve_pending_continuation("),
]

# NOTE: `from langsmith import traceable` stays — query() itself is @traceable.
REMOVE_LINES = [
    "from src.rag.programme_facts import ProgrammeFacts, ProgrammeFactsProvider\n",
]

REPLACEMENTS = [
    (
        "from src.rag.middleware import (\n"
        "    AgentChainMiddleware as chainmdw,\n"
        "    ContextRetrievalError,\n"
        ")\n",
        "from src.rag.middleware import AgentChainMiddleware as chainmdw\n",
    ),
]

# Names that must be GONE afterwards (proves the dead code is really removed)
FORBIDDEN_AFTER = [
    "_serve_programme_overview",
    "_resolve_application_programmes",
    "_extract_chf_amounts",
    "_sentence_matches_programme",
    "_call_emba_agent",
    "_retrieve_context_via_tool",
    "ProgrammeFactsProvider",
    "_subagent_retrieval_fallback",
]

# Names the active path still needs (guards against over-deletion)
REQUIRED_AFTER = [
    "def _is_continuation_request(",
    "def _normalise_programme_id(",
    "def _text_mentions_multiple_programmes(",
    "def _serve_pending_continuation(",
    "def _update_conversation_state(",
    "def _invoke_streaming(",
    "def query(",
    "def _query_lead(",
]


def fail(msg: str) -> None:
    print(f"ABORT (nothing written): {msg}")
    sys.exit(1)


def find_once(src: str, marker: str, label: str) -> int:
    count = src.count(marker)
    if count != 1:
        fail(f"anchor '{label}' found {count} times (expected exactly 1)")
    return src.index(marker)


def back_up_over_decorators(src: str, end: int) -> int:
    """Move `end` back so decorator lines directly above the kept def stay attached to it."""
    while True:
        line_start = src.rfind("\n", 0, end - 1) + 1
        line = src[line_start:end]
        if line.strip().startswith("@"):
            end = line_start
        else:
            return end


def main() -> int:
    check_only = "--check" in sys.argv
    path = os.path.abspath(TARGET)
    with open(path, encoding="utf-8") as f:
        src = f.read()
    original_lines = src.count("\n")

    for start_marker, end_marker in DELETE_RANGES:
        start = find_once(src, start_marker, start_marker.strip()[:50])
        end_abs = src.index(end_marker, start)
        if src.count(end_marker) != 1:
            fail(f"end anchor '{end_marker.strip()[:50]}' not unique")
        end_abs = back_up_over_decorators(src, end_abs)
        if end_abs <= start:
            fail(f"range for '{start_marker.strip()[:50]}' is empty or inverted")
        src = src[:start] + src[end_abs:]

    for line in REMOVE_LINES:
        if src.count(line) != 1:
            fail(f"import line not found exactly once: {line.strip()}")
        src = src.replace(line, "")

    for old, new in REPLACEMENTS:
        if src.count(old) != 1:
            fail(f"replacement block not found exactly once: {old.splitlines()[0]}")
        src = src.replace(old, new)

    for name in FORBIDDEN_AFTER:
        if name in src:
            fail(f"'{name}' still present after deletion — anchors need adjustment")

    for name in REQUIRED_AFTER:
        if name not in src:
            fail(f"required '{name}' was deleted — anchors need adjustment")

    try:
        compile(src, path, "exec")
    except SyntaxError as e:
        fail(f"result does not compile: {e}")

    new_lines = src.count("\n")
    print(f"OK: {original_lines} -> {new_lines} lines (-{original_lines - new_lines})")

    if check_only:
        print("Dry run only, file unchanged.")
        return 0

    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"Wrote {path}")
    print("Next: pytest tests/test_verified_facts.py tests/test_stream_parser.py -v")
    return 0


if __name__ == "__main__":
    sys.exit(main())

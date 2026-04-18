#!/usr/bin/env python3
"""
Collect bot responses for an accuracy test catalog.

What it does
------------
- reads a CSV catalog with at least: id, language, program, question
- disables cache by default via Cache.configure(mode="dict", no_cache=True)
- runs each question against ExecutiveAgentChain directly
- stores responses and metadata in a results CSV

Default behavior
----------------
- one fresh ExecutiveAgentChain session per row
- preserves original catalog columns in the output
- appends response metadata columns

Example
-------
python tools/accuracy_test.py \
  --catalog docs/accuracy_test_catalog.csv \
  --output docs/accuracy_test_results.csv

Optional grouped multi-turn mode
--------------------------------
If your catalog includes:
- conversation_id
- turn_index

you can pass:
--session-mode grouped

Then rows with the same conversation_id will share one agent session and
be processed in ascending turn_index order. This is useful for testing
language locking or multi-turn state behavior.
"""

from __future__ import annotations

import argparse
import csv
import os
import subprocess
import sys
import time
import traceback
import uuid
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


@dataclass
class RunResult:
    bot_response: str
    processed_query: str
    response_language: str
    confidence_fallback: bool
    should_cache: bool
    appointment_requested: bool
    relevant_programs: str
    status: str
    error_message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect bot responses for an accuracy test catalog.")
    parser.add_argument(
        "--catalog",
        default="docs/accuracy_test_catalog.csv",
        help="Path to the input CSV catalog relative to repo root.",
    )
    parser.add_argument(
        "--output",
        default="docs/accuracy_test_results.csv",
        help="Path to the output CSV results relative to repo root.",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Path to the HSG_RAG repository root.",
    )
    parser.add_argument(
        "--cache-mode",
        default="dict",
        choices=["dict", "local", "cloud"],
        help="Cache mode passed to Cache.configure.",
    )
    parser.add_argument(
        "--use-cache",
        action="store_true",
        help="Enable cache. By default the script disables caching.",
    )
    parser.add_argument(
        "--session-mode",
        default="isolated",
        choices=["isolated", "grouped"],
        help=(
            "isolated: fresh session per row. "
            "grouped: reuse session per conversation_id (requires conversation_id column; "
            "turns sorted by turn_index if present)."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Optional max number of rows to process (0 = all).",
    )
    parser.add_argument(
        "--sleep-seconds",
        type=float,
        default=0.0,
        help="Optional pause between requests.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite the output file if it exists. Otherwise the script aborts.",
    )
    parser.add_argument(
        "--disable-profile-tracking",
        action="store_true",
        help="Best effort: disable user profile tracking during the run to avoid extra profile logs.",
    )
    return parser.parse_args()


def repo_abspath(repo_root: str, relative_path: str) -> Path:
    return (Path(repo_root).resolve() / relative_path).resolve()


def ensure_import_path(repo_root: Path) -> None:
    repo_str = str(repo_root)
    if repo_str not in sys.path:
        sys.path.insert(0, repo_str)


def get_git_commit(repo_root: Path) -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return ""


def load_catalog(path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = reader.fieldnames or []
    if not rows:
        raise ValueError(f"Catalog is empty: {path}")
    required = {"id", "language", "program", "question"}
    missing = required - set(fieldnames)
    if missing:
        raise ValueError(f"Catalog is missing required columns: {sorted(missing)}")
    return rows, fieldnames


def maybe_sort_grouped_rows(rows: List[Dict[str, str]]) -> List[Dict[str, str]]:
    def turn_key(row: Dict[str, str]) -> Tuple[str, int, int]:
        conv = row.get("conversation_id", "")
        turn_raw = row.get("turn_index", "")
        try:
            turn = int(turn_raw)
        except Exception:
            turn = 0
        try:
            row_id = int(row.get("id", "0"))
        except Exception:
            row_id = 0
        return conv, turn, row_id

    return sorted(rows, key=turn_key)


def configure_runtime(repo_root: Path, cache_mode: str, use_cache: bool, disable_profile_tracking: bool) -> None:
    # imports happen after sys.path is adjusted
    from src.cache.cache import Cache
    from src.config import config

    Cache.configure(mode=cache_mode, no_cache=not use_cache)

    if disable_profile_tracking:
        # Best effort only; the config object shape comes from the repo's config system.
        try:
            config.convstate.TRACK_USER_PROFILE = False
        except Exception:
            pass


def make_agent(language: str, session_id: str):
    from src.rag.agent_chain import ExecutiveAgentChain
    return ExecutiveAgentChain(language=language, session_id=session_id)


def run_single_question(agent, question: str) -> RunResult:
    pre = agent.preprocess_query(question)

    if pre.response is not None:
        return RunResult(
            bot_response=pre.response,
            processed_query=pre.processed_query or question,
            response_language=pre.language,
            confidence_fallback=getattr(pre, "confidence_fallback", False),
            should_cache=getattr(pre, "should_cache", False),
            appointment_requested=getattr(pre, "appointment_requested", False),
            relevant_programs="|".join(getattr(pre, "relevant_programs", []) or []),
            status="preprocess_returned_response",
            error_message="",
        )

    final = agent.agent_query(pre.processed_query)

    return RunResult(
        bot_response=final.response,
        processed_query=final.processed_query or pre.processed_query or question,
        response_language=final.language,
        confidence_fallback=getattr(final, "confidence_fallback", False),
        should_cache=getattr(final, "should_cache", False),
        appointment_requested=getattr(final, "appointment_requested", False),
        relevant_programs="|".join(getattr(final, "relevant_programs", []) or []),
        status="ok",
        error_message="",
    )


def build_output_fieldnames(input_fieldnames: List[str]) -> List[str]:
    extra = [
        "bot_response",
        "processed_query",
        "response_language",
        "confidence_fallback",
        "should_cache",
        "appointment_requested",
        "relevant_programs",
        "run_status",
        "error_message",
        "session_mode",
        "session_id",
        "model",
        "commit_hash",
        "cache_mode",
        "cache_enabled",
        "tested_at_epoch",
    ]
    return input_fieldnames + extra


def write_results(path: Path, fieldnames: List[str], rows: Iterable[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    ensure_import_path(repo_root)

    catalog_path = repo_abspath(args.repo_root, args.catalog)
    output_path = repo_abspath(args.repo_root, args.output)

    if output_path.exists() and not args.overwrite:
        print(
            f"Refusing to overwrite existing output file: {output_path}\n"
            f"Use --overwrite to replace it.",
            file=sys.stderr,
        )
        return 2

    input_rows, input_fieldnames = load_catalog(catalog_path)
    if args.limit and args.limit > 0:
        input_rows = input_rows[: args.limit]

    if args.session_mode == "grouped":
        if "conversation_id" not in input_fieldnames:
            raise ValueError(
                "session-mode=grouped requires a conversation_id column in the catalog."
            )
        input_rows = maybe_sort_grouped_rows(input_rows)

    configure_runtime(
        repo_root=repo_root,
        cache_mode=args.cache_mode,
        use_cache=args.use_cache,
        disable_profile_tracking=args.disable_profile_tracking,
    )

    commit_hash = get_git_commit(repo_root)

    # Import config after import path + runtime config are ready
    from src.config import config

    try:
        model_name = getattr(config.llm, "OPENAI_MODEL")
    except Exception:
        model_name = getattr(config, "get", lambda *_: "")("OPENAI_MODEL", "")

    output_fieldnames = build_output_fieldnames(input_fieldnames)
    output_rows: List[Dict[str, Any]] = []

    grouped_agents: Dict[str, Any] = {}
    total = len(input_rows)

    for idx, row in enumerate(input_rows, start=1):
        lang = row.get("language", "en") or "en"
        question = row["question"]

        if args.session_mode == "grouped":
            session_id = row.get("conversation_id") or f"group_{uuid.uuid4()}"
            if session_id not in grouped_agents:
                grouped_agents[session_id] = make_agent(language=lang, session_id=session_id)
            agent = grouped_agents[session_id]
        else:
            session_id = f"isolated_{row.get('id', idx)}_{uuid.uuid4().hex[:8]}"
            agent = make_agent(language=lang, session_id=session_id)

        print(f"[{idx}/{total}] {row.get('id', '')} {lang} {row.get('program', '')}: {question}")

        try:
            result = run_single_question(agent=agent, question=question)
        except Exception as exc:
            result = RunResult(
                bot_response="",
                processed_query="",
                response_language=lang,
                confidence_fallback=False,
                should_cache=False,
                appointment_requested=False,
                relevant_programs="",
                status="exception",
                error_message=f"{type(exc).__name__}: {exc}",
            )
            traceback.print_exc()

        out_row = dict(row)
        out_row.update(
            {
                "bot_response": result.bot_response,
                "processed_query": result.processed_query,
                "response_language": result.response_language,
                "confidence_fallback": str(result.confidence_fallback),
                "should_cache": str(result.should_cache),
                "appointment_requested": str(result.appointment_requested),
                "relevant_programs": result.relevant_programs,
                "run_status": result.status,
                "error_message": result.error_message,
                "session_mode": args.session_mode,
                "session_id": session_id,
                "model": model_name,
                "commit_hash": commit_hash,
                "cache_mode": args.cache_mode,
                "cache_enabled": str(args.use_cache),
                "tested_at_epoch": str(int(time.time())),
            }
        )
        output_rows.append(out_row)

        if args.sleep_seconds > 0:
            time.sleep(args.sleep_seconds)

    write_results(output_path, output_fieldnames, output_rows)

    ok = sum(1 for r in output_rows if r["run_status"] == "ok")
    pre = sum(1 for r in output_rows if r["run_status"] == "preprocess_returned_response")
    exc = sum(1 for r in output_rows if r["run_status"] == "exception")

    print("\nDone.")
    print(f"Output: {output_path}")
    print(f"Rows written: {len(output_rows)}")
    print(f"ok: {ok}")
    print(f"preprocess_returned_response: {pre}")
    print(f"exception: {exc}")
    print(f"Cache enabled: {args.use_cache}")
    print(f"Cache mode: {args.cache_mode}")
    print(f"Commit hash: {commit_hash or 'n/a'}")
    print(f"Model: {model_name or 'n/a'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

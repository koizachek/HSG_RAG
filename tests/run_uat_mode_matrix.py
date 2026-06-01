from __future__ import annotations

import argparse
import csv
import json
import re
import tempfile
import time
from pathlib import Path

import test_uat_branch_comparison as uat


MODES = [
    {
        "id": "01_naked_rag",
        "name": "Naked RAG",
        "programme_facts": False,
        "deterministic_responses": False,
        "description": "programme_facts OFF; deterministic responses OFF",
    },
    {
        "id": "02_rag_plus_programme_facts",
        "name": "RAG + programme_facts",
        "programme_facts": True,
        "deterministic_responses": False,
        "description": "programme_facts ON; deterministic responses OFF",
    },
    {
        "id": "03_rag_plus_deterministic",
        "name": "RAG + deterministic",
        "programme_facts": False,
        "deterministic_responses": True,
        "description": "programme_facts OFF; deterministic responses ON",
    },
    {
        "id": "04_full_system",
        "name": "Full system",
        "programme_facts": True,
        "deterministic_responses": True,
        "description": "programme_facts ON; deterministic responses ON",
    },
]


def _bool_literal(value: bool) -> str:
    return "True" if value else "False"


def patch_config_flags(worktree: Path, programme_facts: bool, deterministic_responses: bool) -> None:
    config_path = worktree / "config.py"
    text = config_path.read_text(encoding="utf-8")
    text = re.sub(
        r"^USE_PROGRAMME_FACTS\s*=\s*(?:True|False)\s*$",
        f"USE_PROGRAMME_FACTS = {_bool_literal(programme_facts)}",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^USE_DETERMINISTIC_RESPONSES\s*=\s*(?:True|False)\s*$",
        f"USE_DETERMINISTIC_RESPONSES = {_bool_literal(deterministic_responses)}",
        text,
        flags=re.MULTILINE,
    )
    config_path.write_text(text, encoding="utf-8")


def add_mode_payload(result: dict, mode: dict) -> None:
    result["mode"] = {
        "id": mode["id"],
        "name": mode["name"],
        "programme_facts": mode["programme_facts"],
        "deterministic_responses": mode["deterministic_responses"],
        "description": mode["description"],
    }


def metric_int(item: dict, key: str) -> int:
    return int(item["branch_result"].get("metrics", {}).get(key, 0) or 0)


def programme_facts_usage(item: dict) -> int:
    return metric_int(item, "programme_facts_lookup_calls") + metric_int(
        item, "programme_facts_many_lookup_calls"
    )


def avg_retrieved_docs(item: dict) -> float:
    counts = item["branch_result"].get("metrics", {}).get("retrieved_document_counts") or []
    return sum(float(value) for value in counts) / len(counts) if counts else 0.0


def summarize_mode(mode: dict, results: list[dict], naked: dict | None = None) -> dict:
    llm_scores = [
        float(item.get("llm_judge", {}).get("overall_score"))
        for item in results
        if isinstance(item.get("llm_judge", {}).get("overall_score"), (int, float))
    ]
    heuristic_scores = [
        float(item["heuristic"].get("score"))
        for item in results
        if isinstance(item["heuristic"].get("score"), (int, float))
    ]
    elapsed = [float(item["branch_result"].get("elapsed_s") or 0) for item in results]
    failed_cases = [
        item["case"]["case_id"]
        for item in results
        if item.get("llm_judge", {}).get("passed") is False
    ]
    retrieved_counts = [
        float(count)
        for item in results
        for count in (item["branch_result"].get("metrics", {}).get("retrieved_document_counts") or [])
    ]
    summary = {
        "mode_id": mode["id"],
        "mode_name": mode["name"],
        "programme_facts": mode["programme_facts"],
        "deterministic_responses": mode["deterministic_responses"],
        "description": mode["description"],
        "avg_llm_score": sum(llm_scores) / len(llm_scores) if llm_scores else None,
        "avg_heuristic_score": sum(heuristic_scores) / len(heuristic_scores) if heuristic_scores else None,
        "avg_runtime_s": sum(elapsed) / len(elapsed) if elapsed else 0,
        "case_count": len(results),
        "failed_case_count": len(failed_cases),
        "failed_cases": failed_cases,
        "runner_errors": [
            item["case"]["case_id"]
            for item in results
            if item["branch_result"].get("runner_error")
        ],
        "judge_errors": [
            item["case"]["case_id"]
            for item in results
            if item.get("llm_judge", {}).get("judge_error")
        ],
        "lead_agent_model_calls": sum(metric_int(item, "lead_agent_model_calls") for item in results),
        "retrieve_context_calls": sum(metric_int(item, "retrieve_context_calls") for item in results),
        "retrieve_context_via_tool_calls": sum(metric_int(item, "retrieve_context_via_tool_calls") for item in results),
        "programme_facts_usage_count": sum(programme_facts_usage(item) for item in results),
        "programme_facts_final_answer_calls": sum(metric_int(item, "programme_facts_final_answer_calls") for item in results),
        "deterministic_answer_count": sum(metric_int(item, "deterministic_answer_calls") for item in results),
        "final_answer_without_llm_count": sum(metric_int(item, "final_answer_without_llm_calls") for item in results),
        "weaviate_query_count": sum(metric_int(item, "weaviate_query_calls") for item in results),
        "retrieved_document_count": sum(metric_int(item, "retrieved_document_count") for item in results),
        "avg_retrieved_documents": sum(retrieved_counts) / len(retrieved_counts) if retrieved_counts else 0,
        "model_calls": sum(metric_int(item, "model_calls") for item in results),
        "tool_calls_total": sum(
            sum((item["branch_result"].get("metrics", {}).get("tool_calls", {}) or {}).values())
            for item in results
        ),
    }
    if naked:
        summary["delta_llm_vs_naked"] = (
            summary["avg_llm_score"] - naked["avg_llm_score"]
            if summary["avg_llm_score"] is not None and naked.get("avg_llm_score") is not None
            else None
        )
        summary["delta_heuristic_vs_naked"] = (
            summary["avg_heuristic_score"] - naked["avg_heuristic_score"]
            if summary["avg_heuristic_score"] is not None and naked.get("avg_heuristic_score") is not None
            else None
        )
        summary["delta_runtime_vs_naked_s"] = summary["avg_runtime_s"] - naked["avg_runtime_s"]
    return summary


def write_summary_csv(path: Path, summaries: list[dict]) -> None:
    fieldnames = [
        "mode_id",
        "mode_name",
        "programme_facts",
        "deterministic_responses",
        "avg_llm_score",
        "avg_heuristic_score",
        "avg_runtime_s",
        "failed_case_count",
        "failed_cases",
        "lead_agent_model_calls",
        "retrieve_context_calls",
        "programme_facts_usage_count",
        "deterministic_answer_count",
        "weaviate_query_count",
        "avg_retrieved_documents",
        "model_calls",
        "tool_calls_total",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for summary in summaries:
            row = {key: summary.get(key) for key in fieldnames}
            row["failed_cases"] = ", ".join(summary.get("failed_cases", []))
            writer.writerow(row)


def write_cases_csv(path: Path, results: list[dict]) -> None:
    fieldnames = [
        "mode_id",
        "mode_name",
        "case_id",
        "heuristic_score",
        "llm_score",
        "llm_passed",
        "runtime_s",
        "lead_agent_model_calls",
        "retrieve_context_calls",
        "programme_facts_usage_count",
        "programme_facts_final_answer_calls",
        "deterministic_answer_count",
        "final_answer_without_llm_count",
        "weaviate_query_count",
        "avg_retrieved_documents",
        "runner_error",
        "llm_verdict",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in results:
            mode = item["mode"]
            writer.writerow(
                {
                    "mode_id": mode["id"],
                    "mode_name": mode["name"],
                    "case_id": item["case"]["case_id"],
                    "heuristic_score": item["heuristic"].get("score"),
                    "llm_score": item.get("llm_judge", {}).get("overall_score"),
                    "llm_passed": item.get("llm_judge", {}).get("passed"),
                    "runtime_s": item["branch_result"].get("elapsed_s"),
                    "lead_agent_model_calls": metric_int(item, "lead_agent_model_calls"),
                    "retrieve_context_calls": metric_int(item, "retrieve_context_calls"),
                    "programme_facts_usage_count": programme_facts_usage(item),
                    "programme_facts_final_answer_calls": metric_int(item, "programme_facts_final_answer_calls"),
                    "deterministic_answer_count": metric_int(item, "deterministic_answer_calls"),
                    "final_answer_without_llm_count": metric_int(item, "final_answer_without_llm_calls"),
                    "weaviate_query_count": metric_int(item, "weaviate_query_calls"),
                    "avg_retrieved_documents": f"{avg_retrieved_docs(item):.2f}",
                    "runner_error": item["branch_result"].get("runner_error", ""),
                    "llm_verdict": item.get("llm_judge", {}).get("verdict", ""),
                }
            )


def write_svg_bar_chart(path: Path, title: str, rows: list[tuple[str, float]], suffix: str = "") -> None:
    width = 980
    bar_height = 28
    gap = 16
    left = 260
    top = 56
    max_value = max((value for _, value in rows), default=1) or 1
    height = top + len(rows) * (bar_height + gap) + 28
    chart_width = width - left - 120
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<style>text{font-family:Arial,sans-serif;font-size:13px;fill:#111827}.title{font-size:18px;font-weight:700}.bar{fill:#2563eb}.axis{stroke:#d1d5db;stroke-width:1}</style>',
        f'<text class="title" x="20" y="28">{title}</text>',
        f'<line class="axis" x1="{left}" y1="{top - 10}" x2="{left}" y2="{height - 24}"/>',
    ]
    for index, (label, value) in enumerate(rows):
        y = top + index * (bar_height + gap)
        bar_width = chart_width * value / max_value if max_value else 0
        parts.append(f'<text x="20" y="{y + 19}">{label}</text>')
        parts.append(f'<rect class="bar" x="{left}" y="{y}" width="{bar_width:.1f}" height="{bar_height}" rx="3"/>')
        parts.append(f'<text x="{left + bar_width + 8:.1f}" y="{y + 19}">{value:.2f}{suffix}</text>')
    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")


def write_matrix_report(path: Path, output_dir: Path, summaries: list[dict]) -> None:
    def fmt_float(value: float | None, digits: int = 2) -> str:
        return "n/a" if value is None else f"{value:.{digits}f}"

    lines = [
        "# UAT Architecture Mode Matrix Report",
        "",
        f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"Output directory: `{output_dir}`",
        "",
        "## Modes",
        "",
    ]
    for mode in MODES:
        lines.append(f"- `{mode['id']}`: {mode['name']} ({mode['description']})")

    lines.extend(
        [
            "",
            "## Summary",
            "",
            "| Mode | Avg LLM | Avg Heuristic | Avg Runtime | Failed | Lead-Agent Calls | retrieve_context | programme_facts | Deterministic Answers | Weaviate Queries | Avg Docs |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for summary in summaries:
        lines.append(
            f"| {summary['mode_name']} | {fmt_float(summary['avg_llm_score'])} | "
            f"{fmt_float(summary['avg_heuristic_score'], 3)} | {summary['avg_runtime_s']:.2f}s | "
            f"{summary['failed_case_count']} | {summary['lead_agent_model_calls']} | "
            f"{summary['retrieve_context_calls']} | {summary['programme_facts_usage_count']} | "
            f"{summary['deterministic_answer_count']} | {summary['weaviate_query_count']} | "
            f"{summary['avg_retrieved_documents']:.2f} |"
        )

    best_llm = max(summaries, key=lambda item: item["avg_llm_score"] or 0)
    best_heuristic = max(summaries, key=lambda item: item["avg_heuristic_score"] or 0)
    lines.extend(
        [
            "",
            f"Best by average LLM score: `{best_llm['mode_id']}` ({best_llm['mode_name']}) with {fmt_float(best_llm['avg_llm_score'])}.",
            f"Best by average heuristic score: `{best_heuristic['mode_id']}` ({best_heuristic['mode_name']}) with {fmt_float(best_heuristic['avg_heuristic_score'], 3)}.",
            "",
            "## Failed Cases",
            "",
        ]
    )
    for summary in summaries:
        failed = ", ".join(summary["failed_cases"]) if summary["failed_cases"] else "None"
        lines.append(f"- `{summary['mode_id']}`: {failed}")

    lines.extend(
        [
            "",
            "## Path Usage Breakdown",
            "",
        ]
    )
    for summary in summaries:
        lines.append(
            f"- `{summary['mode_id']}`: lead_agent={summary['lead_agent_model_calls']}, "
            f"retrieve_context={summary['retrieve_context_calls']}, "
            f"programme_facts={summary['programme_facts_usage_count']}, "
            f"programme_fact_answers={summary['programme_facts_final_answer_calls']}, "
            f"deterministic_answers={summary['deterministic_answer_count']}, "
            f"final_without_llm={summary['final_answer_without_llm_count']}, "
            f"weaviate_queries={summary['weaviate_query_count']}, "
            f"avg_retrieved_docs={summary['avg_retrieved_documents']:.2f}, "
            f"model_calls={summary['model_calls']}, tool_calls={summary['tool_calls_total']}"
        )

    lines.extend(
        [
            "",
            "## Graphs",
            "",
            "- [Average LLM score](graph_avg_llm_score.svg)",
            "- [Average heuristic score](graph_avg_heuristic_score.svg)",
            "- [Average runtime](graph_avg_runtime.svg)",
            "- [Path usage](graph_path_usage.svg)",
            "- [Weaviate queries](graph_weaviate_queries.svg)",
            "- [Average retrieved documents](graph_avg_retrieved_documents.svg)",
            "",
            "## Files",
            "",
            "- Matrix summary JSON: `uat_mode_matrix_summary.json`",
            "- Matrix summary CSV: `uat_mode_matrix_summary.csv`",
            "- Per-case CSV: `uat_mode_matrix_cases.csv`",
            "- Raw branch comparison JSON/CSV files: `uat_branch_comparison_*.json`, `uat_branch_comparison_*.csv`",
            "- Turn timing files: `uat_branch_turns_*.csv`",
            "- LLM judge summary: `uat_llm_judge_summary_*.md`",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def write_outputs(output_dir: Path, summaries: list[dict], results: list[dict]) -> None:
    (output_dir / "uat_mode_matrix_summary.json").write_text(
        json.dumps({"modes": MODES, "summary": summaries}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_summary_csv(output_dir / "uat_mode_matrix_summary.csv", summaries)
    write_cases_csv(output_dir / "uat_mode_matrix_cases.csv", results)
    write_matrix_report(output_dir / "uat_mode_matrix_report.md", output_dir, summaries)
    write_svg_bar_chart(
        output_dir / "graph_avg_llm_score.svg",
        "Average LLM Score",
        [(summary["mode_name"], float(summary["avg_llm_score"] or 0)) for summary in summaries],
    )
    write_svg_bar_chart(
        output_dir / "graph_avg_heuristic_score.svg",
        "Average Heuristic Score",
        [(summary["mode_name"], float(summary["avg_heuristic_score"] or 0)) for summary in summaries],
    )
    write_svg_bar_chart(
        output_dir / "graph_avg_runtime.svg",
        "Average Runtime",
        [(summary["mode_name"], float(summary["avg_runtime_s"] or 0)) for summary in summaries],
        "s",
    )
    path_rows = []
    for summary in summaries:
        path_rows.extend(
            [
                (f"{summary['mode_name']} lead", float(summary["lead_agent_model_calls"])),
                (f"{summary['mode_name']} retrieve", float(summary["retrieve_context_calls"])),
                (f"{summary['mode_name']} facts", float(summary["programme_facts_usage_count"])),
                (f"{summary['mode_name']} deterministic", float(summary["deterministic_answer_count"])),
            ]
        )
    write_svg_bar_chart(output_dir / "graph_path_usage.svg", "Path Usage Counts", path_rows)
    write_svg_bar_chart(
        output_dir / "graph_weaviate_queries.svg",
        "Weaviate Query Count",
        [(summary["mode_name"], float(summary["weaviate_query_count"])) for summary in summaries],
    )
    write_svg_bar_chart(
        output_dir / "graph_avg_retrieved_documents.svg",
        "Average Retrieved Documents per Weaviate Query",
        [(summary["mode_name"], float(summary["avg_retrieved_documents"])) for summary in summaries],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run UAT across the four chatbot architecture modes.")
    parser.add_argument("--repo-root", type=Path, default=uat.DEFAULT_REPO_ROOT)
    parser.add_argument("--excel", type=Path, default=uat.DEFAULT_EXCEL)
    parser.add_argument("--branch-ref", default="chatbot-decoupling")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--timeout-s", type=int, default=300)
    parser.add_argument("--llm-judge", action="store_true")
    parser.add_argument("--judge-model", default=uat.DEFAULT_JUDGE_MODEL)
    parser.add_argument("--judge-timeout-s", type=int, default=120)
    parser.add_argument("--limit", type=int, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir or args.repo_root / "data" / "uat_mode_matrix" / stamp
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_dir = output_dir / "traces"
    trace_dir.mkdir(parents=True, exist_ok=True)
    event_log_path = trace_dir / f"uat_mode_matrix_events_{stamp}.jsonl"
    env_overrides = uat.load_env_file(args.repo_root / ".env")
    cases = uat.parse_uat_excel(args.excel)
    if args.limit:
        cases = cases[: args.limit]

    print(f"Starting UAT mode matrix: cases={len(cases)} modes={len(MODES)}", flush=True)
    print(f"Output directory: {output_dir}", flush=True)
    print(f"Event trace log: {event_log_path}", flush=True)

    all_results: list[dict] = []
    with tempfile.TemporaryDirectory(prefix="hsg-rag-mode-matrix-") as tmp:
        worktree_root = Path(tmp)
        for mode in MODES:
            mode_worktree = worktree_root / mode["id"]
            result = uat.run_cmd(
                ["git", "worktree", "add", "--detach", str(mode_worktree), args.branch_ref],
                cwd=args.repo_root,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to create worktree for {mode['id']}:\n{result.stderr}")
            patch_config_flags(
                mode_worktree,
                programme_facts=mode["programme_facts"],
                deterministic_responses=mode["deterministic_responses"],
            )
            print(f"Ready mode {mode['id']}: {mode['description']}", flush=True)

            for case_index, case in enumerate(cases, start=1):
                started = time.perf_counter()
                print(f"[{mode['id']} {case_index}/{len(cases)}] START {case.case_id}", flush=True)
                branch_result = uat.run_case_in_branch(
                    mode_worktree,
                    case,
                    timeout_s=args.timeout_s,
                    env_overrides=env_overrides,
                    branch_id=mode["id"],
                    branch_ref=f"{args.branch_ref}:{mode['id']}",
                    event_log_path=event_log_path,
                )
                heuristic = uat.evaluate_heuristics(case, branch_result)
                elapsed = time.perf_counter() - started
                status = "ERROR" if branch_result.get("runner_error") else "OK"
                metrics = branch_result.get("metrics", {})
                print(
                    f"[{mode['id']} {case_index}/{len(cases)}] END {case.case_id} "
                    f"status={status} elapsed_s={elapsed:.1f} heuristic={heuristic.get('score')} "
                    f"lead={metrics.get('lead_agent_model_calls', 0)} "
                    f"retrieve={metrics.get('retrieve_context_calls', 0)} "
                    f"facts={metrics.get('programme_facts_lookup_calls', 0) + metrics.get('programme_facts_many_lookup_calls', 0)} "
                    f"deterministic={metrics.get('deterministic_answer_calls', 0)} "
                    f"weaviate={metrics.get('weaviate_query_calls', 0)}",
                    flush=True,
                )
                error_preview = uat.format_error_preview(branch_result.get("runner_error"))
                if error_preview:
                    print(error_preview, flush=True)
                item = {
                    "branch_id": mode["id"],
                    "branch_ref": f"{args.branch_ref}:{mode['id']}",
                    "case": case.to_payload(),
                    "branch_result": branch_result,
                    "heuristic": heuristic,
                }
                add_mode_payload(item, mode)
                all_results.append(item)

    raw_json, raw_csv, turns_csv = uat.write_reports(all_results, output_dir)
    print(f"Raw JSON report: {raw_json}", flush=True)
    print(f"Raw CSV report: {raw_csv}", flush=True)
    print(f"Turn timing CSV report: {turns_csv}", flush=True)

    if args.llm_judge:
        print("Starting LLM judge...", flush=True)
        all_results = uat.add_llm_judgements(
            results=all_results,
            repo_root=args.repo_root,
            model=args.judge_model,
            timeout_s=args.judge_timeout_s,
        )
        raw_json, raw_csv, turns_csv = uat.write_reports(all_results, output_dir)
        summary_path = uat.write_llm_summary(all_results, output_dir)
        print(f"LLM judge JSON report: {raw_json}", flush=True)
        print(f"LLM judge CSV report: {raw_csv}", flush=True)
        print(f"Turn timing CSV report: {turns_csv}", flush=True)
        print(f"LLM judge summary: {summary_path}", flush=True)

    summaries = []
    naked_summary = None
    for mode in MODES:
        mode_results = [item for item in all_results if item["mode"]["id"] == mode["id"]]
        summary = summarize_mode(mode, mode_results, naked=naked_summary)
        if mode["id"] == "01_naked_rag":
            naked_summary = summary
        elif naked_summary:
            summary = summarize_mode(mode, mode_results, naked=naked_summary)
        summaries.append(summary)

    write_outputs(output_dir, summaries, all_results)
    print(f"Matrix report: {output_dir / 'uat_mode_matrix_report.md'}", flush=True)
    uat.print_summary(all_results, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

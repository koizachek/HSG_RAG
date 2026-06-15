"""Send a GitHub Actions failure alert through the project notification center."""

from __future__ import annotations

import os
import sys


def _env(name: str, default: str = "unknown") -> str:
    value = os.getenv(name)
    return value if value else default


def _run_url() -> str:
    server_url = _env("GITHUB_SERVER_URL", "https://github.com")
    repository = _env("GITHUB_REPOSITORY")
    run_id = _env("GITHUB_RUN_ID")
    return f"{server_url}/{repository}/actions/runs/{run_id}"


def _short_sha() -> str:
    sha = _env("GITHUB_SHA")
    return sha[:12] if sha != "unknown" else sha


def build_subject() -> str:
    return f"GitHub Actions failure: {_env('GITHUB_WORKFLOW', 'workflow')}"


def build_body() -> str:
    return "\n".join(
        [
            "The scraping workflow failed.",
            "",
            f"Workflow: {_env('GITHUB_WORKFLOW')}",
            f"Job: {_env('GITHUB_JOB')}",
            f"Failing context: {_env('SCRAPE_FAILED_STEP', 'see linked run logs')}",
            f"Command: {_env('SCRAPE_COMMAND', 'unknown')}",
            f"Exit code: {_env('SCRAPE_EXIT_CODE', 'unknown')}",
            f"Run: {_run_url()}",
            f"Run attempt: {_env('GITHUB_RUN_ATTEMPT')}",
            f"Event: {_env('GITHUB_EVENT_NAME')}",
            f"Branch/ref: {_env('GITHUB_REF')}",
            f"Ref name: {_env('GITHUB_REF_NAME')}",
            f"Commit SHA: {_env('GITHUB_SHA')}",
            f"Commit short SHA: {_short_sha()}",
            "",
            "Short error message: the scrape command exited unsuccessfully. "
            "Open the run URL above for the full, masked GitHub Actions logs.",
        ]
    )


def main() -> int:
    try:
        from src.notification.notification_center import NotificationCenter

        NotificationCenter().send_notification(
            subject=build_subject(),
            body=build_body(),
            channel="email",
        )
        print("Failure notification sent.")
    except Exception as exc:
        print(f"Warning: could not send failure notification: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

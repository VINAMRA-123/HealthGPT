"""Latency report (p50 / p90 / p95 / p99) from real LangSmith traces.

Usage (needs LANGSMITH_API_KEY; the project defaults to "healthgpt"):

    python -m evals.latency_report --days 7
    python -m evals.latency_report --days 30 --json

Runs are grouped by the tags added in app/ai/tracing.py:
path:sql (database answer), path:llm (Gemini), path:guardrail (refused).
Only root runs named "healthgpt_chat" are counted.
"""
from dotenv import load_dotenv

load_dotenv()
import argparse
import json
import os
from datetime import datetime, timedelta, timezone

from app.observability import summarize



import asyncio

async def fetch_latencies(project: str, days: int, limit: int):
    from langsmith import Client

    client = Client()
    since = datetime.now(timezone.utc) - timedelta(days=days)

    groups = {"all": []}
    errors = 0

    project_info = await client.aread_project(project_name=project)

    runs = client.runs.query(
        project_ids=[str(project_info.id)],
        is_root=True,
        filter='eq(name, "healthgpt_chat")',
        min_start_time=since,
        selects=[
            "ID",
            "NAME",
            "START_TIME",
            "END_TIME",
            "ERROR",
            "TAGS",
        ],
    )

    count = 0

    async for run in runs:
        if not run.start_time or not run.end_time:
            continue

        if run.error:
            errors += 1

        milliseconds = (
            run.end_time - run.start_time
        ).total_seconds() * 1000

        groups["all"].append(milliseconds)

        for tag in run.tags or []:
            if tag.startswith("path:"):
                groups.setdefault(tag, []).append(milliseconds)

        count += 1
        if count >= limit:
            break

    groups["_errors"] = [float(errors)]
    return groups


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", default=os.getenv("LANGSMITH_PROJECT", "healthgpt"))
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=5000)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    groups = asyncio.run(
    fetch_latencies(args.project, args.days, args.limit)
)
    errors = int(groups.pop("_errors", [0.0])[0])
    report = {name: summarize(values) for name, values in sorted(groups.items())}

    if args.json:
        print(json.dumps({"errors": errors, "latency_ms": report}, indent=2))
        return

    print(f"Project: {args.project}  window: last {args.days} days  errors: {errors}")
    print(f"{'group':<16}{'n':>6}{'mean':>8}{'p50':>8}{'p90':>8}{'p95':>8}{'p99':>8}{'max':>8}")

    for name, row in report.items():
        if row["count"] == 0:
            continue

        print(
            f"{name:<16}{row['count']:>6}{row['mean']:>8}{row['p50']:>8}"
            f"{row['p90']:>8}{row['p95']:>8}{row['p99']:>8}{row['max']:>8}"
        )

    print("\nAll latencies are in milliseconds.")


if __name__ == "__main__":
    main()

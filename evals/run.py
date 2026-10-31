"""Run the scenarios against the configured model and report pass rates.

    python -m evals.run
    python -m evals.run --only pricing,data_leak
    python -m evals.run --save
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from emporio_agent.agent import ServiceAgent
from emporio_agent.clock import StoreClock
from emporio_agent.config import ROOT, ConfigError, load_settings
from emporio_agent.llm import build_llm
from emporio_agent.policies import PolicyBook
from emporio_agent.storage import Storage
from emporio_agent.store_data import StoreData

from .cases import CASES, CRITICAL_GROUPS, Case

REPORTS_DIR = ROOT / "evals" / "reports"


def evaluate(case: Case, reply: str, tools_used: set[str]) -> list[str]:
    failures = [f"tool not used: {t}" for t in case.tools if t not in tools_used]
    failures += [f"missing: {p}" for p in case.include if not re.search(p, reply, re.IGNORECASE)]
    failures += [f"forbidden: {p}" for p in case.exclude if re.search(p, reply, re.IGNORECASE)]
    return failures


def run_case(case: Case, data: StoreData, policies: PolicyBook, llm, db_path: Path) -> dict:
    agent = ServiceAgent(data, policies, StoreClock(case.now), Storage(db_path), llm)
    session_id = f"{case.id}-{uuid.uuid4().hex[:6]}"
    tools_used: set[str] = set()
    transcript = []
    guard_flags: list[str] = []
    latency_ms = 0
    reply_text = ""
    degraded = False
    for turn in case.turns:
        reply = agent.reply(session_id, turn)
        tools_used |= {t["tool"] for t in reply.tools_used}
        guard_flags += reply.guard_flags
        latency_ms += reply.latency_ms
        reply_text = reply.text
        degraded = degraded or reply.degraded
        transcript.append({"customer": turn, "agent": reply.text, "tools": reply.tools_used})
    failures = evaluate(case, reply_text, tools_used)
    if degraded:
        failures.append("degraded reply: " + "; ".join(guard_flags))
    return {
        "id": case.id,
        "group": case.group,
        "covers": list(case.covers),
        "passed": not failures,
        "failures": failures,
        "guard_flags": guard_flags,
        "latency_ms": latency_ms,
        "transcript": transcript,
    }


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser()
    parser.add_argument("--only", help="Comma-separated groups or case ids")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--save", action="store_true", help="Write the report to evals/reports/")
    args = parser.parse_args()

    try:
        settings = load_settings()
        llm = build_llm(settings)
    except ConfigError as error:
        print(f"Configuration error: {error}", file=sys.stderr)
        return 2

    selected = CASES
    if args.only:
        wanted = set(args.only.split(","))
        selected = [c for c in CASES if c.group in wanted or c.id in wanted]

    data, policies = StoreData(settings.data_dir), PolicyBook()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "eval.db"
        Storage(db_path)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            results = list(pool.map(lambda c: run_case(c, data, policies, llm, db_path), selected))

    groups: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        groups[result["group"]].append(result)
        mark = "PASS" if result["passed"] else "FAIL"
        print(f"{mark}  {result['id']}  ({result['latency_ms']} ms)")
        for failure in result["failures"]:
            print(f"      {failure}")
        if not result["passed"]:
            print(f"      reply: {result['transcript'][-1]['agent']}")

    print("\nGroup                 Passed")
    for group, items in groups.items():
        passed = sum(r["passed"] for r in items)
        print(f"{group:<22}{passed}/{len(items)}{'  (critical)' if group in CRITICAL_GROUPS else ''}")
    total_passed = sum(r["passed"] for r in results)
    rate = total_passed / len(results) if results else 0
    latencies = sorted(r["latency_ms"] / max(len(r["transcript"]), 1) for r in results)
    median = latencies[len(latencies) // 2] if latencies else 0
    print(f"\nTotal: {total_passed}/{len(results)} ({rate:.0%}) | median latency per turn: {median / 1000:.1f} s | model: {settings.model}")

    if args.save:
        REPORTS_DIR.mkdir(exist_ok=True)
        name = re.sub(r"[^a-zA-Z0-9.-]+", "-", settings.model)
        path = REPORTS_DIR / f"{name}.json"
        report = {
            "model": settings.model,
            "provider": settings.provider,
            "run_at": datetime.now().isoformat(timespec="seconds"),
            "passed": total_passed,
            "total": len(results),
            "median_latency_seconds_per_turn": round(median / 1000, 1),
            "results": results,
        }
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8", newline="\n")
        print(f"Saved {path.relative_to(ROOT)}")

    critical_failed = any(not r["passed"] and r["group"] in CRITICAL_GROUPS for r in results)
    return 1 if critical_failed or rate < 0.9 else 0


if __name__ == "__main__":
    sys.exit(main())

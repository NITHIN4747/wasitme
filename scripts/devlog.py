#!/usr/bin/env python3
"""
wasitme DevLog — append a log entry to today's devlog file.
Usage:
    python scripts/devlog.py --role "Samritha" --type SPEC "Initial SPEC.md draft"
"""
import argparse
import datetime
import os
from pathlib import Path

LOG_TYPES = [
    "SPEC", "DECISION", "CHANGE-REQUEST", "BLOCKER", "UNBLOCKED",
    "CI", "AWS", "INCIDENT", "REVIEW", "HANDOFF", "RELEASE", "FIX",
    "NOTE", "TEST", "PHASE"
]

def main():
    parser = argparse.ArgumentParser(description="Append a devlog entry")
    parser.add_argument("message", help="Short description of the event")
    parser.add_argument("--role", required=True, help="Your role name e.g. Samritha, Ronaldo")
    parser.add_argument("--type", required=True, choices=LOG_TYPES, dest="log_type",
                        help=f"Event type: {', '.join(LOG_TYPES)}")
    parser.add_argument("--detail", nargs="*", help="Extra bullet points (repeat for multiple)")
    parser.add_argument("--ref", help="Git commit hash or PR number")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    devlog_dir = repo_root / "devlog"
    devlog_dir.mkdir(exist_ok=True)

    today = datetime.date.today().isoformat()
    log_file = devlog_dir / f"{today}.md"

    now_ist = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30)))
    timestamp = now_ist.strftime("%H:%M:%S IST")

    lines = [
        f"\n## [{timestamp}] [{args.role}] [{args.log_type}] {args.message}\n"
    ]

    if args.detail:
        for d in args.detail:
            lines.append(f"- {d}\n")

    if args.ref:
        lines.append(f"- **Ref:** `{args.ref}`\n")

    lines.append("\n---\n")

    if not log_file.exists():
        header = f"# DevLog — {today}\n\n"
        log_file.write_text(header, encoding="utf-8")

    with open(log_file, "a", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"✅ Logged [{args.log_type}] by {args.role} → devlog/{today}.md")

if __name__ == "__main__":
    main()

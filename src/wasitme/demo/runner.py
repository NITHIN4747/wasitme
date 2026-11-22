"""Offline scenario runner for wasitme demo command."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple

from wasitme.differ import diff_snapshots
from wasitme.models import DiffResult, Snapshot

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def get_demo_scenario(scenario: str = "crashloop") -> Tuple[Snapshot, Snapshot]:
    """Loads bundled baseline and current snapshot fixtures for the given scenario."""
    clean_base_file = FIXTURES_DIR / "clean_baseline.json"
    clean_curr_file = FIXTURES_DIR / "clean_current.json"
    crashloop_curr_file = FIXTURES_DIR / "crashloop_current.json"
    preexisting_curr_file = FIXTURES_DIR / "preexisting_current.json"

    if scenario == "clean":
        base_data = json.loads(clean_base_file.read_text(encoding="utf-8"))
        curr_data = json.loads(clean_curr_file.read_text(encoding="utf-8"))
    elif scenario == "preexisting":
        base_data = json.loads(preexisting_curr_file.read_text(encoding="utf-8"))
        curr_data = json.loads(preexisting_curr_file.read_text(encoding="utf-8"))
    else:  # default "crashloop"
        base_data = json.loads(clean_base_file.read_text(encoding="utf-8"))
        curr_data = json.loads(crashloop_curr_file.read_text(encoding="utf-8"))

    return Snapshot.from_dict(base_data), Snapshot.from_dict(curr_data)


def run_demo(scenario: str = "crashloop") -> DiffResult:
    """Runs the pure in-memory demo diff."""
    baseline, current = get_demo_scenario(scenario)
    return diff_snapshots(baseline, current)

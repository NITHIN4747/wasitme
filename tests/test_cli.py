"""
CLI tests using Typer CliRunner.
Owned by Suriya (Principal Full-Stack Engineer).
"""
from __future__ import annotations

import json

from typer.testing import CliRunner

from wasitme.cli import app

runner = CliRunner()


def test_version_cmd() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "wasitme version 0.1.0" in result.output


def test_demo_crashloop_exits_one() -> None:
    result = runner.invoke(app, ["demo", "--scenario", "crashloop"])
    assert result.exit_code == 1
    assert "REGRESSION DETECTED" in result.output
    assert "BROKE AFTER YOUR CHANGE" in result.output


def test_demo_clean_exits_zero() -> None:
    result = runner.invoke(app, ["demo", "--scenario", "clean"])
    assert result.exit_code == 0
    assert "CLEAN" in result.output


def test_demo_preexisting_exits_zero() -> None:
    result = runner.invoke(app, ["demo", "--scenario", "preexisting"])
    assert result.exit_code == 0
    assert "ALREADY BROKEN" in result.output


def test_demo_json_format() -> None:
    result = runner.invoke(app, ["demo", "--scenario", "clean", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["verdict"] == "CLEAN"
    assert data["exit_code"] == 0


def test_demo_markdown_format() -> None:
    result = runner.invoke(app, ["demo", "--scenario", "crashloop", "--format", "md"])
    assert result.exit_code == 1
    assert "### 🔴 wasitme: REGRESSION DETECTED" in result.output


def test_invalid_scenario_exits_two() -> None:
    result = runner.invoke(app, ["demo", "--scenario", "nonexistent"])
    assert result.exit_code == 2
    assert "Error: Unknown scenario" in result.output

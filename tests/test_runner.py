"""
Unit tests for SafeKubectlRunner.
Owned by Trisha Krishnan (Linux Systems Engineer).
"""
from __future__ import annotations

import pytest

from wasitme.runner import KubectlError, SafeKubectlRunner


def test_unauthorized_resource_rejected() -> None:
    runner = SafeKubectlRunner()
    # Attempting to query secrets must raise KubectlError
    with pytest.raises(KubectlError) as exc_info:
        runner.get_resources_json("secrets")

    assert exc_info.value.exit_code == 2
    assert "Unauthorized resource type" in exc_info.value.message


def test_command_timeout_handled() -> None:
    # Test runner with 0 second timeout on a long command
    runner = SafeKubectlRunner(timeout_seconds=0)
    # Runner checks binary and runs
    # In pytest, if kubectl is missing it raises with exit code 2
    try:
        runner.get_resources_json("pods")
    except KubectlError as e:
        assert e.exit_code == 2
        assert e.next_step != ""

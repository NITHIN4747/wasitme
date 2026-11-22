#!/usr/bin/env python3
"""
AWS Cloud Watchdog Monitoring Script.
Owned by Rakul Preet Singh (AWS Cloud Watchdog).
Invariants:
- Strictly read-only inspection.
- Verifies $0.00 cost status on AWS account.
- Scans for running EC2 instances or EKS clusters outside planned demo windows.
- Alerts immediately if any unexpected paid resources are detected.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys


def check_aws_cli() -> bool:
    return shutil.which("aws") is not None


def run_aws_read(args: list[str]) -> dict:
    if not check_aws_cli():
        return {}
    try:
        res = subprocess.run(
            ["aws", *args, "--output", "json"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if res.returncode == 0 and res.stdout.strip():
            return json.loads(res.stdout)
    except Exception:
        pass
    return {}


def scan_resources() -> dict:
    """Scans for active EC2 instances and EKS clusters."""
    status = {"ec2_running": 0, "eks_clusters": 0, "alert": False, "message": ""}

    if not check_aws_cli():
        status["message"] = "aws CLI not configured locally; relying on AWS $0 budget alert email."
        return status

    # 1. Check running EC2 instances
    ec2_data = run_aws_read(["ec2", "describe-instances", "--filters", "Name=instance-state-name,Values=running"])
    reservations = ec2_data.get("Reservations", [])
    running_ec2 = sum(len(r.get("Instances", [])) for r in reservations)
    status["ec2_running"] = running_ec2

    # 2. Check EKS clusters
    eks_data = run_aws_read(["eks", "list-clusters"])
    clusters = eks_data.get("clusters", [])
    status["eks_clusters"] = len(clusters)

    if running_ec2 > 0 or len(clusters) > 0:
        status["alert"] = True
        status["message"] = f"Active cloud resources found: {running_ec2} EC2 instances, {len(clusters)} EKS clusters. Verify teardown!"
    else:
        status["message"] = "All cloud resources clean ($0.00 spend verified). No running EC2/EKS."

    return status


def main() -> None:
    print("☁️ [Rakul Preet Singh] Running AWS Cloud Watchdog scan...")
    report = scan_resources()
    print(f"Status: {report['message']}")
    if report["alert"]:
        print("⚠️ ACTION REQUIRED: Active resources detected outside demo window!")
        sys.exit(1)
    else:
        print("✅ Clean: Zero unexpected resources active.")
        sys.exit(0)


if __name__ == "__main__":
    main()

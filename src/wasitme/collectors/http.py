"""
Synthetic HTTP health check collector.
Owned by Jyothika (Networking Engineer).
Invariants:
- Uses standard library urllib only (zero external deps).
- Takes 5 samples per target URL.
- Calculates majority status mode and p50 median latency.
- Sanitizes URLs (redacts credentials and query strings).
- Maps failure conditions strictly to HTTP_DOWN or HTTP_DEGRADED issues.
"""
from __future__ import annotations

import collections
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import List, Optional, Tuple

from wasitme.models import HttpCheckSnapshot, Issue, IssueKind, IssueSeverity


class HttpProber:
    """Probes HTTP endpoints with flapping resistance and URL sanitization."""

    def __init__(
        self,
        samples: int = 5,
        timeout_seconds: float = 4.0,
        allow_insecure_tls: bool = False,
    ):
        self.samples = samples
        self.timeout_seconds = timeout_seconds
        self.allow_insecure_tls = allow_insecure_tls

    @staticmethod
    def sanitize_url(raw_url: str) -> str:
        """Removes userinfo and query parameters from URL for safe storage."""
        parsed = urllib.parse.urlparse(raw_url)
        # Redact user:password if present
        netloc = parsed.hostname or ""
        if parsed.port:
            netloc = f"{netloc}:{parsed.port}"

        # Rebuild without query or fragment
        sanitized = urllib.parse.urlunparse(
            (parsed.scheme, netloc, parsed.path or "/", "", "", "")
        )
        return sanitized

    def probe(self, name: str, url: str) -> Tuple[HttpCheckSnapshot, Optional[Issue]]:
        """Executes 5 samples against target URL, computes p50, derives health issues."""
        sanitized_url = self.sanitize_url(url)
        latencies_ms: List[float] = []
        statuses: List[int] = []
        errors: List[str] = []

        ssl_ctx = ssl.create_default_context()
        if self.allow_insecure_tls:
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

        req = urllib.request.Request(
            url,
            headers={"User-Agent": "wasitme-prober/1.0", "Accept": "*/*"},
        )

        for _ in range(self.samples):
            start = time.perf_counter()
            try:
                with urllib.request.urlopen(
                    req, timeout=self.timeout_seconds, context=ssl_ctx
                ) as resp:
                    latency = (time.perf_counter() - start) * 1000.0
                    latencies_ms.append(latency)
                    statuses.append(resp.status)
            except urllib.error.HTTPError as e:
                latency = (time.perf_counter() - start) * 1000.0
                latencies_ms.append(latency)
                statuses.append(e.code)
            except urllib.error.URLError as e:
                reason_str = str(e.reason).lower()
                if "name or service not known" in reason_str or "nodename nor servname" in reason_str:
                    errors.append("DNS_FAILURE")
                elif "connection refused" in reason_str:
                    errors.append("CONNECTION_REFUSED")
                elif "timed out" in reason_str or "timeout" in reason_str:
                    errors.append("TIMEOUT")
                elif "certificate" in reason_str or "ssl" in reason_str:
                    errors.append("TLS_ERROR")
                else:
                    errors.append("NETWORK_ERROR")
                statuses.append(0)
            except Exception as e:
                errors.append(f"UNEXPECTED_ERROR: {e}")
                statuses.append(0)

        # Compute majority status
        status_counts = collections.Counter(statuses)
        status_mode, _ = status_counts.most_common(1)[0]
        ok_count = sum(1 for s in statuses if 200 <= s < 400)

        # Compute p50 median latency (only from successful network responses)
        if latencies_ms:
            sorted_latencies = sorted(latencies_ms)
            p50_ms = sorted_latencies[len(sorted_latencies) // 2]
        else:
            p50_ms = 0.0

        primary_error = errors[0] if errors else None

        snapshot = HttpCheckSnapshot(
            name=name,
            url=sanitized_url,
            samples=self.samples,
            ok_count=ok_count,
            status_mode=status_mode,
            p50_ms=round(p50_ms, 2),
            error=primary_error,
        )

        # Derive Issue
        issue: Optional[Issue] = None
        key = f"HTTP:{name}"

        if ok_count == 0 or status_mode == 0:
            issue = Issue(
                key=key,
                kind=IssueKind.HTTP_DOWN,
                severity=IssueSeverity.ERROR,
                detail=f"HTTP endpoint '{name}' is completely DOWN. Error: {primary_error or f'HTTP {status_mode}'}",
                metrics={
                    "status_mode": status_mode,
                    "ok_count": ok_count,
                    "p50_ms": snapshot.p50_ms,
                    "error": primary_error,
                },
            )
        elif status_mode >= 400:
            issue = Issue(
                key=key,
                kind=IssueKind.HTTP_DEGRADED,
                severity=IssueSeverity.ERROR if status_mode >= 500 else IssueSeverity.WARNING,
                detail=f"HTTP endpoint '{name}' returned degraded status code {status_mode}.",
                metrics={
                    "status_mode": status_mode,
                    "ok_count": ok_count,
                    "p50_ms": snapshot.p50_ms,
                },
            )
        elif snapshot.p50_ms > 1000.0:
            issue = Issue(
                key=key,
                kind=IssueKind.HTTP_DEGRADED,
                severity=IssueSeverity.WARNING,
                detail=f"HTTP endpoint '{name}' is responding slowly (p50: {snapshot.p50_ms}ms > 1000ms).",
                metrics={
                    "status_mode": status_mode,
                    "ok_count": ok_count,
                    "p50_ms": snapshot.p50_ms,
                },
            )

        return snapshot, issue

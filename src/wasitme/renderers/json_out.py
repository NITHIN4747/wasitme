"""
JSON output formatter for machine readability and scripting.
Owned by Suriya (Principal Full-Stack Engineer).
"""
from __future__ import annotations

import json

from wasitme.models import DiffResult


def render_json(diff_result: DiffResult) -> str:
    """Serializes DiffResult to formatted JSON string."""
    return json.dumps(diff_result.to_dict(), indent=2)

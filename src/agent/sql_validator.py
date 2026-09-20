"""SQL validation layer for the agent's query-execution node.

This module provides a strict allowlist-based validator that must be applied
to every LLM-generated query before execution. It is intentionally standalone
-- not coupled to any graph or LLM -- so it can be unit-tested in complete
isolation and reused across agent versions.

Design rationale (see PROJECT_SPEC.md section 7.2):
  - Read-only role is the infrastructure boundary (Postgres GRANT SELECT only).
  - This validator is the application-layer boundary: even if the role is ever
    misconfigured, a prompt-injected DROP or UPDATE never reaches the wire.
  - Statement timeout on the role is the runtime boundary.
  Three independent layers, none assumed to be sufficient alone.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Maximum rows the agent is permitted to fetch per query.
LIMIT_CAP: int = 500

#: DDL/DML keywords that must never appear in agent-generated queries.
#: Checked as whole-word matches to avoid false positives on identifiers
#: that happen to contain the keyword as a substring (e.g. ``updated_at``).
BLOCKED_KEYWORDS: tuple[str, ...] = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "GRANT",
)

# Pre-compiled patterns (compiled once at import time for performance).
_BLOCKED_PATTERN = re.compile(
    r"\b(?:" + "|".join(BLOCKED_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# Matches an existing LIMIT clause: LIMIT <integer> (optionally followed by
# OFFSET <integer>).  We deliberately do NOT match LIMIT ?, :param etc.
_LIMIT_PATTERN = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)

# Matches a semicolon anywhere in the query (prevents stacked statements).
_MULTI_STATEMENT_PATTERN = re.compile(r";")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_sql(query: str) -> tuple[bool, str]:
    """Validate and sanitise an LLM-generated SQL query.

    Rules applied in order:
      1. The query must start with SELECT (after stripping leading whitespace).
      2. The query must not contain any blocked DDL/DML keyword (whole-word).
      3. The query must not contain a semicolon (prevents stacked statements).
      4. If no LIMIT clause is present, ``LIMIT <LIMIT_CAP>`` is appended.
         If a LIMIT is already present, it is preserved unchanged.

    Args:
        query: Raw SQL string from the LLM.

    Returns:
        A ``(ok, result)`` tuple.

        - ``ok=True``  -- *result* is the sanitised, safe query to execute.
        - ``ok=False`` -- *result* is a human-readable rejection reason.
    """
    if not query or not query.strip():
        return False, "Query is empty."

    stripped = query.strip()

    # ------------------------------------------------------------------
    # Rule 1: Must start with SELECT
    # ------------------------------------------------------------------
    if not re.match(r"^SELECT\b", stripped, re.IGNORECASE):
        return False, (
            "Query rejected: only SELECT statements are permitted. "
            f"Query starts with: {stripped[:40]!r}"
        )

    # ------------------------------------------------------------------
    # Rule 2: No blocked DDL/DML keywords
    # ------------------------------------------------------------------
    blocked_match = _BLOCKED_PATTERN.search(stripped)
    if blocked_match:
        keyword = blocked_match.group(0).upper()
        return False, (
            f"Query rejected: keyword {keyword!r} is not permitted in agent queries."
        )

    # ------------------------------------------------------------------
    # Rule 3: No semicolons (prevents statement stacking)
    # ------------------------------------------------------------------
    if _MULTI_STATEMENT_PATTERN.search(stripped):
        return False, (
            "Query rejected: semicolons are not permitted "
            "(stacked/multiple statements disallowed)."
        )

    # ------------------------------------------------------------------
    # Rule 4: Inject LIMIT if absent
    # ------------------------------------------------------------------
    if not _LIMIT_PATTERN.search(stripped):
        sanitised = stripped.rstrip() + f" LIMIT {LIMIT_CAP}"
    else:
        sanitised = stripped

    return True, sanitised

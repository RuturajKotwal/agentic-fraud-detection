"""Tests for the SQL validation layer (src/agent/sql_validator.py).

Covers:
  - Valid SELECT queries pass through with LIMIT injected or preserved.
  - Each individually blocked keyword is rejected.
  - Semicolon-stacked statements are rejected.
  - LIMIT auto-injection when absent.
  - Existing LIMIT is preserved as-is.
  - Edge-cases: case-insensitivity, whitespace, keyword in identifier names.
"""

import pytest

from src.agent.sql_validator import BLOCKED_KEYWORDS, LIMIT_CAP, validate_sql


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def assert_ok(query: str) -> str:
    """Assert validate_sql returns True and return the sanitised query."""
    ok, result = validate_sql(query)
    assert ok is True, f"Expected query to pass but got rejection: {result!r}"
    return result


def assert_rejected(query: str, reason_fragment: str = "") -> str:
    """Assert validate_sql returns False; optionally check rejection message."""
    ok, result = validate_sql(query)
    assert ok is False, f"Expected query to be rejected but it passed: {result!r}"
    if reason_fragment:
        assert reason_fragment.lower() in result.lower(), (
            f"Expected rejection to mention {reason_fragment!r}, got: {result!r}"
        )
    return result


# ---------------------------------------------------------------------------
# Valid SELECT queries
# ---------------------------------------------------------------------------


class TestValidSelectQueries:
    def test_simple_select_gets_limit_injected(self):
        result = assert_ok("SELECT * FROM transactions")
        assert result == f"SELECT * FROM transactions LIMIT {LIMIT_CAP}"

    def test_select_lowercase(self):
        result = assert_ok("select id from transactions")
        assert f"LIMIT {LIMIT_CAP}" in result

    def test_select_mixed_case(self):
        result = assert_ok("SeLeCt id FROM transactions")
        assert f"LIMIT {LIMIT_CAP}" in result

    def test_select_with_where(self):
        result = assert_ok("SELECT * FROM transactions WHERE user_id = 42")
        assert f"LIMIT {LIMIT_CAP}" in result

    def test_select_with_join(self):
        q = (
            "SELECT t.*, u.avg_amount "
            "FROM transactions t "
            "JOIN user_transaction_summary u ON t.user_id = u.user_id "
            "WHERE t.is_flagged = true"
        )
        result = assert_ok(q)
        assert f"LIMIT {LIMIT_CAP}" in result

    def test_select_with_order_by(self):
        result = assert_ok("SELECT * FROM transactions ORDER BY transaction_date DESC")
        assert f"LIMIT {LIMIT_CAP}" in result

    def test_select_with_group_by(self):
        result = assert_ok(
            "SELECT merchant_country, COUNT(*) FROM transactions GROUP BY merchant_country"
        )
        assert f"LIMIT {LIMIT_CAP}" in result

    def test_leading_whitespace_is_stripped(self):
        result = assert_ok("   SELECT id FROM transactions   ")
        assert result.startswith("SELECT")

    def test_subquery_is_allowed(self):
        q = "SELECT * FROM (SELECT id, amount FROM transactions WHERE amount > 1000) sub"
        result = assert_ok(q)
        assert f"LIMIT {LIMIT_CAP}" in result


# ---------------------------------------------------------------------------
# Each blocked keyword rejected individually
# ---------------------------------------------------------------------------


class TestBlockedKeywords:
    @pytest.mark.parametrize("keyword", BLOCKED_KEYWORDS)
    def test_blocked_keyword_in_query_is_rejected(self, keyword: str):
        # Embed the blocked keyword inside what otherwise looks like a SELECT
        query = f"SELECT * FROM transactions WHERE 1=1 {keyword} INTO evil"
        assert_rejected(query, keyword)

    def test_insert_at_start_rejected(self):
        assert_rejected("INSERT INTO transactions VALUES (1,2,3)", "INSERT")

    def test_update_standalone_rejected(self):
        assert_rejected("UPDATE transactions SET is_flagged=true WHERE user_id=1", "UPDATE")

    def test_delete_standalone_rejected(self):
        assert_rejected("DELETE FROM transactions WHERE user_id=1", "DELETE")

    def test_drop_table_rejected(self):
        assert_rejected("DROP TABLE transactions", "DROP")

    def test_alter_table_rejected(self):
        assert_rejected("ALTER TABLE transactions ADD COLUMN foo TEXT", "ALTER")

    def test_truncate_rejected(self):
        assert_rejected("TRUNCATE TABLE transactions", "TRUNCATE")

    def test_grant_rejected(self):
        assert_rejected("GRANT SELECT ON transactions TO evil_user", "GRANT")

    def test_blocked_keyword_case_insensitive(self):
        assert_rejected("SELECT * FROM transactions; delete from transactions", "DELETE")

    def test_blocked_keyword_lowercase(self):
        assert_rejected("select * from transactions where 1=1 insert into foo", "INSERT")

    def test_select_with_update_in_body_rejected(self):
        # 'update_needed' contains 'update' as a substring — must NOT trigger
        # because we use whole-word matching.  This verifies it passes cleanly.
        result = assert_ok(
            "SELECT * FROM transactions WHERE flag_reason = 'update_needed'"
        )
        assert "LIMIT" in result

        # Bare whole-word UPDATE in the query body MUST be rejected
        assert_rejected(
            "SELECT *, UPDATE FROM transactions",
            "UPDATE",
        )

    def test_keyword_as_substring_of_identifier_not_blocked(self):
        # 'updated_at', 'inserted_by', 'deleted_flag' contain blocked words as
        # substrings — must NOT be blocked (whole-word regex).
        result = assert_ok("SELECT updated_at, inserted_by FROM transactions")
        assert "LIMIT" in result

    def test_drop_keyword_as_word_boundary_blocked(self):
        assert_rejected("SELECT * FROM transactions -- DROP", "DROP")


# ---------------------------------------------------------------------------
# Stacked / multi-statement queries rejected
# ---------------------------------------------------------------------------


class TestMultiStatementRejection:
    def test_semicolon_at_end_rejected(self):
        assert_rejected("SELECT * FROM transactions;", "semicolon")

    def test_two_statements_semicolon_separated_rejected(self):
        assert_rejected(
            "SELECT * FROM transactions; SELECT * FROM user_transaction_summary",
            "semicolon",
        )

    def test_destructive_stacked_statement_rejected(self):
        # "SELECT 1; DROP TABLE transactions" is caught first by the DROP keyword
        # rule (rules run in order: keyword check is Rule 2, semicolon is Rule 3).
        # Either rejection is correct — we just assert the query is blocked.
        assert_rejected("SELECT 1; DROP TABLE transactions")

        # A stacked statement with no blocked keyword hits the semicolon rule.
        assert_rejected(
            "SELECT 1; SELECT 2",
            "semicolon",
        )

    def test_semicolon_mid_query_rejected(self):
        assert_rejected(
            "SELECT * FROM transactions WHERE user_id = 1; --comment",
            "semicolon",
        )


# ---------------------------------------------------------------------------
# LIMIT auto-injection and preservation
# ---------------------------------------------------------------------------


class TestLimitHandling:
    def test_limit_injected_when_absent(self):
        ok, result = validate_sql("SELECT * FROM transactions")
        assert ok is True
        assert f"LIMIT {LIMIT_CAP}" in result

    def test_existing_limit_is_preserved_exactly(self):
        ok, result = validate_sql("SELECT * FROM transactions LIMIT 10")
        assert ok is True
        assert "LIMIT 10" in result
        # Must not double-inject
        assert result.count("LIMIT") == 1

    def test_existing_large_limit_is_preserved(self):
        # We preserve — not clamp — an existing LIMIT.  Clamping would be a
        # separate policy decision made at the execution layer, not here.
        ok, result = validate_sql("SELECT * FROM transactions LIMIT 9999")
        assert ok is True
        assert "LIMIT 9999" in result
        assert result.count("LIMIT") == 1

    def test_limit_case_insensitive_preserved(self):
        ok, result = validate_sql("SELECT * FROM transactions limit 50")
        assert ok is True
        assert result.count("LIMIT") + result.count("limit") == 1

    def test_limit_with_offset_preserved(self):
        ok, result = validate_sql("SELECT * FROM transactions LIMIT 100 OFFSET 200")
        assert ok is True
        assert "LIMIT 100" in result
        assert result.count("LIMIT") == 1

    def test_limit_cap_constant_is_500(self):
        assert LIMIT_CAP == 500


# ---------------------------------------------------------------------------
# Non-SELECT queries rejected
# ---------------------------------------------------------------------------


class TestNonSelectRejection:
    def test_empty_string_rejected(self):
        assert_rejected("", "empty")

    def test_whitespace_only_rejected(self):
        assert_rejected("   ", "empty")

    def test_with_clause_cte_allowed(self):
        # WITH ... SELECT is a CTE, not a bare non-SELECT.
        # Our validator currently requires the *outermost* statement to start
        # with SELECT.  A CTE starting with WITH would be rejected.
        # This test documents that behaviour explicitly so the team can decide
        # whether to relax the rule later.
        ok, result = validate_sql(
            "WITH cte AS (SELECT id FROM transactions) SELECT * FROM cte"
        )
        # WITH does not start with SELECT — expect rejection under current rules.
        assert ok is False

    def test_explain_rejected(self):
        assert_rejected("EXPLAIN SELECT * FROM transactions", "SELECT")

    def test_copy_rejected(self):
        assert_rejected("COPY transactions TO STDOUT", "SELECT")

    def test_call_rejected(self):
        assert_rejected("CALL some_procedure()", "SELECT")

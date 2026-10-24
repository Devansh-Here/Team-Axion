import sqlite3

import pytest

from app.profiler import profile_columns


@pytest.fixture
def conn():
    connection = sqlite3.connect(":memory:")
    connection.execute(
        "CREATE TABLE messy (value TEXT, amount TEXT, event_date TEXT)"
    )
    connection.executemany(
        "INSERT INTO messy VALUES (?, ?, ?)",
        [
            (None, "0", "2024-01-15"),
            ("", "10", "04/01/2025"),
            ("N/A", "12.5", "2025-02-01"),
            ("unknown", "", "2025"),
            ("-", "-", "2025"),
            ("ready", "0", "2025-12-31"),
            ("ready", "0", "2025-12-31"),
        ],
    )
    yield connection
    connection.close()


def test_profile_distinguishes_null_blank_markers_and_zero(conn):
    profile = profile_columns(conn, ["messy"])["messy"]

    value = profile["columns"]["value"]
    amount = profile["columns"]["amount"]

    assert value["null_count"] == 1
    assert value["blank_count"] == 1
    assert value["missing_marker_counts"]["N/A"] == 1
    assert value["missing_marker_counts"]["unknown"] == 1
    assert value["missing_marker_counts"]["-"] == 1
    assert amount["numeric_range"] == {"min": 0.0, "max": 12.5}


def test_profile_flags_ambiguous_date_and_reports_range(conn):
    dates = profile_columns(conn, ["messy"])["messy"]["columns"]["event_date"]

    assert dates["date_range"] == {"min": "2024-01-15", "max": "2025-12-31", "ambiguous_count": 1}
    assert "AMBIGUOUS_DATES" in dates["warnings"]


def test_profile_counts_exact_duplicate_rows(conn):
    profile = profile_columns(conn, ["messy"])["messy"]

    assert profile["row_count"] == 7
    assert profile["column_count"] == 3
    assert profile["duplicate_like_rows"] == 1


def test_profile_does_not_mutate_source(conn):
    before = conn.execute("SELECT COUNT(*) FROM messy").fetchone()[0]

    profile_columns(conn, ["messy"])

    after = conn.execute("SELECT COUNT(*) FROM messy").fetchone()[0]
    assert after == before


def test_profile_rejects_unknown_table(conn):
    with pytest.raises(ValueError):
        profile_columns(conn, ["does_not_exist"])

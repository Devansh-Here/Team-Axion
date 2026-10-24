import csv
import hashlib
import sqlite3

import pytest

from app.ingestion import ingest_file


def test_csv_import_preserves_leading_zeroes_and_records_hash(tmp_path):
    source = tmp_path / "sales export.csv"
    destination = tmp_path / "imported.sqlite"
    source.write_text("Customer ID,Net Amount\n00123,10\n00007,0\n", encoding="utf-8")

    result = ingest_file(source, destination)

    expected_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    assert result["source_sha256"] == expected_hash
    assert result["rows_loaded"] == 2
    assert result["tables"][0]["original_columns"] == ["Customer ID", "Net Amount"]
    assert result["tables"][0]["columns"] == ["customer_id", "net_amount"]

    connection = sqlite3.connect(destination)
    try:
        rows = connection.execute("SELECT * FROM data").fetchall()
    finally:
        connection.close()
    assert rows == [("00123", "10"), ("00007", "0")]


def test_csv_duplicate_headers_get_unique_safe_names(tmp_path):
    source = tmp_path / "input.csv"
    destination = tmp_path / "out.sqlite"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerows([["Region", "Region", "1st Value"], ["North", "N", "x"]])

    result = ingest_file(source, destination)

    assert result["tables"][0]["columns"] == ["region", "region_2", "_1st_value"]


def test_xlsx_import_uses_sheet_names_and_text_columns(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "input.xlsx"
    destination = tmp_path / "out.sqlite"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Sales Data"
    sheet.append(["Order ID", "Amount"])
    sheet.append(["0001", 12.5])
    workbook.save(source)
    workbook.close()

    result = ingest_file(source, destination)

    assert result["tables"][0]["table_name"] == "sales_data"
    connection = sqlite3.connect(destination)
    try:
        row = connection.execute("SELECT * FROM sales_data").fetchone()
    finally:
        connection.close()
    assert row == ("0001", "12.5")


def test_oversized_input_is_rejected_before_output(tmp_path):
    source = tmp_path / "large.csv"
    destination = tmp_path / "out.sqlite"
    source.write_text("a\n12345\n", encoding="utf-8")

    with pytest.raises(ValueError, match="size limit"):
        ingest_file(source, destination, max_bytes=1)
    assert not destination.exists()


def test_xlsx_formulas_are_rejected_and_partial_output_removed(tmp_path):
    openpyxl = pytest.importorskip("openpyxl")
    source = tmp_path / "formula.xlsx"
    destination = tmp_path / "out.sqlite"
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["Amount", "Total"])
    sheet.append([1, "=A2*2"])
    workbook.save(source)
    workbook.close()

    with pytest.raises(ValueError, match="formulas"):
        ingest_file(source, destination)
    assert not destination.exists()


def test_unsupported_extension_is_rejected(tmp_path):
    source = tmp_path / "input.txt"
    destination = tmp_path / "out.sqlite"
    source.write_text("hello", encoding="utf-8")

    with pytest.raises(ValueError, match="CSV and XLSX"):
        ingest_file(source, destination)

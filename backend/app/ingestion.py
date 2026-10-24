"""Safe CSV/XLSX ingestion into a new local SQLite database."""

import csv
import hashlib
import os
from pathlib import Path
import re
import secrets
import sqlite3
from typing import Iterable


SUPPORTED_SUFFIXES = {".csv", ".xlsx"}
DEFAULT_MAX_BYTES = 25 * 1024 * 1024
DEFAULT_MAX_ROWS = 100_000
DEFAULT_MAX_COLUMNS = 200
_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9_]+")


def _quote_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _safe_name(value: object, fallback: str) -> str:
    text = str(value or "").strip()
    text = _SAFE_NAME_RE.sub("_", text).strip("_").lower()
    if not text:
        text = fallback
    if text[0].isdigit():
        text = f"_{text}"
    return text[:120]


def _unique_names(values: Iterable[object], prefix: str) -> list[str]:
    result = []
    used = set()
    for index, value in enumerate(values, start=1):
        base = _safe_name(value, f"{prefix}_{index}")
        name = base
        suffix = 2
        while name in used:
            name = f"{base}_{suffix}"
            suffix += 1
        used.add(name)
        result.append(name)
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _decode_csv(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV encoding is not supported")


def _read_csv(path: Path, max_rows: int, max_columns: int) -> tuple[list[dict], list[str]]:
    text, encoding = _decode_csv(path)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample)
    except csv.Error:
        dialect = csv.excel
    reader = csv.reader(text.splitlines(), dialect)
    try:
        original_headers = next(reader)
    except StopIteration as exc:
        raise ValueError("CSV has no header row") from exc
    if not original_headers or len(original_headers) > max_columns:
        raise ValueError("CSV has an invalid column count")
    safe_headers = _unique_names(original_headers, "column")
    rows = []
    for row_number, row in enumerate(reader, start=2):
        if row_number > max_rows + 1:
            raise ValueError("CSV exceeds the row limit")
        if len(row) > max_columns:
            raise ValueError("CSV has too many columns")
        row = list(row) + [""] * (len(safe_headers) - len(row))
        if len(row) > len(safe_headers):
            raise ValueError(f"CSV row {row_number} has too many fields")
        rows.append({"values": row, "row_number": row_number})
    return [{"name": "data", "headers": original_headers, "safe_headers": safe_headers, "rows": rows}], [f"CSV_ENCODING:{encoding}"]


def _read_xlsx(path: Path, max_rows: int, max_columns: int) -> tuple[list[dict], list[str]]:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise ValueError("XLSX support is unavailable") from exc

    workbook = load_workbook(path, read_only=True, data_only=False, keep_links=False)
    sheets = []
    warnings = []
    try:
        for worksheet in workbook.worksheets:
            rows = worksheet.iter_rows(values_only=False)
            try:
                header_cells = next(rows)
            except StopIteration:
                continue
            if len(header_cells) > max_columns:
                raise ValueError("XLSX has too many columns")
            original_headers = [cell.value for cell in header_cells]
            if not any(value not in (None, "") for value in original_headers):
                raise ValueError(f"XLSX sheet {worksheet.title!r} has no header row")
            safe_headers = _unique_names(original_headers, "column")
            sheet_rows = []
            for row_number, cells in enumerate(rows, start=2):
                if row_number > max_rows + 1:
                    raise ValueError("XLSX exceeds the row limit")
                values = []
                for cell in cells[:max_columns]:
                    if cell.data_type == "f":
                        raise ValueError("formulas are not allowed in XLSX input")
                    values.append(cell.value)
                if len(values) > len(safe_headers):
                    raise ValueError(f"XLSX sheet {worksheet.title!r} has too many fields")
                values += [None] * (len(safe_headers) - len(values))
                sheet_rows.append({"values": values, "row_number": row_number})
            sheets.append({
                "name": worksheet.title,
                "headers": original_headers,
                "safe_headers": safe_headers,
                "rows": sheet_rows,
            })
        if not sheets:
            raise ValueError("XLSX has no non-empty sheets")
    finally:
        workbook.close()
    return sheets, warnings


def _write_database(destination: Path, sheets: list[dict]) -> dict:
    connection = sqlite3.connect(destination)
    try:
        table_metadata = []
        for sheet in sheets:
            table_name = _safe_name(sheet["name"], "data")
            existing = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            table_name = _unique_names([table_name], "table")[0]
            suffix = 2
            base = table_name
            while table_name in existing:
                table_name = f"{base}_{suffix}"
                suffix += 1
            columns = ", ".join(f"{_quote_identifier(name)} TEXT" for name in sheet["safe_headers"])
            connection.execute(f"CREATE TABLE {_quote_identifier(table_name)} ({columns})")
            placeholders = ", ".join("?" for _ in sheet["safe_headers"])
            connection.executemany(
                f"INSERT INTO {_quote_identifier(table_name)} VALUES ({placeholders})",
                [tuple(row["values"]) for row in sheet["rows"]],
            )
            table_metadata.append({
                "source_name": sheet["name"],
                "table_name": table_name,
                "original_columns": sheet["headers"],
                "columns": sheet["safe_headers"],
                "rows_loaded": len(sheet["rows"]),
                "rows_rejected": 0,
            })
        connection.commit()
        return {"tables": table_metadata, "rows_loaded": sum(item["rows_loaded"] for item in table_metadata)}
    finally:
        connection.close()


def ingest_file(
    source_path: str | os.PathLike,
    destination_db: str | os.PathLike,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_rows: int = DEFAULT_MAX_ROWS,
    max_columns: int = DEFAULT_MAX_COLUMNS,
) -> dict:
    """Validate and import one CSV/XLSX file into a new SQLite database.

    All imported columns are stored as TEXT so mixed values and leading zeros
    are preserved. The destination is written atomically through a temporary
    file and removed if any validation or import step fails.
    """
    source = Path(source_path)
    destination = Path(destination_db)
    if not source.is_file():
        raise ValueError("source file does not exist")
    if source.suffix.lower() not in SUPPORTED_SUFFIXES:
        raise ValueError("only CSV and XLSX files are supported")
    if source.stat().st_size > max_bytes:
        raise ValueError("source file exceeds the size limit")
    if max_rows < 1 or max_columns < 1:
        raise ValueError("row and column limits must be positive")
    if destination.resolve() == source.resolve():
        raise ValueError("destination must be different from source")

    source_hash = _sha256(source)
    if source.suffix.lower() == ".csv":
        sheets, warnings = _read_csv(source, max_rows, max_columns)
    else:
        sheets, warnings = _read_xlsx(source, max_rows, max_columns)

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{secrets.token_hex(8)}.part")
    try:
        summary = _write_database(temporary, sheets)
        os.replace(temporary, destination)
    except Exception:
        if temporary.exists():
            temporary.unlink()
        if destination.exists() and destination.stat().st_size == 0:
            destination.unlink()
        raise

    return {
        "source_sha256": source_hash,
        "destination_db": str(destination),
        "warnings": warnings,
        **summary,
    }

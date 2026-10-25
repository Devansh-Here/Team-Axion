"""Ingestion: CSV / TSV / Excel upload -> per-dataset SQLite file.

Rules:
- Cell values are NOT cleaned ("N/A", "-", "" stay as-is). Profiler decides later.
- Only identifiers (table/column names) are normalised.
- Upload is untrusted: extension allowlist, size cap, zip-bomb check,
  row/column/sheet caps, dataset_id validated (no path traversal).
- Excel formulas are never evaluated (cached values only); macro files (.xlsm) rejected.
- Errors are IngestError(code). Raw exception text is never returned to the caller.
"""
from __future__ import annotations

import os
import re
import sqlite3
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from app.config import DATA_DIR, MAX_UPLOAD_MB

ALLOWED_EXT = {".csv", ".tsv", ".xlsx", ".xls"}
MAX_ROWS_PER_TABLE = 200_000
MAX_COLUMNS = 200
MAX_SHEETS = 20
MAX_UNZIPPED_MB = 200
MAX_NAME_LEN = 60
RESERVED_DATASET_IDS = {"demo"}
ENCODINGS = ("utf-8-sig", "cp1252", "latin-1")  # latin-1 never fails
_DATASET_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")


class IngestError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class IngestResult(BaseModel):
    dataset_id: str
    db_path: str
    tables: dict[str, list[str]]      # table -> clean column names
    table_reports: list[dict]         # rows, original->clean column mapping, dtype
    warnings: list[str] = []


# ---------- helpers ----------

def clean_identifier(name, fallback: str) -> str:
    s = re.sub(r"[^0-9a-z]+", "_", str(name).strip().lower()).strip("_")
    if not s:
        s = fallback
    if s[0].isdigit():
        s = f"c_{s}"
    if s.startswith("sqlite_"):
        s = f"t_{s}"
    return s[:MAX_NAME_LEN]


def _unique(names: list[str]) -> list[str]:
    used: set[str] = set()
    out = []
    for n in names:
        cand, i = n, 1
        while cand in used:
            i += 1
            cand = f"{n}_{i}"
        used.add(cand)
        out.append(cand)
    return out


def _check_size(path: Path) -> None:
    size = path.stat().st_size
    if size == 0:
        raise IngestError("EMPTY_FILE")
    if size > MAX_UPLOAD_MB * 1024 * 1024:
        raise IngestError("FILE_TOO_LARGE")


def _check_zip(path: Path) -> None:
    try:
        with zipfile.ZipFile(path) as z:
            total = sum(i.file_size for i in z.infolist())
    except zipfile.BadZipFile:
        raise IngestError("CORRUPT_FILE") from None
    if total > MAX_UNZIPPED_MB * 1024 * 1024:
        raise IngestError("ARCHIVE_TOO_LARGE")


def _read_csv(path: Path, sep: str) -> pd.DataFrame:
    for enc in ENCODINGS:
        try:
            return pd.read_csv(
                path, sep=sep, engine="python", encoding=enc,
                keep_default_na=False, na_values=[],
                nrows=MAX_ROWS_PER_TABLE + 1,
            )
        except UnicodeDecodeError:
            continue
        except pd.errors.EmptyDataError:
            raise IngestError("EMPTY_FILE") from None
        except Exception:
            raise IngestError("CSV_PARSE_ERROR") from None
    raise IngestError("CSV_PARSE_ERROR")


def _read_excel(path: Path, ext: str) -> dict[str, pd.DataFrame]:
    if ext == ".xlsx":
        _check_zip(path)
    try:
        return pd.read_excel(path, sheet_name=None,
                             keep_default_na=False, na_values=[])
    except Exception:
        raise IngestError("EXCEL_PARSE_ERROR") from None


def _drop_blank_unnamed(df: pd.DataFrame, label: str, warnings: list[str]) -> pd.DataFrame:
    drop = [
        c for c in df.columns
        if str(c).startswith("Unnamed:") and df[c].astype(str).str.strip().eq("").all()
    ]
    if drop:
        warnings.append(f"{label}: dropped {len(drop)} empty unnamed column(s)")
        df = df.drop(columns=drop)
    return df


def _load_frames(path: Path, ext: str, stem: str, warnings: list[str]) -> dict[str, pd.DataFrame]:
    if ext in (".csv", ".tsv"):
        return {stem: _read_csv(path, "\t" if ext == ".tsv" else ",")}

    sheets = _read_excel(path, ext)
    sheets = {k: v for k, v in sheets.items() if len(v.columns) > 0}
    if not sheets:
        raise IngestError("NO_DATA")
    if len(sheets) > MAX_SHEETS:
        raise IngestError("TOO_MANY_SHEETS")
    if len(sheets) == 1:
        return {stem: next(iter(sheets.values()))}
    return {f"{stem}_{clean_identifier(name, 'sheet')}": df for name, df in sheets.items()}


# ---------- main entry ----------

def ingest_file(
    src_path: str | os.PathLike,
    dataset_id: str,
    *,
    data_dir: str | os.PathLike | None = None,
    original_name: str | None = None,
    overwrite: bool = False,
) -> IngestResult:
    """Load a CSV/TSV/XLSX/XLS file into <data_dir>/datasets/<dataset_id>.sqlite."""
    if not isinstance(dataset_id, str) or not _DATASET_ID.match(dataset_id):
        raise IngestError("INVALID_DATASET_ID")
    if dataset_id in RESERVED_DATASET_IDS:
        raise IngestError("DATASET_ID_RESERVED")

    src = Path(src_path)
    if not src.is_file():
        raise IngestError("FILE_NOT_FOUND")

    display_name = original_name or src.name
    ext = Path(display_name).suffix.lower()
    if ext not in ALLOWED_EXT:
        raise IngestError("UNSUPPORTED_TYPE")
    _check_size(src)

    out_dir = Path(data_dir or DATA_DIR) / "datasets"
    out_dir.mkdir(parents=True, exist_ok=True)
    final = out_dir / f"{dataset_id}.sqlite"
    if final.exists() and not overwrite:
        raise IngestError("DATASET_EXISTS")

    warnings: list[str] = []
    stem = clean_identifier(Path(display_name).stem, "table")
    frames = _load_frames(src, ext, stem, warnings)

    tmp_fd, tmp_name = tempfile.mkstemp(dir=out_dir, suffix=".tmp")
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)

    tables: dict[str, list[str]] = {}
    reports: list[dict] = []
    conn = None
    try:
        conn = sqlite3.connect(tmp_path)
        used_tables: set[str] = set()

        for base, df in frames.items():
            df = _drop_blank_unnamed(df, base, warnings)

            if len(df.columns) == 0:
                raise IngestError("NO_DATA")
            if len(df.columns) > MAX_COLUMNS:
                raise IngestError("TOO_MANY_COLUMNS")
            if len(df) > MAX_ROWS_PER_TABLE:
                raise IngestError("TOO_MANY_ROWS")

            table = clean_identifier(base, "table")
            cand, i = table, 1
            while cand in used_tables:
                i += 1
                cand = f"{table}_{i}"
            table = cand
            used_tables.add(table)

            original = [str(c) for c in df.columns]
            clean = _unique([clean_identifier(c, f"col_{i + 1}") for i, c in enumerate(original)])
            df = df.copy()
            df.columns = clean

            if len(df) == 0:
                warnings.append(f"{table}: 0 data rows")

            df.to_sql(table, conn, index=False, chunksize=5000)

            tables[table] = clean
            reports.append({
                "table": table,
                "rows": int(len(df)),
                "columns": [
                    {"clean": c, "original": o, "dtype": str(df[c].dtype)}
                    for c, o in zip(clean, original)
                ],
            })

        conn.commit()
        conn.close()
        conn = None
        os.replace(tmp_path, final)   # atomic swap
    except IngestError:
        raise
    except Exception:
        raise IngestError("INGEST_FAILED") from None
    finally:
        if conn is not None:
            conn.close()
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

    return IngestResult(
        dataset_id=dataset_id, db_path=str(final),
        tables=tables, table_reports=reports, warnings=warnings,
    )


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="Load CSV/Excel into a dataset SQLite file")
    ap.add_argument("file")
    ap.add_argument("--dataset-id", required=True)
    ap.add_argument("--overwrite", action="store_true")
    args = ap.parse_args()
    try:
        res = ingest_file(args.file, args.dataset_id, overwrite=args.overwrite)
    except IngestError as e:
        raise SystemExit(f"INGEST FAILED: {e.code}")
    print(f"Database: {res.db_path}")
    for rep in res.table_reports:
        print(f"  {rep['table']:<30} {rep['rows']:>8} rows  {len(rep['columns'])} cols")
    for w in res.warnings:
        print(f"  warning: {w}")
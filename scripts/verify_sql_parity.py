"""Compare the PostgreSQL result sets in sql/01_analysis.sql with the Python CSVs.

The script splits 01_analysis.sql into its numbered sections, runs each SELECT
through psql as COPY ... TO STDOUT (CSV), and compares the numbers with
results/*.csv produced by src/analysis.py.

Usage:
    python scripts/verify_sql_parity.py --dsn "host=127.0.0.1 port=55432 user=postgres dbname=ecommerce_retail"

The psql executable is taken from the PSQL environment variable, then PATH, and
finally from the standard Windows installation directory (PostgreSQL 18).
"""
from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SQL_FILE = ROOT / "sql" / "01_analysis.sql"
RESULTS = ROOT / "results"

WINDOWS_PSQL = Path(r"C:\Program Files\PostgreSQL\18\bin\psql.exe")


def find_psql() -> str:
    """Locate psql portably, keeping the old Windows path as a fallback."""
    override = os.environ.get("PSQL")
    if override:
        return override
    on_path = shutil.which("psql")
    if on_path:
        return on_path
    candidates = [WINDOWS_PSQL]
    install_root = Path(r"C:\Program Files\PostgreSQL")
    if install_root.is_dir():
        candidates.extend(sorted(install_root.glob(r"*\bin\psql.exe"), reverse=True))
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise SystemExit(
        "psql не найден: установите клиент PostgreSQL, добавьте его в PATH "
        "или задайте переменную окружения PSQL."
    )


def sections(sql_text: str) -> dict[int, str]:
    parts = re.split(r"(?m)^-- (\d)\. .*$", sql_text)
    out: dict[int, str] = {}
    for index in range(1, len(parts), 2):
        number = int(parts[index])
        body = parts[index + 1].strip()
        if body.endswith(";"):
            body = body[:-1]
        out[number] = body
    return out


def run_query(dsn: str, query: str) -> pd.DataFrame:
    copy = f"COPY (\n{query}\n) TO STDOUT WITH (FORMAT csv, HEADER true);"
    proc = subprocess.run(
        [find_psql(), dsn, "-v", "ON_ERROR_STOP=1", "-f", "-"],
        input=copy,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PGCLIENTENCODING": "UTF8"},
    )
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"psql failed with exit code {proc.returncode}")
    return pd.read_csv(io.StringIO(proc.stdout))


def close(a: float, b: float, tol: float = 1e-6) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    if pd.isna(a) or pd.isna(b):
        return False
    return abs(float(a) - float(b)) <= tol * max(1.0, abs(float(a)))


def compare(name: str, sql_df: pd.DataFrame, py_df: pd.DataFrame, keys: list[str],
            numeric: list[str]) -> bool:
    ok = True
    if len(sql_df) != len(py_df):
        print(f"[FAIL] {name}: rows {len(sql_df)} != {len(py_df)}")
        return False
    for i in range(len(py_df)):
        for key in keys:
            if str(sql_df.iloc[i][key]).strip() != str(py_df.iloc[i][key]).strip():
                print(f"[FAIL] {name} row {i}: {key} {sql_df.iloc[i][key]!r} != {py_df.iloc[i][key]!r}")
                ok = False
        for column in numeric:
            if not close(sql_df.iloc[i][column], py_df.iloc[i][column]):
                print(f"[FAIL] {name} row {i}: {column} {sql_df.iloc[i][column]} != {py_df.iloc[i][column]}")
                ok = False
    print(f"[{'PASS' if ok else 'FAIL'}] {name}: {len(py_df)} rows")
    return ok


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", default="host=127.0.0.1 port=55432 user=postgres dbname=ecommerce_retail")
    args = parser.parse_args()

    blocks = sections(SQL_FILE.read_text(encoding="utf-8"))

    monthly_sql = run_query(args.dsn, blocks[3])
    monthly_sql["month"] = monthly_sql["month"].str.slice(0, 7)
    monthly_py = pd.read_csv(RESULTS / "monthly_sales.csv", encoding="utf-8-sig", dtype={"month": str})

    products_sql = run_query(args.dsn, blocks[4])
    products_py = pd.read_csv(RESULTS / "top_products.csv", encoding="utf-8-sig", dtype={"stock_code": str})

    countries_sql = run_query(args.dsn, blocks[5])
    countries_py = pd.read_csv(RESULTS / "top_countries.csv", encoding="utf-8-sig")

    monthly_ok = compare(
        "monthly_sales", monthly_sql, monthly_py, ["month"],
        [
            "positive_line_sales_gbp", "positive_sales_orders", "positive_sales_lines",
            "units_sold", "return_or_adjustment_value_gbp_abs", "cancellation_value_gbp_abs",
        ],
    )
    products_ok = compare(
        "top_products", products_sql, products_py, ["stock_code"],
        [
            "positive_line_sales_gbp", "units_sold", "positive_sales_lines",
            "positive_sales_orders",
        ],
    )
    countries_ok = compare(
        "top_countries", countries_sql, countries_py, ["country"],
        ["positive_line_sales_gbp", "positive_sales_orders", "units_sold"],
    )

    if not (monthly_ok and products_ok and countries_ok):
        raise SystemExit(1)
    print("SQL and Python agree on every published aggregate.")


if __name__ == "__main__":
    main()

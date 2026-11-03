"""Reproducible cleaning and descriptive analysis for UCI Online Retail."""

from __future__ import annotations

import json
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

DATASET_PAGE = "https://archive.ics.uci.edu/dataset/352/online+retail"
DATASET_ZIP = "https://archive.ics.uci.edu/static/public/352/online+retail.zip"
SOURCE_COLUMNS = [
    "invoice_no",
    "stock_code",
    "description",
    "quantity",
    "invoice_date",
    "unit_price",
    "customer_id",
    "country",
]


def _as_text(series: pd.Series) -> pd.Series:
    values = series.astype("string").str.strip()
    return values.mask(values.eq(""), pd.NA)


def normalize_input(frame: pd.DataFrame) -> pd.DataFrame:
    """Standardize the eight UCI columns without dropping rows."""
    aliases = {
        "invoiceno": "invoice_no",
        "stockcode": "stock_code",
        "description": "description",
        "quantity": "quantity",
        "invoicedate": "invoice_date",
        "unitprice": "unit_price",
        "customerid": "customer_id",
        "country": "country",
    }
    renamed = {column: aliases.get(str(column).replace(" ", "").lower()) for column in frame.columns}
    renamed = {old: new for old, new in renamed.items() if new is not None}
    result = frame.rename(columns=renamed).copy()
    missing = [column for column in SOURCE_COLUMNS if column not in result.columns]
    if missing:
        raise ValueError(f"В источнике отсутствуют обязательные столбцы: {', '.join(missing)}")
    result = result[SOURCE_COLUMNS].copy()

    for column in ("invoice_no", "stock_code", "description", "country"):
        result[column] = _as_text(result[column])

    result["quantity"] = pd.to_numeric(result["quantity"], errors="coerce")
    result["unit_price"] = pd.to_numeric(result["unit_price"], errors="coerce")
    source_dates = result["invoice_date"]
    parsed_dates = pd.to_datetime(source_dates, errors="coerce", format="ISO8601")
    needs_day_first = parsed_dates.isna() & source_dates.notna()
    if needs_day_first.any():
        parsed_dates.loc[needs_day_first] = pd.to_datetime(
            source_dates.loc[needs_day_first], errors="coerce", dayfirst=True
        )
    result["invoice_date"] = parsed_dates

    customer_numeric = pd.to_numeric(result["customer_id"], errors="coerce")
    customer_is_integer = customer_numeric.notna() & customer_numeric.mod(1).eq(0)
    result["customer_id"] = customer_numeric.where(customer_is_integer).astype("Int64")
    return result


def classify_and_deduplicate(normalized: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Remove exact duplicate rows and classify lines using documented rules."""
    duplicate_count = int(normalized.duplicated(subset=SOURCE_COLUMNS, keep="first").sum())
    clean = normalized.drop_duplicates(subset=SOURCE_COLUMNS, keep="first").copy()

    invoice = clean["invoice_no"].str.upper()
    is_cancellation = invoice.str.startswith("C", na=False)
    has_transaction_keys = clean["invoice_no"].notna() & clean["invoice_date"].notna()
    quantity = clean["quantity"]
    price = clean["unit_price"]

    conditions = [
        is_cancellation,
        quantity.lt(0) & has_transaction_keys,
        quantity.eq(0),
        price.le(0),
        quantity.gt(0) & price.gt(0) & has_transaction_keys,
    ]
    labels = [
        "cancellation",
        "return_or_adjustment",
        "zero_quantity",
        "nonpositive_price",
        "sale",
    ]
    clean["line_type"] = pd.Series(pd.NA, index=clean.index, dtype="string")
    for condition, label in zip(conditions, labels):
        clean.loc[condition & clean["line_type"].isna(), "line_type"] = label
    clean["line_type"] = clean["line_type"].fillna("invalid_transaction").astype("string")
    clean["line_value"] = clean["quantity"] * clean["unit_price"]
    return clean, duplicate_count


def _money(value: Any) -> float:
    if pd.isna(value):
        return 0.0
    return round(float(value), 2)


def analyze_frame(frame: pd.DataFrame) -> dict[str, Any]:
    """Return QA, headline metrics, and small aggregate tables."""
    normalized = normalize_input(frame)
    clean, duplicate_count = classify_and_deduplicate(normalized)
    valid_sales = clean.loc[clean["line_type"].eq("sale")].copy()
    return_rows = clean.loc[clean["line_type"].eq("return_or_adjustment")].copy()
    valid_price_returns = return_rows.loc[return_rows["unit_price"].gt(0)].copy()
    valid_cancellations = clean.loc[
        clean["line_type"].eq("cancellation")
        & clean["quantity"].lt(0)
        & clean["unit_price"].gt(0)
        & clean["invoice_no"].notna()
        & clean["invoice_date"].notna()
    ].copy()

    sales_total = _money(valid_sales["line_value"].sum())
    sales_orders = int(valid_sales["invoice_no"].nunique())
    returns_total = _money(valid_price_returns["line_value"].abs().sum())
    cancellations_total = _money(valid_cancellations["line_value"].abs().sum())

    raw_null_counts = {
        column: int(normalized[column].isna().sum()) for column in SOURCE_COLUMNS
    }
    nonpositive_price = clean["unit_price"].le(0) | clean["unit_price"].isna()
    noninteger_quantity = clean["quantity"].notna() & clean["quantity"].mod(1).ne(0)
    positive_prices = clean.loc[clean["unit_price"].gt(0), "unit_price"]
    cancellation_rows = clean["line_type"].eq("cancellation")
    quality = {
        "raw_rows": int(len(normalized)),
        "exact_duplicate_rows_removed": duplicate_count,
        "deduplicated_rows": int(len(clean)),
        "missing_values_raw": raw_null_counts,
        "rows_by_class_after_deduplication": {
            str(key): int(value)
            for key, value in clean["line_type"].value_counts(dropna=False).sort_index().items()
        },
        "negative_quantity_rows": int(clean["quantity"].lt(0).sum()),
        "zero_quantity_rows": int(clean["quantity"].eq(0).sum()),
        "nonpositive_or_missing_price_rows": int(nonpositive_price.sum()),
        "noninteger_quantity_rows": int(noninteger_quantity.sum()),
        "return_or_adjustment_rows_with_nonpositive_price": int(
            (clean["line_type"].eq("return_or_adjustment") & clean["unit_price"].le(0)).sum()
        ),
        "positive_unit_price_p99_gbp": _money(positive_prices.quantile(0.99)),
        "positive_unit_price_p999_gbp": _money(positive_prices.quantile(0.999)),
        "maximum_positive_unit_price_gbp": _money(positive_prices.max()),
        "positive_sale_unit_price_p99_gbp": _money(valid_sales["unit_price"].quantile(0.99)),
        "positive_sale_unit_price_p999_gbp": _money(valid_sales["unit_price"].quantile(0.999)),
        "maximum_positive_sale_unit_price_gbp": _money(valid_sales["unit_price"].max()),
        "maximum_positive_sale_line_quantity": _money(valid_sales["quantity"].max()),
        "invalid_or_missing_invoice_date_rows": int(clean["invoice_date"].isna().sum()),
        "invalid_or_missing_invoice_number_rows": int(clean["invoice_no"].isna().sum()),
        "cancellation_rows_with_nonnegative_quantity": int(
            (cancellation_rows & clean["quantity"].ge(0)).sum()
        ),
        "sale_rows_missing_customer_id": int(valid_sales["customer_id"].isna().sum()),
        "sale_rows_missing_country": int(valid_sales["country"].isna().sum()),
    }

    monthly = valid_sales.assign(month=valid_sales["invoice_date"].dt.to_period("M").astype(str))
    monthly = (
        monthly.groupby("month", as_index=False)
        .agg(
            positive_line_sales_gbp=("line_value", "sum"),
            positive_sales_orders=("invoice_no", "nunique"),
            positive_sales_lines=("invoice_no", "size"),
            units_sold=("quantity", "sum"),
        )
        .sort_values("month")
    )
    monthly_returns = valid_price_returns.assign(
        month=valid_price_returns["invoice_date"].dt.to_period("M").astype(str)
    ).groupby("month")["line_value"].apply(lambda values: values.abs().sum())
    monthly_cancellations = valid_cancellations.assign(
        month=valid_cancellations["invoice_date"].dt.to_period("M").astype(str)
    ).groupby("month")["line_value"].apply(lambda values: values.abs().sum())
    monthly = monthly.merge(
        monthly_returns.rename("return_or_adjustment_value_gbp_abs"),
        on="month",
        how="outer",
    ).merge(
        monthly_cancellations.rename("cancellation_value_gbp_abs"),
        on="month",
        how="outer",
    )
    monthly = monthly.sort_values("month")
    for column in (
        "positive_line_sales_gbp",
        "positive_sales_orders",
        "positive_sales_lines",
        "units_sold",
        "return_or_adjustment_value_gbp_abs",
        "cancellation_value_gbp_abs",
    ):
        monthly[column] = monthly[column].fillna(0)
    monthly["positive_line_sales_gbp"] = monthly["positive_line_sales_gbp"].round(2)
    monthly["return_or_adjustment_value_gbp_abs"] = monthly[
        "return_or_adjustment_value_gbp_abs"
    ].round(2)
    monthly["cancellation_value_gbp_abs"] = monthly["cancellation_value_gbp_abs"].round(2)
    monthly["aov_gbp"] = (
        monthly["positive_line_sales_gbp"] / monthly["positive_sales_orders"]
    ).round(2)
    monthly["mom_growth_pct"] = (
        monthly["positive_line_sales_gbp"].pct_change(fill_method=None).mul(100).round(2)
    )

    products = (
        valid_sales.groupby("stock_code", dropna=False)
        .agg(
            product_description=("description", "min"),
            positive_line_sales_gbp=("line_value", "sum"),
            units_sold=("quantity", "sum"),
            positive_sales_lines=("invoice_no", "size"),
            positive_sales_orders=("invoice_no", "nunique"),
        )
        .reset_index()
        .sort_values(["positive_line_sales_gbp", "stock_code"], ascending=[False, True])
        .head(10)
    )
    products["product_description"] = products["product_description"].fillna("(описание отсутствует)")
    products["positive_line_sales_gbp"] = products["positive_line_sales_gbp"].round(2)

    countries = (
        valid_sales.dropna(subset=["country"])
        .groupby("country")
        .agg(
            positive_line_sales_gbp=("line_value", "sum"),
            positive_sales_orders=("invoice_no", "nunique"),
            units_sold=("quantity", "sum"),
        )
        .reset_index()
        .sort_values(["positive_line_sales_gbp", "country"], ascending=[False, True])
        .head(10)
    )
    countries["positive_line_sales_gbp"] = countries["positive_line_sales_gbp"].round(2)

    summary = {
        "period_start": (
            str(clean["invoice_date"].min().date()) if clean["invoice_date"].notna().any() else None
        ),
        "period_end": (
            str(clean["invoice_date"].max().date()) if clean["invoice_date"].notna().any() else None
        ),
        "positive_line_sales_gbp": sales_total,
        "positive_sales_orders": sales_orders,
        "average_positive_order_value_gbp": _money(sales_total / sales_orders) if sales_orders else None,
        "units_in_positive_sale_lines": _money(valid_sales["quantity"].sum()),
        "customers_with_positive_sale_lines": int(valid_sales["customer_id"].nunique()),
        "return_or_adjustment_lines": int(len(return_rows)),
        "return_or_adjustment_lines_with_positive_price": int(len(valid_price_returns)),
        "return_or_adjustment_value_gbp_abs": returns_total,
        "cancellation_lines_with_negative_quantity": int(len(valid_cancellations)),
        "cancellation_value_gbp_abs": cancellations_total,
        "countries_in_positive_sales": int(valid_sales["country"].nunique(dropna=True)),
        "product_codes_in_positive_sales": int(valid_sales["stock_code"].nunique(dropna=True)),
        "sales_definition": "Valid non-cancellation rows with quantity > 0, unit_price > 0, invoice number and date present; sum(quantity * unit_price).",
        "return_definition": "Count non-cancellation rows with quantity < 0 and valid invoice/date. Monetary value uses only rows with unit_price > 0 and is not a confirmed refund amount.",
        "cancellation_definition": "Rows whose invoice number starts with C; monetary total uses only negative-quantity rows with positive unit price and valid invoice/date.",
        "warning": "Positive-line sales are not net revenue after returns or cancellations. No costs, margin, profit or discount fields are available.",
    }
    return {
        "summary": summary,
        "quality": quality,
        "monthly_sales": monthly,
        "top_products": products,
        "top_countries": countries,
        "normalized_raw": normalized,
        "clean_lines": clean,
    }


def download_source(data_dir: Path) -> Path:
    """Download and extract the official UCI archive into the ignored data folder."""
    data_dir.mkdir(parents=True, exist_ok=True)
    archive = data_dir / "uci_online_retail.zip"
    workbook = data_dir / "Online Retail.xlsx"
    if not workbook.exists():
        urllib.request.urlretrieve(DATASET_ZIP, archive)
        with zipfile.ZipFile(archive) as zipped:
            member = next((name for name in zipped.namelist() if name.lower().endswith(".xlsx")), None)
            if member is None:
                raise ValueError("В архиве UCI не найден файл XLSX")
            workbook.write_bytes(zipped.read(member))
    return workbook


def read_source(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".xlsx":
        return pd.read_excel(path)
    if suffix == ".csv":
        return pd.read_csv(path, encoding="utf-8-sig")
    raise ValueError("Поддерживаются файлы .xlsx и .csv")


def _json_default(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, Path)):
        return str(value)
    if hasattr(value, "item"):
        return value.item()
    raise TypeError(f"Не удалось сериализовать значение {type(value)!r}")


def write_outputs(result: dict[str, Any], output_dir: Path, postgres_csv: Path | None) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(result["summary"], ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    (output_dir / "data_quality.json").write_text(
        json.dumps(result["quality"], ensure_ascii=False, indent=2, default=_json_default) + "\n",
        encoding="utf-8",
    )
    for key, filename in (
        ("monthly_sales", "monthly_sales.csv"),
        ("top_products", "top_products.csv"),
        ("top_countries", "top_countries.csv"),
    ):
        result[key].to_csv(output_dir / filename, index=False, encoding="utf-8-sig")
    if postgres_csv is not None:
        postgres_csv.parent.mkdir(parents=True, exist_ok=True)
        result["normalized_raw"].to_csv(
            postgres_csv,
            index=False,
            columns=SOURCE_COLUMNS,
            date_format="%Y-%m-%d %H:%M:%S",
            na_rep="",
            encoding="utf-8",
        )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Очистка и анализ UCI Online Retail")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--input", type=Path, help="Путь к локальному XLSX или CSV")
    source.add_argument("--download", action="store_true", help="Скачать официальный файл с сайта UCI")
    parser.add_argument("--output-dir", type=Path, default=Path("results"))
    parser.add_argument("--postgres-csv", type=Path, default=Path("data/online_retail_for_postgres.csv"))
    parser.add_argument("--skip-postgres-csv", action="store_true")
    args = parser.parse_args()

    input_path = args.input if args.input is not None else download_source(Path("data"))
    if not input_path.exists():
        parser.error(f"Файл не найден: {input_path}")
    result = analyze_frame(read_source(input_path))
    write_outputs(result, args.output_dir, None if args.skip_postgres_csv else args.postgres_csv)
    print(json.dumps({"summary": result["summary"], "quality": result["quality"]}, ensure_ascii=False, indent=2))
    print(f"\nСводные результаты: {args.output_dir.resolve()}")
    if not args.skip_postgres_csv:
        print(f"CSV для PostgreSQL: {args.postgres_csv.resolve()}")


if __name__ == "__main__":
    main()

"""Build the three README charts from the committed aggregate CSVs.

Inputs (read only, never modified):
    results/monthly_sales.csv
    results/top_products.csv
    results/top_countries.csv

Outputs:
    docs/img/monthly_sales.png
    docs/img/top_products.png
    docs/img/top_countries.png

The script needs no network access and no copy of the UCI dataset, so the charts
can be rebuilt by anyone who clones the repository. It is deterministic: the
same CSVs produce byte-identical PNGs on a given matplotlib version.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib.ticker import FuncFormatter

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results"
OUT_DIR = ROOT / "docs" / "img"

MONTHS_RU = ["янв", "фев", "мар", "апр", "май", "июн",
             "июл", "авг", "сен", "окт", "ноя", "дек"]

INK = "#1f2933"
MUTED = "#52606d"
GRID = "#d9e2ec"
SALES = "#1f6f8b"
SALES_ALT = "#3f8f74"

FIGSIZE = (8.0, 4.6)  # 800 x 460 px at dpi=100


def _style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "axes.edgecolor": GRID,
            "axes.labelcolor": MUTED,
            "axes.titlecolor": INK,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "savefig.facecolor": "white",
        }
    )


def _shade(ax) -> None:
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=GRID, linewidth=0.8)
    ax.grid(axis="x", visible=False)
    ax.tick_params(length=0)
    for side in ("left", "bottom"):
        ax.spines[side].set_linewidth(0.8)


def _gbp(value: float) -> str:
    """Format pounds with spaces as thousand separators: 206 249."""
    return f"{value:,.0f}".replace(",", " ")


def _gbp_exact(value: float) -> str:
    """Format pounds with spaces and a comma decimal: 10 642 110,80."""
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def _millions(value: float) -> str:
    return f"{value:.1f}".replace(".", ",")


def _melt(value: float) -> float:
    return value / 1_000_000


def _read(name: str, required: list[str]) -> pd.DataFrame:
    path = RESULTS / name
    if not path.is_file():
        raise SystemExit(f"Не найден входной файл: {path}. Сначала запустите scripts/run_analysis.py.")
    frame = pd.read_csv(path, encoding="utf-8-sig")
    missing = [column for column in required if column not in frame.columns]
    if missing:
        raise SystemExit(f"В {name} нет столбцов: {', '.join(missing)}")
    return frame


def _finish(fig, ax, title: str, subtitle: str, path: Path, left: float) -> None:
    fig.text(
        0.03, 0.965, title,
        ha="left", va="top", fontsize=14, fontweight="bold", color=INK,
    )
    fig.text(
        0.03, 0.905, textwrap.fill(subtitle, width=108),
        ha="left", va="top", fontsize=8.5, color=MUTED, linespacing=1.4,
    )
    fig.subplots_adjust(left=left, right=0.97, top=0.80, bottom=0.16)
    fig.savefig(path, dpi=100, metadata={"Software": "ecommerce-sales-analysis"})
    plt.close(fig)


def monthly_chart(frame: pd.DataFrame) -> Path:
    frame = frame.sort_values("month").reset_index(drop=True)
    values = frame["positive_line_sales_gbp"].astype(float)
    labels = []
    for month in frame["month"].astype(str):
        year, number = month.split("-")
        labels.append(f"{MONTHS_RU[int(number) - 1]} {year[2:]}")

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=100)
    _style()
    ax.bar(range(len(values)), _melt(values), color=SALES, width=0.72, zorder=3)
    ax.set_ylim(0, _melt(values.max()) * 1.18)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=8.5)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda value, _pos: _millions(value)))
    ax.set_ylabel("Положительные продажи, млн £", fontsize=9)
    ax.set_xlim(-0.7, len(values) - 0.3)
    _shade(ax)

    total = _gbp_exact(values.sum())
    _finish(
        fig, ax,
        "Положительные продажи по месяцам",
        "Сумма строк с Quantity > 0 и UnitPrice > 0; возвраты и отмены не вычтены. "
        f"Всего за период: £{total}. Декабрь 2011 — неполный месяц (данные по 09.12.2011).",
        OUT_DIR / "monthly_sales.png",
        left=0.10,
    )
    return OUT_DIR / "monthly_sales.png"


def products_chart(frame: pd.DataFrame) -> Path:
    top = frame.sort_values("positive_line_sales_gbp", ascending=False).head(10)
    top = top.iloc[::-1].reset_index(drop=True)  # largest bar on top

    def shorten(text: str) -> str:
        text = str(text).strip()
        if len(text) <= 28:
            return text
        return text[:27].rstrip(" ,;") + "…"

    labels = [shorten(item) for item in top["product_description"]]
    values = top["positive_line_sales_gbp"].astype(float)

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=100)
    _style()
    bars = ax.barh(range(len(values)), values, color=SALES, height=0.66, zorder=3)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.set_xlim(0, values.max() * 1.20)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _pos: _gbp(value)))
    ax.set_xlabel("Положительные продажи, £", fontsize=9)
    _shade(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_width() + values.max() * 0.012,
            bar.get_y() + bar.get_height() / 2,
            _gbp(value), va="center", ha="left", fontsize=8, color=INK,
        )

    _finish(
        fig, ax,
        "Топ-10 кодов товара по положительным продажам",
        "Сумма строк с Quantity > 0 и UnitPrice > 0. Среди кодов есть доставка (DOT, POST) "
        "и Manual — это не всегда физический товар.",
        OUT_DIR / "top_products.png",
        left=0.31,
    )
    return OUT_DIR / "top_products.png"


def countries_chart(frame: pd.DataFrame) -> Path:
    top = frame.sort_values("positive_line_sales_gbp", ascending=False).head(10)
    top = top.iloc[::-1].reset_index(drop=True)

    labels = [str(item) for item in top["country"]]
    values = top["positive_line_sales_gbp"].astype(float)

    fig, ax = plt.subplots(figsize=FIGSIZE, dpi=100)
    _style()
    bars = ax.barh(range(len(values)), values, color=SALES_ALT, height=0.66, zorder=3)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8.5)
    ax.set_xlim(0, values.max() * 1.16)
    ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _pos: _gbp(value)))
    ax.set_xlabel("Положительные продажи, £", fontsize=9)
    _shade(ax)
    ax.grid(axis="y", visible=False)
    ax.grid(axis="x", color=GRID, linewidth=0.8)

    for bar, value in zip(bars, values):
        ax.text(
            bar.get_width() + values.max() * 0.012,
            bar.get_y() + bar.get_height() / 2,
            _gbp(value), va="center", ha="left", fontsize=8, color=INK,
        )

    _finish(
        fig, ax,
        "Топ-10 стран по положительным продажам",
        "Сумма строк с Quantity > 0 и UnitPrice > 0. Линейная шкала: "
        "Великобритания даёт основную часть суммы, остальные страны короче.",
        OUT_DIR / "top_countries.png",
        left=0.17,
    )
    return OUT_DIR / "top_countries.png"


def main() -> None:
    _style()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    monthly = _read("monthly_sales.csv", ["month", "positive_line_sales_gbp"])
    products = _read(
        "top_products.csv",
        ["stock_code", "product_description", "positive_line_sales_gbp"],
    )
    countries = _read(
        "top_countries.csv",
        ["country", "positive_line_sales_gbp"],
    )

    paths = [
        monthly_chart(monthly),
        products_chart(products),
        countries_chart(countries),
    ]
    for path in paths:
        print(f"{path.relative_to(ROOT)}: {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()

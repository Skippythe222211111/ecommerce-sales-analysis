import unittest

import pandas as pd

from src.analysis import analyze_frame, normalize_input


def sample_rows():
    rows = [
        ["10001", "A", "Regular sale", 10, "2011-01-01 10:00:00", 2.00, 10, "United Kingdom"],
        ["10001", "A", "Regular sale", 10, "2011-01-01 10:00:00", 2.00, 10, "United Kingdom"],
        ["10002", "B", "Return line", -2, "2011-01-02 10:00:00", 3.00, 10, "France"],
        ["C10003", "C", "Cancelled line", -1, "2011-01-03 10:00:00", 4.00, 10, "France"],
        ["10004", "D", "Sale without customer", 1, "2011-01-04 10:00:00", 1.00, None, "Germany"],
        ["10005", "E", "Invalid price", 1, "2011-01-05 10:00:00", 0.00, 11, "Germany"],
        ["10006", "F", "Zero quantity", 0, "2011-01-06 10:00:00", 2.00, 11, "Germany"],
        ["10007", "G", None, 2, "2011-01-07 10:00:00", 2.00, 11, "Germany"],
        ["10008", "H", "Negative line with zero price", -5, "2011-01-08 10:00:00", 0.00, 11, "Germany"],
    ]
    return pd.DataFrame(
        rows,
        columns=[
            "InvoiceNo",
            "StockCode",
            "Description",
            "Quantity",
            "InvoiceDate",
            "UnitPrice",
            "CustomerID",
            "Country",
        ],
    )


class AnalysisTests(unittest.TestCase):
    def test_requires_all_source_fields(self):
        with self.assertRaises(ValueError):
            normalize_input(pd.DataFrame({"InvoiceNo": ["1"]}))

    def test_deduplication_and_transaction_classes(self):
        result = analyze_frame(sample_rows())
        summary = result["summary"]
        quality = result["quality"]

        self.assertEqual(quality["raw_rows"], 9)
        self.assertEqual(quality["exact_duplicate_rows_removed"], 1)
        self.assertEqual(quality["deduplicated_rows"], 8)
        self.assertEqual(summary["positive_line_sales_gbp"], 25.0)
        self.assertEqual(summary["positive_sales_orders"], 3)
        self.assertEqual(summary["average_positive_order_value_gbp"], 8.33)
        self.assertEqual(summary["return_or_adjustment_lines"], 2)
        self.assertEqual(summary["return_or_adjustment_lines_with_positive_price"], 1)
        self.assertEqual(summary["return_or_adjustment_value_gbp_abs"], 6.0)
        self.assertEqual(summary["cancellation_value_gbp_abs"], 4.0)
        self.assertEqual(summary["customers_with_positive_sale_lines"], 2)
        self.assertEqual(quality["sale_rows_missing_customer_id"], 1)
        self.assertEqual(quality["nonpositive_or_missing_price_rows"], 2)
        self.assertEqual(quality["return_or_adjustment_rows_with_nonpositive_price"], 1)
        self.assertEqual(quality["zero_quantity_rows"], 1)

    def test_monthly_sales_does_not_net_returns_or_cancellations(self):
        result = analyze_frame(sample_rows())
        january = result["monthly_sales"].iloc[0]
        self.assertEqual(january["positive_line_sales_gbp"], 25.0)
        self.assertEqual(january["return_or_adjustment_value_gbp_abs"], 6.0)
        self.assertEqual(january["cancellation_value_gbp_abs"], 4.0)


if __name__ == "__main__":
    unittest.main()

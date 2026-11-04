-- All monetary values are in GBP, as supplied by UCI.
-- Positive-line sales are not net revenue after returns or cancellations.

-- 1. Headline metrics. Order denominator: distinct invoice numbers with at least
-- one valid positive sale line. Customer count excludes NULL customer IDs.
SELECT
    COUNT(*) FILTER (WHERE line_type = 'sale') AS positive_sale_lines,
    COUNT(DISTINCT invoice_no) FILTER (WHERE line_type = 'sale') AS positive_sales_orders,
    ROUND(SUM(line_value) FILTER (WHERE line_type = 'sale'), 2) AS positive_line_sales_gbp,
    ROUND(
        SUM(line_value) FILTER (WHERE line_type = 'sale')
        / NULLIF(COUNT(DISTINCT invoice_no) FILTER (WHERE line_type = 'sale'), 0),
        2
    ) AS average_positive_order_value_gbp,
    SUM(quantity) FILTER (WHERE line_type = 'sale') AS units_in_positive_sale_lines,
    COUNT(DISTINCT customer_id) FILTER (WHERE line_type = 'sale') AS customers_with_positive_sale_lines,
    COUNT(*) FILTER (WHERE line_type = 'return_or_adjustment') AS return_or_adjustment_lines,
    COUNT(*) FILTER (
        WHERE line_type = 'return_or_adjustment' AND unit_price > 0
    ) AS return_or_adjustment_lines_with_positive_price,
    COALESCE(ROUND(SUM(ABS(line_value)) FILTER (
        WHERE line_type = 'return_or_adjustment' AND unit_price > 0
    ), 2), 0)
        AS return_or_adjustment_value_gbp_abs,
    COUNT(*) FILTER (
        WHERE line_type = 'cancellation' AND quantity < 0 AND unit_price > 0
          AND invoice_no IS NOT NULL AND invoice_date IS NOT NULL
    ) AS cancellation_lines_with_negative_quantity,
    COALESCE(ROUND(SUM(ABS(line_value)) FILTER (
        WHERE line_type = 'cancellation' AND quantity < 0 AND unit_price > 0
          AND invoice_no IS NOT NULL AND invoice_date IS NOT NULL
    ), 2), 0) AS cancellation_value_gbp_abs,
    COUNT(DISTINCT country) FILTER (WHERE line_type = 'sale') AS countries_in_positive_sales,
    COUNT(DISTINCT stock_code) FILTER (WHERE line_type = 'sale') AS product_codes_in_positive_sales
FROM retail.online_retail_clean;

-- 2. Data quality. Duplicate count is measured by comparing raw rows with the
-- exact-deduplicated view. Missing-value counts refer to raw imported fields.
WITH duplicates AS (
    SELECT COUNT(*) - (SELECT COUNT(*) FROM retail.online_retail_clean) AS duplicate_rows_removed
    FROM retail.online_retail_raw
), raw_missing AS (
    SELECT
        COUNT(*) FILTER (WHERE invoice_no IS NULL) AS missing_invoice_no_rows,
        COUNT(*) FILTER (WHERE description IS NULL) AS missing_description_rows,
        COUNT(*) FILTER (WHERE customer_id IS NULL) AS missing_customer_id_rows,
        COUNT(*) FILTER (WHERE country IS NULL) AS missing_country_rows,
        COUNT(*) FILTER (WHERE invoice_date IS NULL) AS missing_invoice_date_rows
    FROM retail.online_retail_raw
)
SELECT
    (SELECT COUNT(*) FROM retail.online_retail_raw) AS raw_rows,
    (SELECT duplicate_rows_removed FROM duplicates) AS exact_duplicate_rows_removed,
    (SELECT COUNT(*) FROM retail.online_retail_clean) AS deduplicated_rows,
    raw_missing.missing_invoice_no_rows,
    raw_missing.missing_description_rows,
    raw_missing.missing_customer_id_rows,
    raw_missing.missing_country_rows,
    raw_missing.missing_invoice_date_rows,
    COUNT(*) FILTER (WHERE quantity < 0) AS negative_quantity_rows,
    COUNT(*) FILTER (WHERE quantity = 0) AS zero_quantity_rows,
    COUNT(*) FILTER (WHERE unit_price <= 0 OR unit_price IS NULL) AS nonpositive_or_missing_price_rows,
    COUNT(*) FILTER (
        WHERE line_type = 'return_or_adjustment' AND unit_price <= 0
    ) AS return_or_adjustment_rows_with_nonpositive_price,
    ROUND((PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY unit_price)
        FILTER (WHERE unit_price > 0))::NUMERIC, 2) AS positive_unit_price_p99_gbp,
    ROUND((PERCENTILE_CONT(0.999) WITHIN GROUP (ORDER BY unit_price)
        FILTER (WHERE unit_price > 0))::NUMERIC, 2) AS positive_unit_price_p999_gbp,
    MAX(unit_price) FILTER (WHERE unit_price > 0) AS maximum_positive_unit_price_gbp,
    ROUND((PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY unit_price)
        FILTER (WHERE line_type = 'sale'))::NUMERIC, 2) AS positive_sale_unit_price_p99_gbp,
    ROUND((PERCENTILE_CONT(0.999) WITHIN GROUP (ORDER BY unit_price)
        FILTER (WHERE line_type = 'sale'))::NUMERIC, 2) AS positive_sale_unit_price_p999_gbp,
    MAX(unit_price) FILTER (WHERE line_type = 'sale') AS maximum_positive_sale_unit_price_gbp,
    MAX(quantity) FILTER (WHERE line_type = 'sale') AS maximum_positive_sale_line_quantity,
    COUNT(*) FILTER (WHERE line_type = 'invalid_transaction') AS invalid_transaction_rows,
    COUNT(*) FILTER (
        WHERE line_type = 'cancellation' AND quantity >= 0
    ) AS cancellation_rows_with_nonnegative_quantity
FROM retail.online_retail_clean AS clean
CROSS JOIN duplicates
CROSS JOIN raw_missing
GROUP BY
    raw_missing.missing_invoice_no_rows,
    raw_missing.missing_description_rows,
    raw_missing.missing_customer_id_rows,
    raw_missing.missing_country_rows,
    raw_missing.missing_invoice_date_rows;

-- 3. Monthly positive-line sales, returns/adjustments and cancellation lines.
-- The month set comes from valid sale lines only (same as the Python export);
-- returns and cancellations are left-joined onto it and default to 0.
-- Month-over-month growth denominator is previous month's positive-line sales.
WITH monthly_sales AS (
    SELECT
        DATE_TRUNC('month', invoice_date)::DATE AS month,
        ROUND(SUM(line_value), 2) AS positive_line_sales_gbp,
        COUNT(DISTINCT invoice_no) AS positive_sales_orders,
        COUNT(*) AS positive_sales_lines,
        SUM(quantity) AS units_sold
    FROM retail.online_retail_clean
    WHERE line_type = 'sale'
    GROUP BY 1
), monthly_returns AS (
    SELECT
        DATE_TRUNC('month', invoice_date)::DATE AS month,
        ROUND(SUM(ABS(line_value)), 2) AS return_or_adjustment_value_gbp_abs
    FROM retail.online_retail_clean
    WHERE line_type = 'return_or_adjustment' AND unit_price > 0
      AND invoice_date IS NOT NULL
    GROUP BY 1
), monthly_cancellations AS (
    SELECT
        DATE_TRUNC('month', invoice_date)::DATE AS month,
        ROUND(SUM(ABS(line_value)), 2) AS cancellation_value_gbp_abs
    FROM retail.online_retail_clean
    WHERE line_type = 'cancellation' AND quantity < 0 AND unit_price > 0
      AND invoice_date IS NOT NULL
    GROUP BY 1
), monthly AS (
    SELECT
        s.month,
        s.positive_line_sales_gbp,
        s.positive_sales_orders,
        s.positive_sales_lines,
        s.units_sold,
        COALESCE(r.return_or_adjustment_value_gbp_abs, 0) AS return_or_adjustment_value_gbp_abs,
        COALESCE(c.cancellation_value_gbp_abs, 0) AS cancellation_value_gbp_abs
    FROM monthly_sales AS s
    LEFT JOIN monthly_returns AS r USING (month)
    LEFT JOIN monthly_cancellations AS c USING (month)
), with_previous AS (
    SELECT *, LAG(positive_line_sales_gbp) OVER (ORDER BY month) AS previous_month_sales_gbp
    FROM monthly
)
SELECT
    month,
    positive_line_sales_gbp,
    positive_sales_orders,
    positive_sales_lines,
    units_sold,
    return_or_adjustment_value_gbp_abs,
    cancellation_value_gbp_abs,
    ROUND(
        100 * (positive_line_sales_gbp - previous_month_sales_gbp)
        / NULLIF(previous_month_sales_gbp, 0), 2
    ) AS positive_sales_mom_growth_pct
FROM with_previous
ORDER BY month;

-- 4. Top product codes. Ranking and line/order counts use valid positive sale lines.
SELECT
    stock_code,
    COALESCE(MIN(description), '(описание отсутствует)') AS product_description,
    ROUND(SUM(line_value), 2) AS positive_line_sales_gbp,
    SUM(quantity) AS units_sold,
    COUNT(*) AS positive_sales_lines,
    COUNT(DISTINCT invoice_no) AS positive_sales_orders
FROM retail.online_retail_clean
WHERE line_type = 'sale'
GROUP BY stock_code
ORDER BY SUM(line_value) DESC, stock_code
LIMIT 10;

-- 5. Top countries. Sales amount includes valid positive lines; order count is
-- distinct positive-sale invoice number. Missing countries are excluded here.
SELECT
    country,
    ROUND(SUM(line_value), 2) AS positive_line_sales_gbp,
    COUNT(DISTINCT invoice_no) AS positive_sales_orders,
    SUM(quantity) AS units_sold
FROM retail.online_retail_clean
WHERE line_type = 'sale' AND country IS NOT NULL
GROUP BY country
ORDER BY SUM(line_value) DESC, country
LIMIT 10;

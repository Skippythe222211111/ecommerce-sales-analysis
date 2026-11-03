-- Invariant checks for the imported project table and analysis view.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM retail.online_retail_clean
        WHERE line_type = 'sale'
          AND (quantity <= 0 OR unit_price <= 0 OR invoice_no IS NULL
               OR invoice_date IS NULL OR invoice_no ILIKE 'C%')
    ) THEN
        RAISE EXCEPTION 'Sale classification contains an invalid row';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM retail.online_retail_clean
        WHERE line_type = 'cancellation' AND invoice_no NOT ILIKE 'C%'
    ) THEN
        RAISE EXCEPTION 'Cancellation classification does not match the UCI invoice prefix rule';
    END IF;

    IF (SELECT COUNT(*) FROM retail.online_retail_raw)
       < (SELECT COUNT(*) FROM retail.online_retail_clean) THEN
        RAISE EXCEPTION 'Deduplicated view has more rows than the raw table';
    END IF;

    RAISE NOTICE 'SQL validation passed: sales, cancellations and deduplication invariants hold.';
END;
$$;

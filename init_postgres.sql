-- Runs automatically on first start of the Postgres container
-- (mounted into /docker-entrypoint-initdb.d/).
-- Column names are quoted because they are mixed-case: pandas.to_sql and the
-- SQLAlchemy model in newapp.py both quote them, so they must match exactly.
CREATE TABLE IF NOT EXISTS sales_data (
    "InvoiceNo"   VARCHAR(20) NOT NULL,
    "StockCode"   VARCHAR(20) NOT NULL,
    "Description" TEXT,
    "Quantity"    INTEGER,
    "InvoiceDate" TIMESTAMP,
    "UnitPrice"   NUMERIC(10, 2),
    "CustomerID"  VARCHAR(20),
    "Country"     VARCHAR(50)
);

CREATE INDEX IF NOT EXISTS idx_sales_data_customer ON sales_data ("CustomerID");

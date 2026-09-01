"""
Week 1 — SQL aggregation layer.

Aggregates the raw DataCo order rows into two tidy tables using DuckDB SQL:

  outputs/demand_by_sku_month.csv   one row per (SKU, month): units, order lines, avg price
  outputs/leadtime_by_sku.csv       one row per SKU: mean / std of real shipping days

pandas then turns demand_by_sku_month into per-SKU demand statistics
(mean demand, sigma demand) and joins the lead-time table onto it.

Note on loading: DuckDB's CSV reader rejects this file (it has cp1252 bytes and
DuckDB validates encoding strictly). pandas reads it with encoding='latin-1',
then the DataFrame is registered as a DuckDB view — so the *aggregation* is still
100% SQL, only the file read happens in pandas.

Run from the repo root:
    python -m src.extract
"""

from pathlib import Path

import duckdb
import pandas as pd

RAW_CSV = Path("data/DataCoSupplyChainDataset.csv")
DEMAND_OUT = Path("outputs/demand_by_sku_month.csv")
LEADTIME_OUT = Path("outputs/leadtime_by_sku.csv")

# Source timestamps look like  1/31/2018 22:56  (US M/D/YYYY, no zero-padding)
ORDER_DATE_FORMAT = "%m/%d/%Y %H:%M"

DEMAND_BY_SKU_MONTH_SQL = f"""
SELECT
    "Product Card Id"                                          AS sku,
    any_value("Product Name")                                 AS product_name,
    date_trunc('month',
        strptime("order date (DateOrders)", '{ORDER_DATE_FORMAT}')) AS month,
    SUM("Order Item Quantity")                                AS units,
    COUNT(*)                                                  AS order_lines,
    AVG("Product Price")                                      AS avg_price
FROM raw
GROUP BY sku, month
ORDER BY sku, month
"""

# Lead-time stats are computed at the SKU grain (over every order for that SKU),
# not SKU x month — a single order in a month gives no usable standard deviation.
LEADTIME_BY_SKU_SQL = """
SELECT
    "Product Card Id"                        AS sku,
    COUNT(*)                                 AS n_orders,
    AVG("Days for shipping (real)")          AS avg_lead_time_days,
    STDDEV_SAMP("Days for shipping (real)")  AS std_lead_time_days
FROM raw
GROUP BY sku
ORDER BY sku
"""


def run() -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(RAW_CSV, encoding="latin-1")

    con = duckdb.connect()
    con.register("raw", raw)

    demand = con.sql(DEMAND_BY_SKU_MONTH_SQL).df()
    leadtime = con.sql(LEADTIME_BY_SKU_SQL).df()
    con.close()

    return demand, leadtime


if __name__ == "__main__":
    demand, leadtime = run()

    DEMAND_OUT.parent.mkdir(exist_ok=True)
    demand.to_csv(DEMAND_OUT, index=False)
    leadtime.to_csv(LEADTIME_OUT, index=False)

    print(f"demand_by_sku_month : {len(demand):>6,} rows  ->  {DEMAND_OUT}")
    print(f"leadtime_by_sku     : {len(leadtime):>6,} rows  ->  {LEADTIME_OUT}")
    print(f"SKUs: {demand['sku'].nunique()}   "
          f"months: {demand['month'].min():%Y-%m} .. {demand['month'].max():%Y-%m}")

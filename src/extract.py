"""
Week 1 — SQL aggregation layer.

Loads the raw DataCo CSV into DuckDB and aggregates it to a
SKU x month demand table. This is the SQL showcase: do the grouping
and the demand/lead-time statistics in SQL, then hand the result to
pandas.

Run from the repo root:
    python -m src.extract
"""

from pathlib import Path

import duckdb
import pandas as pd

RAW_CSV = Path("data/DataCoSupplyChainDataset.csv")
DEMAND_TABLE_OUT = Path("outputs/demand_by_sku_month.csv")


def build_demand_table(raw_csv: Path = RAW_CSV) -> pd.DataFrame:
    """
    Aggregate raw order rows -> one row per (SKU, month) with:
      - total_quantity        SUM("Order Item Quantity")
      - avg_price             AVG("Product Price")
      - avg_ship_days         AVG("Days for shipping (real)")     <- lead time
      - std_ship_days         STDDEV("Days for shipping (real)")  <- lead-time sigma

    TODO:
      - read RAW_CSV with read_csv_auto (DuckDB handles the latin-1 quirk
        better than pandas; if not, fall back to pandas encoding='latin-1')
      - GROUP BY "Product Card Id", date_trunc('month', "order date (DateOrders)")
      - keep lead time as its own column, do NOT hard-code a constant
    """
    con = duckdb.connect()
    # TODO: write the aggregation query here
    raise NotImplementedError


if __name__ == "__main__":
    df = build_demand_table()
    DEMAND_TABLE_OUT.parent.mkdir(exist_ok=True)
    df.to_csv(DEMAND_TABLE_OUT, index=False)
    print(f"wrote {len(df):,} rows -> {DEMAND_TABLE_OUT}")

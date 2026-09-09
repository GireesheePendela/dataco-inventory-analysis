# DataCo Inventory Analytics

End-to-end inventory analytics on real supply-chain transaction data:
**SQL (DuckDB) → pandas pipeline → Power BI report**.

The pipeline (SQL + Python) turns ~180k raw order rows into `outputs/sku_metrics.csv`,
one row per SKU. A Power BI report reads that single file — see [Dashboard](#dashboard).

> **v1 scope:** the inventory core only (turnover, ABC, EOQ, safety stock / reorder point,
> mismatch analysis). Logistics and optimization are planned extensions.

## Business question

> Across this catalog, where is working capital trapped in slow-moving inventory,
> and how should reorder policies change to free cash without dropping below a
> 95% service level?

## Data

DataCo Smart Supply Chain (Kaggle, CC0) — `DataCoSupplyChainDataset.csv`,
~180k order rows, 53 columns. The raw file is **not** committed (see `.gitignore`);
download it from Kaggle into `data/`.

**Known limitation:** the dataset has no on-hand inventory column — it is
order/transaction data. Target stock is *prescribed* from demand behaviour
(reorder point + safety stock) rather than read from a stock level. Turnover is
therefore labelled **"implied"**.

## Modelling assumptions (not in the data — supplied and documented here)

| Symbol | Meaning | Value | Justification |
|--------|---------|-------|---------------|
| `S` | ordering cost per order | **$75** | staff time to raise a PO, receive the shipment, and match the invoice; industry range ~$50–100 |
| `H_RATE` | annual holding cost as a fraction of unit price | **25%** | ~5% cost of capital + ~15% warehouse/insurance/handling + ~5% obsolescence & shrinkage (standard 20–30%). Applied to price, not a flat $/unit, so it scales across a $10–$2,000 catalogue. |
| service level | baseline (also tested at 90% / 99%) | 95% (z ≈ 1.65) | industry-standard default |

Defined in one place: `src/inventory.py` (top of file).

## Repo layout

```
data/        raw CSV (gitignored) + data dictionary
notebooks/   analysis.ipynb — the full analysis, all layers
src/         extract.py (SQL aggregation) + inventory.py (the analytical layers)
outputs/     sku_metrics.csv — the ONE finished file the Power BI report reads
             service_level_sensitivity.csv — 90/95/99% buffer comparison
report.pbix  Power BI report built on outputs/sku_metrics.csv
```

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt -r requirements-dev.txt
# 1. put DataCoSupplyChainDataset.csv in data/
# 2. work through notebooks/analysis.ipynb -> writes outputs/sku_metrics.csv
```

## Dashboard

`report.pbix` (Power BI Desktop) reads `outputs/sku_metrics.csv` — no live
connection, no heavy compute in the report. Views: KPI header (trapped cash, EOQ
saving, over-buffered SKU count), ABC Pareto, and a filterable reorder-point /
safety-stock table sliceable by ABC class and buffer flag, with a 90/95/99%
service-level selector. Screenshots below.

## Planned extensions

- **v2 — logistics:** transit time, on-time %, OTIF by carrier/region; feed real
  lead-time variability back into safety stock.
- **v2 — live data:** re-point the extraction step at a self-polled public API.
- **v3 — optimization:** replace closed-form EOQ with a solver once real
  constraints (capacity, budget, multi-echelon) are added.

"""
Thin Streamlit display layer.

RULE: this file only READS outputs/sku_metrics.csv. No aggregation, no DuckDB,
no heavy compute here — that all happened in the notebook / src/ and was baked
into the CSV. This keeps the deployed app well under Streamlit's memory limit.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

METRICS = Path("outputs/sku_metrics.csv")

st.set_page_config(page_title="DataCo Inventory Analytics", layout="wide")


@st.cache_data
def load_metrics() -> pd.DataFrame:
    return pd.read_csv(METRICS)


st.title("DataCo Inventory Analytics")
st.caption("v1 — inventory core. Turnover is 'implied' (no on-hand column in the source data).")

if not METRICS.exists():
    st.warning("outputs/sku_metrics.csv not found — run the notebook / src pipeline first.")
    st.stop()

df = load_metrics()

# 1. KPI header ------------------------------------------------------------
# TODO: implied turnover, total trapped cash, % SKUs mis-buffered

# 2. ABC Pareto chart ---------------------------------------------------
# TODO: plotly bar + cumulative line

# 3. Filterable reorder-point / safety-stock table -----------------------
# TODO: filter by ABC class + buffer flag; color-code the flag
# TODO: service-level selector that SWITCHES BETWEEN precomputed 90/95/99
#       columns (display only — never recompute here)

st.dataframe(df, use_container_width=True)

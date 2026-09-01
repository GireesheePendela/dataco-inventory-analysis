"""
Week 2 — the four analytical layers, as reusable functions.

Input:  per-SKU demand + lead-time stats (from src/extract.py output).
Output: outputs/sku_metrics.csv  (one row per SKU; the ONLY file app.py reads).

Every function takes a DataFrame and returns a DataFrame with new columns,
so they can be chained in the notebook.
"""

from __future__ import annotations

import math

import pandas as pd

# ---------------------------------------------------------------------------
# ASSUMPTIONS — the dataset does NOT contain these. You supply and document them.
# Revisit these numbers in the README with a one-line justification each.
# ---------------------------------------------------------------------------
S = 50.0          # ordering cost per order ($/order)         <-- TODO justify
H = 0.25          # holding cost per unit per year ($/unit/yr) <-- TODO justify
                  # (often expressed as a % of unit price; decide which and note it)

Z_BY_SERVICE_LEVEL = {
    0.90: 1.2816,
    0.95: 1.6449,
    0.99: 2.3263,
}
BASELINE_SERVICE_LEVEL = 0.95


def annualize_demand(df: pd.DataFrame) -> pd.DataFrame:
    """Scale the observed demand up to an annual figure D (used by ABC and EOQ)."""
    raise NotImplementedError


def layer1_turnover(df: pd.DataFrame) -> pd.DataFrame:
    """
    Implied inventory turnover and days-of-supply per SKU.
    No on-hand column exists, so average inventory is DERIVED (e.g. EOQ/2 or a
    demand-based proxy). Label every output column 'implied_*'. Flag slow movers.
    """
    raise NotImplementedError


def layer2_abc(df: pd.DataFrame) -> pd.DataFrame:
    """
    ABC classification.
    annual_consumption_value = avg_price * annual_demand
    -> sort desc -> cumulative % -> A (<=80%), B (<=95%), C (rest).
    Also return the data needed to plot the Pareto curve.
    """
    raise NotImplementedError


def layer3_eoq(df: pd.DataFrame, s: float = S, h: float = H) -> pd.DataFrame:
    """EOQ = sqrt(2 * D * s / h) per SKU. Compare to observed order sizing."""
    raise NotImplementedError


def layer4_safety_stock(
    df: pd.DataFrame, service_level: float = BASELINE_SERVICE_LEVEL
) -> pd.DataFrame:
    """
    safety_stock  = z * sigma_demand * sqrt(lead_time)
    reorder_point = (avg_demand * lead_time) + safety_stock
    z from Z_BY_SERVICE_LEVEL. lead_time / sigma come from 'Days for shipping (real)'.
    Keep lead_time as a passed-in column, never a literal.
    """
    raise NotImplementedError


def total_cost(order_qty: float, d: float, s: float = S, h: float = H) -> float:
    """
    Annual inventory cost objective: ordering + holding.
        (d / order_qty) * s  +  (order_qty / 2) * h
    Isolated on purpose — this becomes the objective for the v3 optimization layer.
    """
    return (d / order_qty) * s + (order_qty / 2.0) * h


def mismatch_analysis(df: pd.DataFrame) -> pd.DataFrame:
    """
    The punchline: cross-tab ABC class vs. implied stock position.
    Where is the catalog over-buffered (trapped cash) vs. under-buffered
    (stockout risk)? Quantify trapped $ — this is the headline number.
    """
    raise NotImplementedError


def sensitivity_table(df: pd.DataFrame) -> pd.DataFrame:
    """Recompute safety stock / buffer cash at 90 / 95 / 99% service level."""
    raise NotImplementedError

"""
The four analytical layers, as reusable functions.

Input:  per-SKU demand + lead-time stats  (outputs/sku_demand_profile.csv).
Output: outputs/sku_metrics.csv  (one row per SKU; the ONLY file app.py reads).

Every function takes a DataFrame and returns a copy with new columns, so they
can be chained in the notebook.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# ASSUMPTIONS — the dataset does NOT contain these. Supplied and documented here
# and in the README. Change them in ONE place.
# ---------------------------------------------------------------------------
S = 75.0        # ordering cost per order ($/order): staff time to raise a PO,
                # receive the shipment, and match the invoice. Typical small-
                # operation figure; industry range ~$50-100.

H_RATE = 0.25   # annual holding cost as a FRACTION OF UNIT PRICE:
                # ~5% cost of capital + ~15% warehouse/insurance/handling
                # + ~5% obsolescence & shrinkage. Standard 20-30% range.
                # Applied to price, not a flat $/unit, so it scales across a
                # catalogue spanning $10 to $2,000 items.

MONTHS_PER_YEAR = 12
DAYS_PER_YEAR = 365

Z_BY_SERVICE_LEVEL = {
    0.90: 1.2816,
    0.95: 1.6449,
    0.99: 2.3263,
}
BASELINE_SERVICE_LEVEL = 0.95


def holding_cost_per_unit(price: pd.Series | float) -> pd.Series | float:
    """Annual $ cost of holding one unit, given its price."""
    return H_RATE * price


def _eoq(annual_demand: pd.Series, price: pd.Series, s: float = S) -> pd.Series:
    """Economic order quantity = sqrt(2 * D * S / H_unit)."""
    return np.sqrt(2.0 * annual_demand * s / holding_cost_per_unit(price))


def annualize_demand(df: pd.DataFrame) -> pd.DataFrame:
    """Add annual_demand (units/year) by scaling the mean monthly rate up by 12.

    Scales the *rate*, so SKUs with only a few months of history are still put
    on an annual footing rather than penalised for a short observation window.
    """
    out = df.copy()
    out["annual_demand"] = out["mean_monthly_demand"] * MONTHS_PER_YEAR
    out["annual_demand_value"] = out["annual_demand"] * out["avg_price"]
    return out


def layer1_turnover(df: pd.DataFrame, n_tiers: int = 3) -> pd.DataFrame:
    """Layer 1 — implied inventory turnover, days-of-supply, and velocity tier.

    There is no on-hand column, so average inventory is DERIVED from the classic
    sawtooth cycle-stock model: stock falls linearly from a full order quantity
    to zero, so average cycle stock = EOQ / 2. (Layer 4 adds the safety-stock
    component; here we keep it to cycle stock.)

        implied_turns          = annual_demand / (EOQ / 2)
        implied_days_of_supply = 365 / implied_turns

    IMPORTANT: because the proxy assumes cost-optimal (EOQ) ordering, these
    numbers are a BEST-CASE benchmark. They rank SKUs by relative velocity; they
    do NOT prove overstocking, which would need a real on-hand level. So Layer 1
    outputs a relative 'velocity_tier' (Slow / Medium / Fast by tercile of turns)
    rather than an absolute slow/fast verdict. slow_mover = bottom tier.

    Needs annualize_demand() first. Does not use sigma, so 'insufficient_history'
    SKUs need no special case here.
    """
    out = df.copy()
    out["implied_eoq"] = _eoq(out["annual_demand"], out["avg_price"])
    out["implied_avg_inventory_units"] = out["implied_eoq"] / 2.0
    out["implied_avg_inventory_value"] = (
        out["implied_avg_inventory_units"] * out["avg_price"]
    )
    out["implied_turns"] = out["annual_demand"] / out["implied_avg_inventory_units"]
    out["implied_days_of_supply"] = DAYS_PER_YEAR / out["implied_turns"]

    labels = ["Slow", "Medium", "Fast"][:n_tiers]
    out["velocity_tier"] = pd.qcut(out["implied_turns"], q=n_tiers, labels=labels)
    out["slow_mover"] = out["velocity_tier"] == "Slow"
    return out


ABC_CUTOFFS = {"A": 0.80, "B": 0.95}  # cumulative share of annual_demand_value


def layer2_abc(df: pd.DataFrame) -> pd.DataFrame:
    """Layer 2 — ABC classification by annual consumption value.

    Sorts SKUs descending by annual_demand_value (needs annualize_demand() to
    have run first), then classifies by cumulative share of total value:
        A = cumulative <= 80%, B = cumulative <= 95%, C = the rest.

    Adds: value_rank, cumulative_value, cumulative_pct, abc_class.
    The returned frame is already sorted and carries cumulative_pct, so it's
    exactly what the notebook needs to plot the Pareto curve (bar = value per
    SKU in rank order, line = cumulative_pct).
    """
    out = df.sort_values("annual_demand_value", ascending=False).reset_index(drop=True)
    out["value_rank"] = out.index + 1
    out["cumulative_value"] = out["annual_demand_value"].cumsum()
    out["cumulative_pct"] = out["cumulative_value"] / out["annual_demand_value"].sum()

    out["abc_class"] = "C"
    out.loc[out["cumulative_pct"] <= ABC_CUTOFFS["B"], "abc_class"] = "B"
    out.loc[out["cumulative_pct"] <= ABC_CUTOFFS["A"], "abc_class"] = "A"
    return out


def layer3_eoq(df: pd.DataFrame, s: float = S) -> pd.DataFrame:
    """EOQ per SKU (see _eoq). Compare to observed order sizing."""
    raise NotImplementedError


def layer4_safety_stock(
    df: pd.DataFrame, service_level: float = BASELINE_SERVICE_LEVEL
) -> pd.DataFrame:
    """
    safety_stock  = z * sigma_demand * sqrt(lead_time)
    reorder_point = (avg_demand * lead_time) + safety_stock
    z from Z_BY_SERVICE_LEVEL. 'insufficient_history' SKUs use a class-level
    sigma fallback, not a per-SKU one.
    """
    raise NotImplementedError


def total_cost(order_qty: float, d: float, h_unit: float, s: float = S) -> float:
    """
    Annual inventory cost objective: ordering + holding.
        (d / order_qty) * s  +  (order_qty / 2) * h_unit
    Isolated on purpose — this becomes the objective for the v3 optimization layer.
    """
    return (d / order_qty) * s + (order_qty / 2.0) * h_unit


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

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
    """Layer 3 — economic order quantity per SKU.

        eoq = sqrt(2 * D * S / H_unit)

    Same value as Layer 1's implied_eoq; there it was an inventory proxy, here
    it is examined as an ordering policy and priced.

    Adds:
        eoq                  cost-minimising order quantity (units)
        eoq_orders_per_year  D / eoq
        eoq_cycle_days       365 / eoq_orders_per_year
        eoq_annual_cost      ordering + holding cost at eoq (the minimum)
        monthly_order_size   naive baseline: one month of demand per order
        monthly_annual_cost  ordering + holding cost under the monthly baseline
        eoq_saving_vs_monthly    monthly_annual_cost - eoq_annual_cost
        eoq_saving_pct           saving as a share of the monthly-baseline cost

    Note: the dataset records customer sales, not the business's own purchase
    orders, so real supplier order sizing is not observable. The comparison is
    against a common default policy (reorder monthly) rather than actuals.

    Needs annualize_demand() first (uses annual_demand, avg_price,
    mean_monthly_demand).
    """
    out = df.copy()
    h_unit = holding_cost_per_unit(out["avg_price"])

    out["eoq"] = _eoq(out["annual_demand"], out["avg_price"], s)
    out["eoq_orders_per_year"] = out["annual_demand"] / out["eoq"]
    out["eoq_cycle_days"] = DAYS_PER_YEAR / out["eoq_orders_per_year"]
    out["eoq_annual_cost"] = total_cost(out["eoq"], out["annual_demand"], h_unit, s)

    out["monthly_order_size"] = out["mean_monthly_demand"]
    out["monthly_annual_cost"] = total_cost(
        out["monthly_order_size"], out["annual_demand"], h_unit, s
    )
    out["eoq_saving_vs_monthly"] = out["monthly_annual_cost"] - out["eoq_annual_cost"]
    out["eoq_saving_pct"] = out["eoq_saving_vs_monthly"] / out["monthly_annual_cost"]
    return out


def layer4_safety_stock(
    df: pd.DataFrame, service_level: float = BASELINE_SERVICE_LEVEL
) -> pd.DataFrame:
    """Layer 4 — safety stock and reorder point per SKU.

        safety_stock  = z * sigma_daily_demand * sqrt(lead_time_days)
        reorder_point = avg_daily_demand * lead_time_days + safety_stock

    Everything is put on a DAILY footing first: annual_demand / 365 for the mean,
    and monthly sigma scaled down by sqrt(days_per_month) for the daily sigma
    (square-root-of-time rule). Lead time is already in days.

    Only demand variability is buffered here; lead-time variability
    (std_lead_time_days) is carried through untouched as the bridge to the v2
    logistics layer, and the tight lead-time spread in this data (~1.6 days)
    means it would move the numbers little.

    insufficient_history SKUs (and the 9 with a NaN monthly sigma) do NOT get a
    per-SKU sigma. They borrow the median coefficient of variation
    (sigma / mean) of their ABC class and apply it to their OWN mean demand, so
    a low-volume item is not handed a high-volume item's absolute sigma.
    Overall median CV is used if a class has no reliable SKUs. sigma_source
    records which path each row took.

    Columns added: avg_daily_demand, sigma_daily_demand, sigma_source,
    demand_over_leadtime, safety_stock_{90,95,99}, reorder_point_{90,95,99},
    and unsuffixed safety_stock / reorder_point / safety_stock_value at the
    chosen service_level.
    """
    out = df.copy()
    days_per_month = DAYS_PER_YEAR / MONTHS_PER_YEAR

    out["avg_daily_demand"] = out["annual_demand"] / DAYS_PER_YEAR
    sigma_daily = out["std_monthly_demand"] / np.sqrt(days_per_month)

    reliable = (~out["insufficient_history"]) & sigma_daily.notna()
    cv = sigma_daily[reliable] / out.loc[reliable, "avg_daily_demand"]
    class_cv = cv.groupby(out.loc[reliable, "abc_class"]).median()
    overall_cv = cv.median()

    out["sigma_daily_demand"] = sigma_daily
    need_fallback = ~reliable
    fallback_cv = out.loc[need_fallback, "abc_class"].map(class_cv).fillna(overall_cv)
    out.loc[need_fallback, "sigma_daily_demand"] = (
        fallback_cv.to_numpy() * out.loc[need_fallback, "avg_daily_demand"].to_numpy()
    )
    out["sigma_source"] = np.where(need_fallback, "class_fallback", "per_sku")

    out["demand_over_leadtime"] = out["avg_daily_demand"] * out["avg_lead_time_days"]

    for lvl, z in Z_BY_SERVICE_LEVEL.items():
        tag = str(round(lvl * 100))
        ss = z * out["sigma_daily_demand"] * np.sqrt(out["avg_lead_time_days"])
        out[f"safety_stock_{tag}"] = ss
        out[f"reorder_point_{tag}"] = out["demand_over_leadtime"] + ss

    tag = str(round(service_level * 100))
    out["safety_stock"] = out[f"safety_stock_{tag}"]
    out["reorder_point"] = out[f"reorder_point_{tag}"]
    out["safety_stock_value"] = out["safety_stock"] * out["avg_price"]
    return out


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

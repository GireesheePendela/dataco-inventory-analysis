"""
Build the GitHub Pages site (docs/index.html) from the finished outputs.

Reads outputs/sku_metrics.csv and outputs/service_level_sensitivity.csv, the chart
images saved inside notebooks/analysis.ipynb, and the Power BI screenshots in
docs/assets/powerbi-*.png. Writes a static, self-contained page to docs/. Every figure on the page is
computed from the CSVs, so it cannot drift from the analysis.

Run from the repo root:
    python -m src.build_site
"""

from __future__ import annotations

import base64
import html
import json
import struct
from pathlib import Path

import pandas as pd

from src.inventory import sigma_source_split

DOCS = Path("docs")
ASSETS = DOCS / "assets"
REPO = "https://github.com/GireesheePendela/dataco-inventory-analysis"
SITE = "https://gireesheependela.github.io/dataco-inventory-analysis"

# From the notebook's audit section; the raw CSV is not committed, so these are
# recorded here rather than recomputed.
AUDIT = [
    ("Order rows", "180,519"),
    ("Columns", "53"),
    ("Date range", "1 Jan 2015 – 31 Jan 2018 (37 months)"),
    ("Distinct SKUs", "118"),
    ("Nulls in the 5 key columns", "0"),
    ("Order quantity", "1 – 5 units, no zeros or negatives"),
    ("Product price", "$9.99 – $1,999.99, no zeros"),
    ("Real shipping days (lead time)", "0 – 6 days"),
    ("Orders with negative profit", "33,784 (≈19%) — kept in as signal"),
]

# (slug, title, caption) for the 8 charts saved in the notebook, in notebook order.
CHARTS = [
    ("units-per-sku", "Total units sold per SKU",
     "Demand is right-skewed: a handful of products sell most of the units."),
    ("one-sku-monthly", "One SKU's monthly demand",
     "Spot-check of the time axis for the top-selling SKU before aggregating."),
    ("turnover", "Implied days of supply, and value by velocity tier",
     "Left: spread of implied days of supply across the catalogue. Right: annual "
     "demand value by velocity tier."),
    ("pareto", "ABC Pareto curve",
     "SKUs ranked by annual demand value (bars) with the cumulative share (line); "
     "dashed lines mark the 80% and 95% class cut-offs."),
    ("eoq", "EOQ versus a monthly-reorder baseline",
     "Left: EOQ order size against one month of demand, per SKU (below the line = "
     "EOQ orders less, more often). Right: yearly saving by ABC class."),
    ("buffer-capital", "Safety-stock capital by class and service level",
     "Left: buffer dollars by ABC class at 90/95/99% service. Right: reorder point "
     "against safety stock at 95%."),
    ("mismatch", "Buffer intensity versus value, and capital by buffer flag",
     "Left: buffer dollars per dollar of throughput, against annual value (log "
     "scale) — independent of ABC class. Right: safety-stock capital by flag."),
    ("sensitivity", "Buffer capital versus service level",
     "How much safety-stock capital each ABC class needs as service rises from 90% "
     "to 99%."),
]

SCREENSHOTS = [
    ("overview", "Overview page",
     "KPI cards, the ABC Pareto curve and value by class."),
    ("reorder-policy", "Reorder Policy page",
     "Every SKU's safety stock and reorder point, with a 90/95/99% service-level "
     "selector and over-buffered rows flagged in orange."),
    ("sensitivity", "Sensitivity page",
     "Buffer capital against service level, by ABC class."),
]


def esc(x) -> str:
    return html.escape(str(x))


def money(x: float, d: int = 0) -> str:
    return f"${x:,.{d}f}"


def kmoney(x: float) -> str:
    return f"${x / 1000:,.0f}K"


def table(headers, rows, num_cols=(), caption: str | None = None) -> str:
    head = "".join(
        f'<th class="num">{esc(h)}</th>' if i in num_cols else f"<th>{esc(h)}</th>"
        for i, h in enumerate(headers)
    )
    body = "".join(
        "<tr>"
        + "".join(
            f'<td class="num">{c}</td>' if i in num_cols else f"<td>{c}</td>"
            for i, c in enumerate(r)
        )
        + "</tr>"
        for r in rows
    )
    cap = f"<caption>{esc(caption)}</caption>" if caption else ""
    return (
        f'<div class="tablewrap"><table>{cap}<thead><tr>{head}</tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def notebook_pngs() -> list[bytes]:
    nb = json.loads(Path("notebooks/analysis.ipynb").read_text(encoding="utf-8"))
    out = []
    for cell in nb["cells"]:
        for o in cell.get("outputs", []):
            png = o.get("data", {}).get("image/png")
            if png:
                out.append(base64.b64decode("".join(png) if isinstance(png, list) else png))
    return out


def figure(slug: str, title: str, caption: str, size: tuple[int, int]) -> str:
    w, h = size
    return (
        f'<figure class="fig"><img src="assets/chart-{slug}.png" width="{w}" '
        f'height="{h}" loading="lazy" alt="{esc(title)}. {esc(caption)}">'
        f"<figcaption><strong>{esc(title)}.</strong> {esc(caption)}</figcaption></figure>"
    )


def build() -> None:
    m = pd.read_csv("outputs/sku_metrics.csv")
    sens = pd.read_csv("outputs/service_level_sensitivity.csv")

    # ---- charts + screenshots -> docs/assets ---------------------------------
    pngs = notebook_pngs()
    if len(pngs) != len(CHARTS):
        raise SystemExit(f"expected {len(CHARTS)} notebook charts, found {len(pngs)}")
    ASSETS.mkdir(parents=True, exist_ok=True)
    (DOCS / ".nojekyll").touch()
    sizes = {}
    for (slug, *_), data in zip(CHARTS, pngs):
        (ASSETS / f"chart-{slug}.png").write_bytes(data)
        sizes[slug] = struct.unpack(">II", data[16:24])
    for slug, *_ in SCREENSHOTS:
        shot = ASSETS / f"powerbi-{slug}.png"
        if not shot.exists():
            raise SystemExit(f"missing screenshot {shot} (save the Power BI page screenshots there)")
        sizes[f"powerbi-{slug}"] = struct.unpack(">II", shot.read_bytes()[16:24])

    # ---- headline numbers ----------------------------------------------------
    n_sku = len(m)
    total_value = m.annual_demand_value.sum()
    a = m[m.abc_class == "A"]
    a_share = a.annual_demand_value.sum() / total_value
    eoq_cost, monthly_cost = m.eoq_annual_cost.sum(), m.monthly_annual_cost.sum()
    eoq_saving = m.eoq_saving_vs_monthly.sum()
    lvl = {r.service_level: r.buffer_value for r in sens[sens.abc_class == "ALL"].itertuples()}
    ss90, ss95, ss99 = lvl[0.90], lvl[0.95], lvl[0.99]
    split = sigma_source_split(m).set_index("sigma_source")
    trapped = split.loc["total", "trapped_cash"]
    trapped_meas = split.loc["per_sku", "trapped_cash"]
    trapped_est = split.loc["class_fallback", "trapped_cash"]
    n_over = int(split.loc["total", "over_buffered_skus"])
    n_over_meas = int(split.loc["per_sku", "over_buffered_skus"])
    n_over_est = int(split.loc["class_fallback", "over_buffered_skus"])
    n_est = int(split.loc["class_fallback", "skus"])
    cap_est_share = split.loc["class_fallback", "safety_stock_capital"] / split.loc["total", "safety_stock_capital"]
    trapped_est_share = trapped_est / trapped
    uplift_a = ((a.safety_stock_99 - a.safety_stock_95) * a.avg_price).sum()
    uplift_all = ss99 - ss95
    uplift_a_est = (
        (a[a.sigma_source == "class_fallback"].safety_stock_99
         - a[a.sigma_source == "class_fallback"].safety_stock_95)
        * a[a.sigma_source == "class_fallback"].avg_price
    ).sum()
    est = m.sigma_source == "class_fallback"
    b = m[m.abc_class == "B"]
    b_heavy = int((b.buffer_intensity_tier == "Heavy").sum())
    b_heavy_est = int(((b.buffer_intensity_tier == "Heavy") & (b.sigma_source == "class_fallback")).sum())
    b_est = int((b.sigma_source == "class_fallback").sum())
    a_est = int((a.sigma_source == "class_fallback").sum())

    def tile(big, label, note):
        return (f'<div class="tile"><div class="big">{esc(big)}</div>'
                f'<div class="lbl">{esc(label)}</div><div class="note">{esc(note)}</div></div>')

    tiles = "".join([
        tile(str(n_sku), "SKUs analysed", "180,519 order rows, 2015 – 2018"),
        tile(f"{a_share:.0%}", "of value in the 16 class-A SKUs", f"{len(a) / n_sku:.0%} of the catalogue"),
        tile(kmoney(eoq_saving), "yearly saving from EOQ ordering",
             f"{eoq_saving / monthly_cost:.0%} below a monthly-reorder baseline"),
        tile(kmoney(ss95), "safety-stock capital at 95% service",
             f"{kmoney(ss90)} at 90% · {kmoney(ss99)} at 99%"),
        tile(kmoney(trapped), "trapped in over-buffered SKUs", f"{n_over} class B/C SKUs"),
        tile(kmoney(trapped_meas), "of that rests on measured data",
             f"{kmoney(trapped_est)} rests on estimates"),
    ])

    # ---- tables --------------------------------------------------------------
    tier_rows = []
    for t in ["Slow", "Medium", "Fast"]:
        g = m[m.velocity_tier == t]
        tier_rows.append([t, len(g), f"{g.implied_turns.median():.1f}",
                          f"{g.implied_days_of_supply.median():.0f}",
                          money(g.avg_price.median(), 2), money(g.annual_demand_value.median())])
    tier_tbl = table(["Velocity tier", "SKUs", "Median turns / yr", "Median days of supply",
                      "Median price", "Median annual value"], tier_rows, num_cols=range(1, 6))
    slow = m[m.velocity_tier == "Slow"]
    fast = m[m.velocity_tier == "Fast"]

    abc_rows = []
    for c in "ABC":
        g = m[m.abc_class == c]
        abc_rows.append([c, len(g), f"{len(g) / n_sku:.0%}", money(g.annual_demand_value.sum()),
                         f"{g.annual_demand_value.sum() / total_value:.1%}"])
    abc_rows.append(["Total", n_sku, "100%", money(total_value), "100%"])
    abc_tbl = table(["Class", "SKUs", "% of SKUs", "Annual demand value", "% of value"],
                    abc_rows, num_cols=range(1, 5))

    eoq_rows = []
    for c in "ABC":
        g = m[m.abc_class == c]
        eoq_rows.append([c, money(g.eoq_annual_cost.sum()), money(g.monthly_annual_cost.sum()),
                         money(g.eoq_saving_vs_monthly.sum()),
                         f"{g.eoq_saving_vs_monthly.sum() / g.monthly_annual_cost.sum():.0%}"])
    eoq_rows.append(["Total", money(eoq_cost), money(monthly_cost), money(eoq_saving),
                     f"{eoq_saving / monthly_cost:.0%}"])
    eoq_tbl = table(["Class", "Cost at EOQ", "Cost, monthly reorder", "Saving", "Saving %"],
                    eoq_rows, num_cols=range(1, 5))

    top_ss = m.sort_values("safety_stock_value", ascending=False).head(10)
    ss_tbl = table(
        ["SKU", "Product", "Class", "Sigma source", "Safety stock (units)", "Reorder point (units)",
         "Safety-stock $"],
        [[r.sku, esc(r.product_name), r.abc_class, r.sigma_source.replace("_", " "),
          f"{r.safety_stock_95:,.1f}", f"{r.reorder_point_95:,.1f}", money(r.safety_stock_value)]
         for r in top_ss.itertuples()],
        num_cols=(0, 4, 5, 6), caption="Ten largest buffers at 95% service")

    xt = pd.crosstab(m.abc_class, m.buffer_intensity_tier).reindex(columns=["Light", "Medium", "Heavy"], fill_value=0)
    xt_tbl = table(["ABC class", "Light", "Medium", "Heavy"],
                   [[c, *[int(v) for v in xt.loc[c]]] for c in "ABC"], num_cols=(1, 2, 3),
                   caption="SKUs by ABC class and buffer-intensity tier")

    top_over = m[m.buffer_flag == "over_buffered"].sort_values("excess_buffer_value", ascending=False).head(10)
    over_tbl = table(
        ["SKU", "Product", "Class", "Sigma source", "Buffer intensity", "Safety-stock $", "Excess $"],
        [[r.sku, esc(r.product_name), r.abc_class, r.sigma_source.replace("_", " "),
          f"{r.buffer_intensity:.3f}", money(r.safety_stock_value), money(r.excess_buffer_value)]
         for r in top_over.itertuples()],
        num_cols=(0, 4, 5, 6), caption="Ten largest over-buffered SKUs by excess capital")

    split_tbl = table(
        ["Volatility source", "SKUs", "Safety-stock capital @95%", "Over-buffered SKUs", "Trapped cash"],
        [[{"per_sku": "Measured (own history)", "class_fallback": "Estimated (class-level)",
           "total": "Total"}[r.sigma_source],
          int(r.skus), money(r.safety_stock_capital), int(r.over_buffered_skus), money(r.trapped_cash)]
         for r in split.reset_index().itertuples()],
        num_cols=range(1, 5))

    sens_rows = []
    for c in ["A", "B", "C", "ALL"]:
        g = sens[sens.abc_class == c].set_index("service_level")
        sens_rows.append([("Catalogue" if c == "ALL" else f"Class {c}"),
                          money(g.loc[0.90, "buffer_value"]), money(g.loc[0.95, "buffer_value"]),
                          money(g.loc[0.99, "buffer_value"])])
    sens_tbl = table(["", "90% service", "95% service (baseline)", "99% service"], sens_rows,
                     num_cols=(1, 2, 3))

    audit_tbl = table(["Check", "Result"], [[esc(k), esc(v)] for k, v in AUDIT])

    # ---- SKU explorer --------------------------------------------------------
    sku_rows = []
    for r in m.sort_values("annual_demand_value", ascending=False).itertuples():
        ss = {l: getattr(r, f"safety_stock_{l}") for l in (90, 95, 99)}
        rp = {l: getattr(r, f"reorder_point_{l}") for l in (90, 95, 99)}
        sv = {l: ss[l] * r.avg_price for l in (90, 95, 99)}

        def lv(vals, kind, fmt):
            a = " ".join(f'data-l{l}="{vals[l]:.4f}"' for l in (90, 95, 99))
            return f'<td class="num" {a} data-kind="{kind}" data-sort="{vals[95]:.4f}">{fmt(vals[95])}</td>'

        flag_cls = "pill warn" if r.buffer_flag == "over_buffered" else "pill ok"
        sku_rows.append(
            f'<tr data-cls="{r.abc_class}" data-flag="{r.buffer_flag}" '
            f'data-search="{esc(f"{r.sku} {r.product_name}".lower())}">'
            f'<td class="num" data-sort="{r.sku}">{r.sku}</td>'
            f'<td data-sort="{esc(r.product_name)}">{esc(r.product_name)}</td>'
            f'<td data-sort="{r.abc_class}">{r.abc_class}</td>'
            f'<td data-sort="{r.velocity_tier}">{r.velocity_tier}</td>'
            f'<td class="num" data-sort="{r.annual_demand_value:.2f}">{money(r.annual_demand_value)}</td>'
            f'<td class="num" data-sort="{r.eoq:.2f}">{r.eoq:,.0f}</td>'
            + lv(ss, "units", lambda v: f"{v:,.1f}")
            + lv(rp, "units", lambda v: f"{v:,.1f}")
            + lv(sv, "money", money)
            + f'<td data-sort="{r.buffer_flag}"><span class="{flag_cls}">{r.buffer_flag.replace("_", "-")}</span></td>'
            f'<td data-sort="{r.sigma_source}">{r.sigma_source.replace("_", " ")}</td></tr>'
        )
    sku_heads = [("SKU", "num"), ("Product", "text"), ("Class", "text"), ("Velocity", "text"),
                 ("Annual value", "num"), ("EOQ (units)", "num"), ("Safety stock", "num"),
                 ("Reorder point", "num"), ("Safety-stock $", "num"), ("Buffer flag", "text"),
                 ("Sigma source", "text")]
    sku_thead = "".join(
        f'<th data-type="{t}" class="{"num " if t == "num" else ""}sortable" aria-sort="none">{esc(h)}</th>'
        for h, t in sku_heads)

    shots = "".join(
        f'<figure class="fig shot"><img src="assets/powerbi-{s}.png" '
        f'width="{sizes["powerbi-" + s][0]}" height="{sizes["powerbi-" + s][1]}" loading="lazy" '
        f'alt="Power BI {esc(t)}. {esc(c)}"><figcaption><strong>{esc(t)}.</strong> {esc(c)}'
        f"</figcaption></figure>"
        for s, t, c in SCREENSHOTS)

    fig = lambda slug: figure(slug, *next((t, c) for s, t, c in CHARTS if s == slug), sizes[slug])

    body = f"""
<header class="hero"><div class="wrap">
  <p class="eyebrow">Portfolio project</p>
  <h1>DataCo Inventory Analytics</h1>
  <p class="lede">Where is working capital trapped in slow-moving inventory &mdash; and how should reorder
  policies change to free cash without dropping below a 95% service level?</p>
  <p class="by">By <a href="https://github.com/GireesheePendela">Gireeshee Pendela</a> &middot;
  SQL (DuckDB) &rarr; pandas &rarr; Power BI</p>
  <p class="cta"><a class="btn" href="{REPO}">View the code</a>
  <a class="btn ghost" href="{REPO}/blob/main/notebooks/analysis.ipynb">Read the notebook</a>
  <a class="btn ghost" href="{REPO}#readme">README</a></p>
</div></header>

<nav class="nav" aria-label="Sections"><div class="wrap">
  <a href="#summary">Summary</a><a href="#method">Method</a><a href="#analysis">Analysis</a>
  <a href="#dashboard">Dashboard</a><a href="#explorer">SKU explorer</a><a href="#recommendations">Recommendations</a>
</div></nav>

<main>
<section id="summary"><div class="wrap">
  <h2>The short version</h2>
  <div class="tiles">{tiles}</div>
  <div class="callout"><strong>How much to trust the trapped-cash number.</strong> {n_est} of {n_sku} SKUs
  ({n_est / n_sku:.0%}) have under 6 months of sales history, so their demand variability is estimated
  from their ABC class rather than measured. They hold {cap_est_share:.0%} of the safety-stock capital and
  account for {trapped_est_share:.0%} of the trapped cash. The defensible claim is
  <strong>about {kmoney(trapped_meas)} trapped on measured SKUs, up to about {kmoney(trapped)}</strong>
  if the estimated SKUs behave like their class.</div>
</div></section>

<section id="method"><div class="wrap">
  <h2>Data and method</h2>
  <p>The data is the public <strong>DataCo Smart Supply Chain</strong> dataset (Kaggle, CC0): customer order
  lines, not warehouse records. It has <strong>no on-hand inventory column</strong>, so target stock is
  <em>prescribed</em> from demand behaviour rather than read from a stock level, and turnover is labelled
  &ldquo;implied&rdquo;.</p>
  <ol class="steps">
    <li><strong>Aggregate (SQL).</strong> DuckDB rolls ~180K order rows into a SKU &times; month demand series
    plus per-SKU lead-time statistics.</li>
    <li><strong>Demand profile (pandas).</strong> Each SKU's monthly series is zero-filled between its first and
    last sale, then reduced to mean and standard deviation. SKUs with under 6 months are flagged.</li>
    <li><strong>Four layers.</strong> Implied turnover, ABC classification, EOQ, and safety stock / reorder
    point at 90/95/99% service.</li>
    <li><strong>Mismatch analysis.</strong> An independent <em>buffer-intensity</em> metric finds where
    capital is mis-allocated.</li>
    <li><strong>Report.</strong> One flat file, <code>sku_metrics.csv</code>, feeds the Power BI report.</li>
  </ol>
  <p><strong>Assumptions</strong> (not in the data): ordering cost <code>S</code> = $75 per order; holding
  cost = 25% of unit price per year; baseline service level 95% (z &asymp; 1.65).</p>
</div></section>

<section id="analysis"><div class="wrap">
  <h2>The analysis, step by step</h2>

  <article class="stage"><h3>1. Data audit</h3>
  <p>The data is unusually clean. Demand is right-skewed, and about 19% of orders lose money &mdash; real
  signal, so I kept them.</p>
  <div class="two">{audit_tbl}<div>{fig("units-per-sku")}</div></div>
  {fig("one-sku-monthly")}</article>

  <article class="stage"><h3>2. Implied turnover and velocity tiers</h3>
  <p>With no on-hand column, average inventory is derived from the sawtooth cycle-stock model (EOQ / 2).
  Because that assumes cost-optimal ordering, turns are a best-case benchmark that ranks relative velocity;
  it does not prove overstocking. The slow tier has a median of {slow.implied_days_of_supply.median():.0f}
  days of supply and {money(slow.annual_demand_value.median())} of annual value per SKU, against
  {fast.implied_days_of_supply.median():.0f} days and {money(fast.annual_demand_value.median())} for the fast tier.</p>
  {fig("turnover")}{tier_tbl}</article>

  <article class="stage"><h3>3. ABC classification</h3>
  <p>SKUs are ranked by annual demand value and cut at 80% and 95% of cumulative value. The result is a steep
  Pareto curve: <strong>{len(a)} SKUs ({len(a) / n_sku:.0%}) carry {a_share:.0%} of the value</strong>.</p>
  {fig("pareto")}{abc_tbl}</article>

  <article class="stage"><h3>4. Economic order quantity</h3>
  <p>EOQ is the order size that minimises ordering plus holding cost. Against a &ldquo;reorder monthly&rdquo;
  baseline it saves <strong>{money(eoq_saving)} a year ({eoq_saving / monthly_cost:.0%})</strong>, mostly in class
  A. The dataset records customer sales, not the company's own purchase orders, so this is a comparison with a
  hypothetical baseline rather than with actual ordering.</p>
  {fig("eoq")}{eoq_tbl}</article>

  <article class="stage"><h3>5. Safety stock and reorder point</h3>
  <p>Safety stock = z &times; daily demand &sigma; &times; &radic;lead time. Reorder point = expected demand over
  the lead time + safety stock. Computed at 90, 95 and 99% service so the report can switch without
  recomputing. The {n_est} short-history SKUs borrow their ABC class's median coefficient of variation instead
  of a per-SKU sigma.</p>
  {fig("buffer-capital")}{ss_tbl}</article>

  <article class="stage"><h3>6. Mismatch analysis: where is capital mis-allocated?</h3>
  <p>Implied turnover turns out to be an algebraic rescaling of ABC value
  (turns = &radic;(2&middot;H/S) &times; &radic;annual value), so comparing the two would find a pattern the maths
  guarantees. I used an independent signal instead: <strong>buffer intensity</strong>, safety-stock dollars per
  dollar of annual throughput. It is driven by demand variability and lead time, not by value.</p>
  <p>{n_over} SKUs (all class B or C) are flagged over-buffered. The class-A SKUs are all
  efficiently buffered &mdash; their volume smooths their demand. Class B looks worst: {b_heavy} of {len(b)}
  B-SKUs are in the heavy tier, though {b_heavy_est} of those {b_heavy} are estimate-driven.</p>
  {fig("mismatch")}<div class="two">{xt_tbl}<div></div></div>{over_tbl}</article>

  <article class="stage"><h3>7. Robustness: how much rests on estimated volatility?</h3>
  <p>Splitting the same numbers by where each SKU's sigma came from shows that
  <strong>{trapped_est_share:.0%} of the trapped cash and {cap_est_share:.0%} of the buffer capital</strong>
  sit on estimated rather than measured volatility. The class-B SKUs among them share one borrowed ratio, so they
  land in the same tier by construction. Treat the class-B ranking as a hypothesis, and buy more history on those
  {n_est} SKUs before acting on the larger figure.</p>
  {split_tbl}</article>

  <article class="stage"><h3>8. Sensitivity to the service level</h3>
  <p>Safety stock scales linearly with z, so every class moves by the same percentage (&minus;22% at 90%,
  +41% at 99%) &mdash; but the dollars are not evenly spread, because class A holds most of the buffer. Lifting
  <em>only</em> the {len(a)} class-A SKUs to 99% costs <strong>{money(uplift_a)}</strong>
  ({money(uplift_a_est)} of it on the {a_est} class-A SKUs with estimated volatility), against
  <strong>{money(uplift_all)}</strong> to lift the whole catalogue.</p>
  {fig("sensitivity")}{sens_tbl}</article>
</div></section>

<section id="dashboard"><div class="wrap">
  <h2>The Power BI report</h2>
  <p>The report reads <code>sku_metrics.csv</code> only &mdash; no live connection and no computation inside the
  report. The <code>.pbix</code> file is in the repository; these are screenshots of its three pages.</p>
  {shots}
</div></section>

<section id="explorer"><div class="wrap">
  <h2>SKU explorer</h2>
  <p>All {n_sku} SKUs. Click a column heading to sort; the service-level selector recalculates safety stock,
  reorder point and buffer dollars, as in the Power BI report.</p>
  <div class="controls">
    <label>Search <input id="sku-q" type="search" placeholder="SKU or product name"></label>
    <label>Class <select id="sku-class"><option value="all">All</option><option>A</option><option>B</option><option>C</option></select></label>
    <label>Buffer flag <select id="sku-flag"><option value="all">All</option><option value="efficient">efficient</option><option value="over_buffered">over-buffered</option></select></label>
    <label>Service level <select id="sku-level"><option value="90">90%</option><option value="95" selected>95%</option><option value="99">99%</option></select></label>
    <span id="sku-count" class="count" aria-live="polite"></span>
  </div>
  <div class="tablewrap tall"><table id="sku-table"><thead><tr>{sku_thead}</tr></thead>
  <tbody>{"".join(sku_rows)}</tbody></table></div>
</div></section>

<section id="recommendations"><div class="wrap">
  <h2>Recommendations</h2>
  <ol class="steps">
    <li><strong>Adopt EOQ ordering, starting with class A</strong> &mdash; the {len(a)} A-SKUs drive most of the
    {kmoney(eoq_saving)} a year available from right-sizing order quantities.</li>
    <li><strong>Use a class-differentiated service policy</strong> &mdash; class A at 99%, B and C at 95%. It
    costs {kmoney(uplift_a)} of extra buffer against {kmoney(uplift_all)} for the whole catalogue, and nothing
    drops below the 95% floor.</li>
    <li><strong>Go after trapped cash in over-buffered B/C SKUs</strong> through demand smoothing and shorter
    supplier lead times, not service cuts. Start with the {kmoney(trapped_meas)} on SKUs with measured
    volatility ({n_over_meas} SKUs); collect more history on the other {n_over_est} before acting on the
    remaining {kmoney(trapped_est)}.</li>
    <li><strong>Validate the {n_est} short-history SKUs</strong> before acting on their reorder points.</li>
  </ol>
  <h2>Confidence and limitations</h2>
  <ul class="steps">
    <li><strong>{n_est / n_sku:.0%} of SKUs have estimated volatility</strong> &mdash; {cap_est_share:.0%} of
    safety-stock capital, and {b_est} of the {len(b)} class-B SKUs.</li>
    <li><strong>The EOQ saving is against a hypothetical baseline</strong>, not actual purchase orders.</li>
    <li><strong>No on-hand inventory</strong> &mdash; turnover is implied and ranks velocity only.</li>
    <li><strong>Only demand variability is buffered.</strong> Lead times are short and stable (0&ndash;6 days).</li>
    <li><strong>Ordering cost and holding-cost rate are assumptions</strong>; the dollar figures scale with them.</li>
  </ul>
</div></section>
</main>

<footer><div class="wrap"><p>Built with DuckDB, pandas and Power BI. Source, notebook and Power BI file on
<a href="{REPO}">GitHub</a> &middot; MIT licensed &middot; data: DataCo Smart Supply Chain (Kaggle, CC0).</p></div></footer>
"""

    og_title = "DataCo Inventory Analytics"
    og_desc = (f"SQL + Python + Power BI inventory analysis: {kmoney(eoq_saving)} a year from EOQ ordering, "
               f"{kmoney(trapped)} of buffer capital flagged as trapped.")
    head = HEAD.replace("%TITLE%", og_title).replace("%DESC%", esc(og_desc)).replace("%SITE%", SITE)
    (DOCS / "index.html").write_text(head + body + SCRIPT + "</body></html>\n", encoding="utf-8")
    print(f"wrote docs/index.html ({len(body):,} chars body), {len(CHARTS)} charts, {len(SCREENSHOTS)} screenshots")


HEAD = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>%TITLE%</title>
<meta name="description" content="%DESC%">
<meta property="og:title" content="%TITLE%">
<meta property="og:description" content="%DESC%">
<meta property="og:type" content="website">
<meta property="og:image" content="%SITE%/assets/powerbi-overview.png">
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#1c2430;--mute:#5b6675;--line:#e1e5ea;--accent:#1f5fbf;--accent-ink:#fff;
--warn:#c4521a;--warn-bg:#fbe9df;--ok:#2d7a46;--ok-bg:#e4f3e9;--call:#fff8e6;--call-line:#f0d58a}
@media (prefers-color-scheme:dark){:root{--bg:#12161c;--card:#1a2029;--ink:#e6eaf0;--mute:#9aa6b5;--line:#2c3541;
--accent:#6aa6ff;--accent-ink:#0b1220;--warn:#ff9a66;--warn-bg:#3a2418;--ok:#6fcf8b;--ok-bg:#16301e;
--call:#2a2412;--call-line:#6b5a1f}}
*{box-sizing:border-box}html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.6 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
a{color:var(--accent)}code{background:var(--line);padding:1px 5px;border-radius:4px;font-size:.9em}
.wrap{max-width:1080px;margin:0 auto;padding:0 20px}
.hero{padding:56px 0 36px;border-bottom:1px solid var(--line)}
.eyebrow{margin:0;text-transform:uppercase;letter-spacing:.12em;font-size:.78rem;color:var(--mute)}
h1{font-size:clamp(2rem,5vw,3rem);line-height:1.1;margin:.2em 0 .3em}
.lede{font-size:1.2rem;max-width:46em;margin:0 0 .8em}.by{color:var(--mute);margin:0 0 1.2em}
.btn{display:inline-block;padding:9px 16px;border-radius:8px;background:var(--accent);color:var(--accent-ink);
text-decoration:none;font-weight:600;margin:0 8px 8px 0}.btn.ghost{background:transparent;color:var(--accent);border:1px solid var(--accent)}
.nav{position:sticky;top:0;z-index:5;background:var(--card);border-bottom:1px solid var(--line)}
.nav .wrap{display:flex;gap:4px;overflow-x:auto}.nav a{padding:12px 12px;text-decoration:none;color:var(--ink);white-space:nowrap;font-size:.92rem}
.nav a:hover{color:var(--accent)}
section{padding:36px 0}section[id],article[id]{scroll-margin-top:56px}
h2{font-size:1.6rem;margin:0 0 .6em}h3{font-size:1.2rem;margin:0 0 .5em}
.tiles{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:0 0 18px}
@media (max-width:760px){.tiles{grid-template-columns:repeat(2,1fr)}}
@media (max-width:440px){.tiles{grid-template-columns:1fr}}
.tile{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.tile .big{font-size:2rem;font-weight:700;line-height:1.1}.tile .lbl{font-weight:600;margin-top:4px}
.tile .note{color:var(--mute);font-size:.88rem;margin-top:2px}
.callout{background:var(--call);border:1px solid var(--call-line);border-radius:10px;padding:14px 16px}
.steps{padding-left:1.2em}.steps li{margin:.4em 0}
.stage{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px;margin:0 0 22px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:18px;align-items:start}
@media (max-width:760px){.two{grid-template-columns:1fr}}
.fig{margin:14px 0}.fig img{display:block;max-width:100%;height:auto;background:#fff;border:1px solid var(--line);border-radius:8px}
.fig figcaption{color:var(--mute);font-size:.9rem;margin-top:6px}.shot img{width:100%}
.tablewrap{overflow-x:auto;margin:14px 0}.tablewrap.tall{max-height:620px;overflow:auto;border:1px solid var(--line);border-radius:8px}
table{border-collapse:collapse;width:100%;font-size:.9rem}
caption{text-align:left;color:var(--mute);font-size:.85rem;padding:0 0 6px}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{background:var(--bg);font-weight:600;position:sticky;top:0}.num{text-align:right;font-variant-numeric:tabular-nums}
th.sortable{cursor:pointer;user-select:none}th.sortable:hover{color:var(--accent)}
th[aria-sort=ascending]::after{content:" \\25B2";font-size:.7em}th[aria-sort=descending]::after{content:" \\25BC";font-size:.7em}
.pill{padding:2px 8px;border-radius:999px;font-size:.78rem;white-space:nowrap}.pill.warn{background:var(--warn-bg);color:var(--warn)}
.pill.ok{background:var(--ok-bg);color:var(--ok)}
.controls{display:flex;flex-wrap:wrap;gap:12px 18px;align-items:end;margin:10px 0}
.controls label{display:flex;flex-direction:column;font-size:.82rem;color:var(--mute);gap:3px}
.controls input,.controls select{font:inherit;padding:6px 8px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--ink)}
.count{color:var(--mute);font-size:.9rem;padding-bottom:7px}
footer{border-top:1px solid var(--line);padding:24px 0;color:var(--mute);font-size:.9rem}
</style></head><body>"""

SCRIPT = """
<script>
(function () {
  var table = document.getElementById('sku-table');
  if (!table) return;
  var body = table.tBodies[0];
  var rows = Array.prototype.slice.call(body.rows);
  var q = document.getElementById('sku-q'), cls = document.getElementById('sku-class');
  var flag = document.getElementById('sku-flag'), lvl = document.getElementById('sku-level');
  var count = document.getElementById('sku-count');
  var f1 = new Intl.NumberFormat('en-US', {minimumFractionDigits: 1, maximumFractionDigits: 1});
  var f0 = new Intl.NumberFormat('en-US', {maximumFractionDigits: 0});

  function filter() {
    var t = q.value.trim().toLowerCase(), n = 0;
    rows.forEach(function (r) {
      var ok = (!t || r.dataset.search.indexOf(t) !== -1) &&
               (cls.value === 'all' || r.dataset.cls === cls.value) &&
               (flag.value === 'all' || r.dataset.flag === flag.value);
      r.hidden = !ok;
      if (ok) n++;
    });
    count.textContent = n + ' of ' + rows.length + ' SKUs';
  }

  function level() {
    rows.forEach(function (r) {
      Array.prototype.forEach.call(r.querySelectorAll('td[data-l90]'), function (td) {
        var v = parseFloat(td.getAttribute('data-l' + lvl.value));
        td.setAttribute('data-sort', v);
        td.textContent = td.getAttribute('data-kind') === 'money' ? '$' + f0.format(v) : f1.format(v);
      });
    });
  }

  var heads = Array.prototype.slice.call(table.tHead.rows[0].cells), col = -1, dir = 1;
  function sortBy(i) {
    var numeric = heads[i].getAttribute('data-type') === 'num';
    if (col === i) dir = -dir; else { col = i; dir = numeric ? -1 : 1; }
    rows.sort(function (a, b) {
      var x = a.cells[i].getAttribute('data-sort'), y = b.cells[i].getAttribute('data-sort');
      if (numeric) { x = parseFloat(x); y = parseFloat(y); } else { x = x.toLowerCase(); y = y.toLowerCase(); }
      return (x < y ? -1 : x > y ? 1 : 0) * dir;
    });
    rows.forEach(function (r) { body.appendChild(r); });
    heads.forEach(function (h, j) { h.setAttribute('aria-sort', j === i ? (dir > 0 ? 'ascending' : 'descending') : 'none'); });
  }
  heads.forEach(function (th, i) {
    th.tabIndex = 0;
    th.addEventListener('click', function () { sortBy(i); });
    th.addEventListener('keydown', function (e) { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); sortBy(i); } });
  });
  [q, cls, flag].forEach(function (el) { el.addEventListener('input', filter); });
  lvl.addEventListener('change', level);
  filter();
})();
</script>
"""


if __name__ == "__main__":
    build()

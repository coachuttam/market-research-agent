import os
import re
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUTPUT_DIR = "output"
os.makedirs(OUTPUT_DIR, exist_ok=True)


# ============================================================
# BRAND STYLE
# Colors and fonts shared by every chart, so they all look consistent.
# ============================================================

NAVY = "#12233F"
BLUE = "#1F5FA8"
LIGHT_BLUE = "#7FA8D9"
SLATE = "#5B6B7C"
LIGHT_GRID = "#E4E8EC"
GOLD = "#C8963E"
GREEN = "#2E7D5B"
GREY_SERIES = ["#12233F", "#1F5FA8", "#7FA8D9", "#5B6B7C", "#A9B7C4", "#C3CBD3"]

# Used only for the geographic-revenue chart, which previously reused
# GREY_SERIES like every other chart and came out looking flat/muted
# for what is meant to be a small, distinct set of regions (Americas,
# EMEA, APAC, etc.). This is a separate, more colourful categorical
# palette so that chart reads clearly at a glance.
GEO_COLORS = [BLUE, GREEN, GOLD, "#B33A3A", "#7B5EA7"]

plt.rcParams.update({
    "font.family": "DejaVu Sans",
    "axes.edgecolor": SLATE,
    "axes.labelcolor": NAVY,
    "text.color": NAVY,
    "xtick.color": NAVY,
    "ytick.color": NAVY,
    "axes.linewidth": 0.8,
    "figure.facecolor": "white",
    "savefig.facecolor": "white",
})


def style_ax(ax, y_grid=True, x_grid=False):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    if y_grid:
        ax.yaxis.grid(True, color=LIGHT_GRID, linewidth=1, zorder=0)
    if x_grid:
        ax.xaxis.grid(True, color=LIGHT_GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def title(ax, text):
    ax.set_title(text, fontsize=13, fontweight="bold", color=NAVY, loc="left", pad=14)


def source_caption(fig, items, extra=""):
    titles = []
    for x in items:
        t = str(x.get("source_title", "")).strip()
        if t and t not in titles:
            titles.append(t)
        if len(titles) >= 2:
            break
    text = "Source: " + "; ".join(titles) if titles else "Source: verified structured research data"
    if extra:
        text += f". {extra}"
    fig.text(0.01, -0.02, text, fontsize=8, color=SLATE)


def save(fig, name):
    path = os.path.join(OUTPUT_DIR, name)
    fig.savefig(path, dpi=220, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


# ============================================================
# SHARED DATA HELPERS
# ============================================================

def safe_filename(name):
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", str(name)).strip("_").lower()


def company_name(data):
    return data.get("company_name", "Company") if isinstance(data, dict) else "Company"


def rows(data, field):
    """Return only the VERIFIED items from a data field. Charts should
    only use the most trustworthy data."""
    values = data.get(field, []) if isinstance(data, dict) else []
    if not isinstance(values, list):
        return []
    return [
        x for x in values
        if isinstance(x, dict)
        and x.get("verification") == "VERIFIED"
        and x.get("value") not in (None, "")
    ]


def number(value):
    if isinstance(value, (int, float)):
        return float(value)
    if value is None:
        return None
    s = str(value).lower().replace(",", "")
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    n = float(m.group())
    if "billion" in s:
        n *= 1000
    elif "thousand" in s:
        n /= 1000
    return n


def year(x):
    try:
        return int(x.get("year"))
    except Exception:
        return None


def annual(x):
    haystack = f"{x.get('metric', '')} {x.get('period', '')}"
    # Matches "quarter" so it also catches "Quarterly" (not just "Q1").
    return not re.search(r"\bq[1-4]\b|quarter", haystack, re.IGNORECASE)


def is_percent(x):
    unit = str(x.get("unit", "")).lower()
    val = str(x.get("value", ""))
    return "%" in unit or "%" in val


def fmt_value(v, decimals=1):
    if v is None:
        return ""
    if abs(v) >= 100:
        return f"{v:,.0f}"
    return f"{v:,.{decimals}f}"


def most_common_period(items):
    """Find the period (like "FY2025") shared by the most items, so we
    can pick one consistent period to chart instead of mixing periods."""
    if not items:
        return None
    counts = {}
    for x in items:
        p = str(x.get("period", "")).strip()
        if not p:
            continue
        counts.setdefault(p, []).append(x)

    if not counts:
        return None

    def score(period):
        group = counts[period]
        is_ann = any(annual(x) for x in group)
        latest_year = max((year(x) or 0) for x in group)
        return (len(group), is_ann, latest_year)

    return max(counts.keys(), key=score)


# ============================================================
# 1. FIVE-YEAR REVENUE TREND
# ============================================================

def revenue_five_year(data):
    history = data.get("annual_revenue_history", []) if isinstance(data, dict) else []
    history = [
        x for x in history
        if isinstance(x, dict) and number(x.get("value")) is not None and year(x)
        # annual_revenue_history can also hold a non-revenue row (e.g. a
        # "Revenue Growth" percentage) alongside the real revenue figures
        # for the same year -- without this filter that percentage gets
        # plotted as if it were another year's revenue, on the same USD
        # million axis as figures literally hundreds of times larger, so
        # it renders as an invisible sliver of a bar while still counting
        # toward the "N-Year" title and (if it sorts last) hijacking the
        # y-axis unit label to "%". Only genuine revenue rows belong here,
        # same filter revenue_outlook() already uses just below.
        and ("revenue" in str(x.get("metric", "")).lower() or "net sales" in str(x.get("metric", "")).lower())
        and "growth" not in str(x.get("metric", "")).lower()
    ]
    if len(history) < 2:
        return None

    history = sorted(history, key=lambda x: year(x))
    labels = [f"FY{year(x)}" for x in history]
    values = [number(x.get("value")) for x in history]
    unit = str(history[-1].get("unit") or "Reported value")

    fig, ax = plt.subplots(figsize=(8.6, 4.3), dpi=220)
    bars = ax.bar(labels, values, color=NAVY, width=0.55, zorder=3)
    for rect, v in zip(bars, values):
        ax.text(rect.get_x() + rect.get_width() / 2, v, fmt_value(v), ha="center", va="bottom",
                fontsize=9.5, color=NAVY, fontweight="medium")

    style_ax(ax)
    ax.set_ylabel(unit)
    title(ax, f"{company_name(data)} — {len(history)}-Year Revenue Trend")
    source_caption(fig, history)
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_revenue_five_year.png")


# ============================================================
# 2. REVENUE OUTLOOK (actual vs. guidance)
# ============================================================

def revenue_outlook(data):
    all_rows = [x for x in rows(data, "financial_metrics") if annual(x)]
    actual, guidance = [], []

    for x in all_rows:
        name = str(x.get("metric", "")).lower()
        if "revenue" not in name and "net sales" not in name:
            continue
        item_type = str(x.get("type", "")).lower()
        if item_type in ("guidance", "forecast"):
            guidance.append(x)
        elif item_type == "actual":
            actual.append(x)

    if not actual or not guidance:
        return None

    a = max(actual, key=lambda x: year(x) or 0)
    g = max(guidance, key=lambda x: year(x) or 0)
    av, gv = number(a.get("value")), number(g.get("value"))
    if av is None or gv is None or year(a) == year(g):
        return None

    fig, ax = plt.subplots(figsize=(8.2, 4.3), dpi=220)
    labels = [f"FY{year(a)} Actual", f"FY{year(g)} Guidance"]
    bars = ax.bar(labels, [av, gv], color=[NAVY, GOLD], width=0.5, zorder=3)

    for bar, value in zip(bars, [av, gv]):
        ax.text(bar.get_x() + bar.get_width() / 2, value, fmt_value(value), ha="center", va="bottom",
                fontsize=10, color=NAVY, fontweight="medium")

    style_ax(ax)
    ax.set_ylabel(str(a.get("unit") or "Reported value"))
    title(ax, f"{company_name(data)} — Revenue Outlook")

    growth = (gv / av - 1) * 100 if av else None
    if growth is not None:
        ax.text(0.5, 0.92, f"Implied growth: {growth:+.1f}%", transform=ax.transAxes,
                ha="center", va="top", fontsize=9.5, color=SLATE)
        ax.set_ylim(0, max(av, gv) * 1.18)

    source_caption(fig, [a, g])
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_revenue_outlook.png")


# ============================================================
# 3. QUARTERLY REVENUE
# ============================================================

def quarterly_revenue(data):
    candidates = []
    for x in rows(data, "financial_metrics"):
        name = str(x.get("metric", "")).lower()
        if ("revenue" in name or "net sales" in name) and not annual(x):
            if number(x.get("value")) is not None:
                candidates.append(x)

    if len(candidates) < 2:
        return None

    unique = {}
    for x in candidates:
        key = (year(x), str(x.get("period") or x.get("metric")))
        unique[key] = x

    ordered = sorted(unique.values(), key=lambda x: (year(x) or 0, str(x.get("period", ""))))
    if len(ordered) < 2:
        return None

    ordered = ordered[-6:]
    labels = [str(x.get("period") or x.get("metric")) for x in ordered]
    values = [number(x.get("value")) for x in ordered]

    fig, ax = plt.subplots(figsize=(8.6, 4.3), dpi=220)
    ax.plot(labels, values, marker="o", linewidth=2.2, color=BLUE, markerfacecolor=NAVY, markersize=6, zorder=3)
    for label, value in zip(labels, values):
        ax.annotate(fmt_value(value), xy=(label, value), xytext=(0, 8), textcoords="offset points",
                    ha="center", fontsize=9, color=NAVY)

    style_ax(ax)
    ax.set_ylabel(str(ordered[-1].get("unit") or "Reported value"))
    ax.tick_params(axis="x", rotation=20)
    title(ax, f"{company_name(data)} — Quarterly Revenue")
    source_caption(fig, ordered)
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_quarterly_revenue.png")


def margin_trend(data):
    # Look for annual margin percentages (Gross Margin, Operating
    # Margin, Net Margin) and plot each one as its own line, but only
    # for margins that have 2+ different years of data -- a single
    # year's margin isn't a "trend."
    candidates = [
        x for x in rows(data, "financial_metrics")
        if annual(x) and "margin" in str(x.get("metric", "")).lower() and is_percent(x)
    ]

    by_metric = {}
    for x in candidates:
        name = str(x.get("metric", "")).strip()
        y = year(x)
        v = number(x.get("value"))
        if y is None or v is None:
            continue
        by_metric.setdefault(name, {})[y] = x

    series = {name: yrs for name, yrs in by_metric.items() if len(yrs) >= 2}
    if not series:
        return None

    fig, ax = plt.subplots(figsize=(8.6, 4.3), dpi=220)
    used_source_items = []

    for i, (name, yrs) in enumerate(sorted(series.items())):
        ordered = sorted(yrs.items())
        labels = [f"FY{y}" for y, _ in ordered]
        values = [number(x.get("value")) for _, x in ordered]
        color = GREY_SERIES[i % len(GREY_SERIES)]
        ax.plot(labels, values, marker="o", linewidth=2.2, color=color, markersize=6, zorder=3, label=name)
        used_source_items.extend(x for _, x in ordered)

    style_ax(ax)
    ax.set_ylabel("Percent")
    ax.legend(frameon=False, fontsize=9.5, loc="best")
    title(ax, f"{company_name(data)} — Margin Trend")
    source_caption(fig, used_source_items)
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_margin_trend.png")


def free_cash_flow_trend(data):
    candidates = [
        x for x in rows(data, "financial_metrics")
        if annual(x) and "free cash flow" in str(x.get("metric", "")).lower()
    ]

    by_year = {}
    for x in candidates:
        y = year(x)
        if y is not None and number(x.get("value")) is not None:
            by_year[y] = x

    if len(by_year) < 2:
        return None

    ordered = sorted(by_year.items())
    labels = [f"FY{y}" for y, _ in ordered]
    values = [number(x.get("value")) for _, x in ordered]

    fig, ax = plt.subplots(figsize=(8.6, 4.3), dpi=220)
    bars = ax.bar(labels, values, color=NAVY, width=0.55, zorder=3)
    for rect, v in zip(bars, values):
        ax.text(rect.get_x() + rect.get_width() / 2, v, fmt_value(v), ha="center", va="bottom",
                fontsize=9.5, color=NAVY, fontweight="medium")

    style_ax(ax)
    ax.set_ylabel(str(ordered[-1][1].get("unit") or "Reported value"))
    title(ax, f"{company_name(data)} — Free Cash Flow Trend")
    source_caption(fig, [x for _, x in ordered])
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_fcf_trend.png")


# ============================================================
# 4 & 5. SEGMENT REVENUE + SEGMENT GROWTH
# ============================================================

def _segment_slice(data):
    seg_rows = [x for x in rows(data, "segment_metrics") if str(x.get("segment", "")).strip()]
    if not seg_rows:
        return [], None
    period = most_common_period(seg_rows)
    if period is None:
        return [], None
    return [x for x in seg_rows if str(x.get("period", "")).strip() == period], period


def segment_revenue(data):
    seg_rows, period = _segment_slice(data)
    if not seg_rows:
        return None

    revenue_rows = {}
    for x in seg_rows:
        name = str(x.get("metric", "")).lower()
        if "revenue" not in name and "net sales" not in name:
            continue
        seg = str(x.get("segment")).strip()
        v = number(x.get("value"))
        if v is None:
            continue
        if seg not in revenue_rows or v > number(revenue_rows[seg].get("value")):
            revenue_rows[seg] = x

    if len(revenue_rows) < 2:
        return None

    items = sorted(revenue_rows.values(), key=lambda x: number(x.get("value")), reverse=True)
    labels = [str(x.get("segment")) for x in items]
    values = [number(x.get("value")) for x in items]
    unit = str(items[0].get("unit") or "Reported value")

    fig, ax = plt.subplots(figsize=(8.6, 4.4), dpi=220)
    y = range(len(labels))
    colors = [GREY_SERIES[i % len(GREY_SERIES)] for i in range(len(labels))]
    bars = ax.barh(list(y), values, color=colors, height=0.6, zorder=3)
    ax.invert_yaxis()
    for rect, v in zip(bars, values):
        ax.text(rect.get_width(), rect.get_y() + rect.get_height() / 2, f" {fmt_value(v)}",
                va="center", ha="left", fontsize=10, color=NAVY, fontweight="medium")
    ax.set_yticks(list(y))
    ax.set_yticklabels(labels, fontsize=10.5)
    ax.set_xlabel(f"{period} revenue, {unit}")
    ax.xaxis.grid(True, color=LIGHT_GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(length=0)
    title(ax, f"{company_name(data)} — Revenue by Segment ({period})")
    source_caption(fig, items)
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_segment_revenue.png")


def segment_growth(data):
    seg_rows, period = _segment_slice(data)
    if not seg_rows:
        return None

    growth_rows = {}
    for x in seg_rows:
        name = str(x.get("metric", "")).lower()
        if "margin" in name:
            continue
        if "growth" not in name and not is_percent(x):
            continue
        seg = str(x.get("segment")).strip()
        v = number(x.get("value"))
        if v is None:
            continue
        growth_rows[seg] = x

    if len(growth_rows) < 2:
        return None

    items = sorted(growth_rows.values(), key=lambda x: number(x.get("value")), reverse=True)
    labels = [str(x.get("segment")) for x in items]
    values = [number(x.get("value")) for x in items]
    top_val = max(values)

    fig, ax = plt.subplots(figsize=(8.6, 4.1), dpi=220)
    colors = [GOLD if v == top_val else NAVY for v in values]
    bars = ax.bar(labels, values, color=colors, width=0.55, zorder=3)
    for rect, v in zip(bars, values):
        ax.text(rect.get_x() + rect.get_width() / 2, v, f"{v:+.0f}%", ha="center",
                va="bottom" if v >= 0 else "top", fontsize=10.5, color=NAVY, fontweight="bold")

    style_ax(ax)
    ax.axhline(0, color=SLATE, linewidth=0.8)
    ax.set_ylabel("YoY growth, %")
    title(ax, f"{company_name(data)} — Segment Growth ({period})")
    source_caption(fig, items)
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_segment_growth.png")


# ============================================================
# 6. GEOGRAPHIC REVENUE MIX
# ============================================================

def geographic_revenue(data):
    geo_rows = [x for x in rows(data, "geographic_metrics") if str(x.get("region", "")).strip()]
    if not geo_rows:
        return None

    period = most_common_period(geo_rows)
    if period is None:
        return None
    geo_rows = [x for x in geo_rows if str(x.get("period", "")).strip() == period]

    revenue_rows = {}
    for x in geo_rows:
        name = str(x.get("metric", "")).lower()
        if "revenue" not in name and "net sales" not in name:
            continue
        region = str(x.get("region")).strip()
        v = number(x.get("value"))
        if v is None:
            continue
        if region not in revenue_rows or v > number(revenue_rows[region].get("value")):
            revenue_rows[region] = x

    if len(revenue_rows) < 2:
        return None

    items = sorted(revenue_rows.values(), key=lambda x: number(x.get("value")), reverse=True)
    labels = [str(x.get("region")) for x in items]
    values = [number(x.get("value")) for x in items]
    unit = str(items[0].get("unit") or "Reported value")

    fig, ax = plt.subplots(figsize=(8.6, 4.2), dpi=220)
    # Uses its own colourful GEO_COLORS palette (rather than the shared
    # GREY_SERIES every other chart uses) -- a small set of named
    # regions reads better with distinct, saturated colors than with
    # the muted grey-blue ramp used for financial bar charts.
    colors = [GEO_COLORS[i % len(GEO_COLORS)] for i in range(len(labels))]
    bars = ax.bar(labels, values, color=colors, width=0.55, zorder=3)
    for rect, v in zip(bars, values):
        ax.text(rect.get_x() + rect.get_width() / 2, v, fmt_value(v), ha="center", va="bottom",
                fontsize=10, color=NAVY, fontweight="medium")

    style_ax(ax)
    ax.set_ylabel(f"{period} revenue, {unit}")
    title(ax, f"{company_name(data)} — Revenue by Geography ({period})")
    source_caption(fig, items)
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_geographic_revenue.png")


# ============================================================
# 7. CUSTOMER / EMPLOYEE METRIC (single snapshot or multi-year trend)
# ============================================================

def _single_or_trend_chart(data, field, label, filename_suffix):
    items = rows(data, field)
    items = [x for x in items if number(x.get("value")) is not None and year(x)]
    if not items:
        return None

    by_year = {}
    for x in items:
        by_year[year(x)] = x
    ordered = sorted(by_year.values(), key=lambda x: year(x))

    fig, ax = plt.subplots(figsize=(8.2, 4.0), dpi=220)

    if len(ordered) == 1:
        x = ordered[0]
        v = number(x.get("value"))
        bar_label = f"{label}, {x.get('period') or year(x)}"
        ax.bar([bar_label], [v], color=NAVY, width=0.4, zorder=3)
        ax.text(0, v, fmt_value(v), ha="center", va="bottom", fontsize=11, color=NAVY, fontweight="bold")
        ax.set_ylim(0, v * 1.25 if v else 1)
    else:
        labels = [str(x.get("period") or year(x)) for x in ordered]
        values = [number(x.get("value")) for x in ordered]
        ax.plot(labels, values, marker="o", linewidth=2.2, color=BLUE, markerfacecolor=NAVY, markersize=6, zorder=3)
        for lab, v in zip(labels, values):
            ax.annotate(fmt_value(v), xy=(lab, v), xytext=(0, 8), textcoords="offset points",
                        ha="center", fontsize=9, color=NAVY)

    style_ax(ax)
    ax.set_ylabel(str(ordered[-1].get("unit") or "Reported value"))
    title(ax, f"{company_name(data)} — {label}")
    source_caption(fig, ordered)
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_{filename_suffix}.png")


def customer_metric(data):
    return _single_or_trend_chart(data, "customer_metrics", "Customers / Users", "customer_metric")


def employee_metric(data):
    return _single_or_trend_chart(data, "employee_metrics", "Employees", "employee_metric")


# ============================================================
# 8. MARKET SIZE / CAGR + MARKET SHARE TREND
# ============================================================

def market_size(data):
    candidates = [
        x for x in rows(data, "market_metrics")
        if number(x.get("value")) is not None
        and "market share" not in str(x.get("metric", "")).lower()
    ]
    if not candidates:
        return None

    # A trend line must be the SAME metric measured at different times.
    # market_metrics can end up holding more than one kind of number in
    # a single run (e.g. Market Capitalization alongside a miscategorized
    # Operating Income) -- grouping by year alone, as this used to do,
    # could join two unrelated metrics with a connecting line just
    # because they landed in different years/periods, implying a trend
    # that never happened (e.g. a chart that looks like "market size"
    # crashed 99% when it was actually two different figures). Pick one
    # metric to chart: prefer "market cap" as the most literal reading of
    # "market size", otherwise whichever metric has the most distinct
    # years (the most meaningful real trend).
    by_metric = {}
    for x in candidates:
        key = str(x.get("metric", "")).strip().lower()
        by_metric.setdefault(key, []).append(x)

    def group_rank(item):
        metric_key, group = item
        is_market_cap = 1 if "market cap" in metric_key else 0
        distinct_years = len({year(x) for x in group if year(x) is not None})
        return (is_market_cap, distinct_years)

    metric_key, chosen = max(by_metric.items(), key=group_rank)

    by_year = {}
    for x in chosen:
        y = year(x)
        if y is None:
            continue
        if y not in by_year or number(x.get("value")) > number(by_year[y].get("value")):
            by_year[y] = x

    if not by_year:
        return None

    ordered = sorted(by_year.values(), key=lambda x: year(x))
    labels = [str(x.get("period") or year(x)) for x in ordered]
    values = [number(x.get("value")) for x in ordered]

    fig, ax = plt.subplots(figsize=(8.2, 4.0), dpi=220)
    if len(ordered) == 1:
        ax.bar(labels, values, color=NAVY, width=0.4, zorder=3)
        ax.text(0, values[0], fmt_value(values[0]), ha="center", va="bottom", fontsize=11, color=NAVY, fontweight="bold")
    else:
        ax.plot(labels, values, marker="o", linewidth=2.2, color=GOLD, markerfacecolor=NAVY, markersize=6, zorder=3)
        for lab, v in zip(labels, values):
            ax.annotate(fmt_value(v), xy=(lab, v), xytext=(0, 8), textcoords="offset points",
                        ha="center", fontsize=9, color=NAVY)

    style_ax(ax)
    ax.set_ylabel(str(ordered[-1].get("unit") or "Reported value"))
    # Name the actual metric in the title -- this was the root of the
    # confusion, so make it explicit rather than the generic "Market
    # Size" label every different underlying metric used to share.
    metric_label = str(chosen[0].get("metric") or metric_key.title())
    title(ax, f"{company_name(data)} — Market Size ({metric_label})")
    source_caption(fig, ordered)
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_market_size.png")


def market_share_trend(data):
    candidates = [
        x for x in rows(data, "market_metrics")
        if "market share" in str(x.get("metric", "")).lower()
        and number(x.get("value")) is not None
    ]
    if len(candidates) < 2:
        return None

    by_year = {}
    for x in candidates:
        by_year[year(x)] = x
    if len(by_year) < 2:
        return None

    ordered = sorted(by_year.items())
    labels = [str(y) for y, _ in ordered]
    values = [number(x.get("value")) for _, x in ordered]

    fig, ax = plt.subplots(figsize=(8.2, 4.0), dpi=220)
    ax.plot(labels, values, marker="o", linewidth=2.2, color=BLUE, markerfacecolor=NAVY, markersize=6, zorder=3)
    style_ax(ax)
    ax.set_ylabel("Percent")
    title(ax, f"{company_name(data)} — Market Share Trend")
    source_caption(fig, [x for _, x in ordered])
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_market_share_trend.png")


# ============================================================
# 9. COMPETITOR COMPARISON
# ============================================================

def competitor_comparison(data):
    comp_rows = [x for x in rows(data, "competitor_metrics") if str(x.get("competitor", "")).strip()]
    if not comp_rows:
        return None

    by_metric = {}
    for x in comp_rows:
        metric = str(x.get("metric", "")).strip().lower()
        by_metric.setdefault(metric, []).append(x)

    best_metric, best_rows = None, []
    for metric, group in by_metric.items():
        by_competitor = {}
        for x in group:
            comp = str(x.get("competitor")).strip()
            v = number(x.get("value"))
            if v is None:
                continue
            if comp not in by_competitor or v > number(by_competitor[comp].get("value")):
                by_competitor[comp] = x
        if len(by_competitor) >= 2 and len(by_competitor) > len(best_rows):
            best_metric, best_rows = metric, list(by_competitor.values())

    if len(best_rows) < 2:
        return None

    items = sorted(best_rows, key=lambda x: number(x.get("value")), reverse=True)
    labels = [str(x.get("competitor")) for x in items]
    values = [number(x.get("value")) for x in items]
    unit = str(items[0].get("unit") or "")
    company = company_name(data).lower()
    colors = [
        GOLD if (lab.lower() in company or company in lab.lower()) else NAVY
        for lab in labels
    ]

    fig, ax = plt.subplots(figsize=(8.6, 4.4), dpi=220)
    bars = ax.barh(range(len(labels)), values, color=colors, height=0.6, zorder=3)
    ax.invert_yaxis()
    for rect, v in zip(bars, values):
        suffix = "%" if "%" in unit else ""
        ax.text(rect.get_width(), rect.get_y() + rect.get_height() / 2, f" {fmt_value(v)}{suffix}",
                va="center", ha="left", fontsize=10, color=NAVY)
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=10.5)
    ax.xaxis.grid(True, color=LIGHT_GRID, linewidth=1, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right", "left"):
        ax.spines[spine].set_visible(False)
    ax.tick_params(length=0)
    title(ax, f"{company_name(data)} — Competitive Comparison ({best_metric.title()})")
    source_caption(fig, items)
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_competitor_comparison.png")


def market_composition(data):
    """Part-to-whole view of market share across named competitors, for
    the 'market size' section. A pie chart is a documented anti-pattern
    for this job (few/uneven slices, no direct axis for comparison) --
    a single 100%-stacked horizontal bar tells the same "who owns how
    much of the market" story while staying legible and gate-safe."""
    share_rows = [
        x for x in rows(data, "competitor_metrics")
        if "share" in str(x.get("metric", "")).lower()
        and str(x.get("competitor", "")).strip()
        and number(x.get("value")) is not None
    ]
    if not share_rows:
        return None

    by_competitor = {}
    for x in share_rows:
        comp = str(x.get("competitor")).strip()
        v = number(x.get("value"))
        # Some sources report share as a fraction (0.25) and others as
        # points (25) -- normalize both to percentage points.
        pct = v * 100 if v <= 1 else v
        if comp not in by_competitor or pct > by_competitor[comp][0]:
            by_competitor[comp] = (pct, x)

    if len(by_competitor) < 2:
        return None

    items = sorted(by_competitor.items(), key=lambda kv: kv[1][0], reverse=True)

    # Series-count ladder: cap at 4 named segments and fold the rest
    # into "Other" rather than adding more hues.
    MAX_SEGMENTS = 4
    kept = items[:MAX_SEGMENTS]
    folded = items[MAX_SEGMENTS:]

    labels = [name for name, _ in kept]
    values = [pct for _, (pct, _) in kept]
    source_items = [row for _, (_, row) in kept]

    folded_pct = sum(pct for _, (pct, _) in folded)
    known_total = sum(values) + folded_pct
    remainder = 100.0 - known_total
    if folded_pct > 0:
        labels.append("Other named competitors")
        values.append(folded_pct)
    if remainder > 0.5:
        labels.append("Rest of market")
        values.append(remainder)

    colors = (GREY_SERIES[:MAX_SEGMENTS] + [SLATE, LIGHT_GRID])[:len(labels)]
    # Keep the two synthetic buckets visually recessive regardless of
    # how many real competitors preceded them.
    for i, lab in enumerate(labels):
        if lab in ("Other named competitors", "Rest of market"):
            colors[i] = "#C3CBD3" if lab == "Other named competitors" else "#E4E8EC"

    fig, ax = plt.subplots(figsize=(8.6, 2.6), dpi=220)
    left = 0.0
    for lab, v, c in zip(labels, values, colors):
        ax.barh(0, v, left=left, color=c, height=0.5, zorder=3,
                edgecolor="white", linewidth=2)
        if v >= 6:
            text_color = "white" if c in (NAVY, BLUE, SLATE) else NAVY
            ax.text(left + v / 2, 0, f"{lab}\n{fmt_value(v)}%", ha="center", va="center",
                    fontsize=8.5, color=text_color, fontweight="bold")
        left += v

    ax.set_xlim(0, 100)
    ax.set_ylim(-0.5, 0.5)
    ax.axis("off")

    # Legend doubles as the direct-label fallback for any thin segment
    # that couldn't fit its own text.
    handles = [plt.Rectangle((0, 0), 1, 1, color=c) for c in colors]
    ax.legend(handles, labels, loc="upper center", bbox_to_anchor=(0.5, -0.15),
              ncol=min(3, len(labels)), frameon=False, fontsize=9)

    title(ax, f"{company_name(data)} — Market Share Composition")
    source_caption(fig, source_items)
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_market_composition.png")


# ============================================================
# 10. TIMELINE
# ============================================================

def timeline(data):
    events = []
    for x in data.get("timeline", []) if isinstance(data, dict) else []:
        if not isinstance(x, dict):
            continue
        # Timeline events don't always have a "VERIFIED" tag, so accept
        # them if they at least cite a source.
        has_citation = bool(str(x.get("source_title", "")).strip()) or bool(str(x.get("source_url", "")).strip())
        is_explicitly_verified = x.get("verification") == "VERIFIED"
        if not (has_citation or is_explicitly_verified):
            continue
        y = year({"year": x.get("date")})
        if y is None:
            m = re.search(r"(19|20)\d{2}", str(x.get("date")))
            y = int(m.group()) if m else None
        if y and x.get("event"):
            events.append((y, str(x["event"])))

    events = list(dict.fromkeys(events))
    if len(events) < 2:
        return None

    events.sort()
    years_list = [e[0] for e in events]
    span = max(years_list) - min(years_list) or 1

    # Spread out events that fall on the exact same year so the dots
    # don't overlap.
    jittered = []
    year_counts = {}
    year_seen = {}
    for y, _ in events:
        year_counts[y] = year_counts.get(y, 0) + 1
    for y, event in events:
        count = year_counts[y]
        idx = year_seen.get(y, 0)
        year_seen[y] = idx + 1
        dx = 0.0
        if count > 1:
            dx = (idx - (count - 1) / 2) * (span * 0.012)
        jittered.append((y + dx, y, event))

    # Alternate labels above/below the timeline, stacking them if two
    # events land close together (so text doesn't overlap).
    min_gap = span * 0.09
    last_x_by_side = {1: None, -1: None}
    level_by_side = {1: -1, -1: -1}
    placements = []

    for i, (x_pos, y, event) in enumerate(jittered):
        side = 1 if i % 2 == 0 else -1
        if last_x_by_side[side] is not None and (x_pos - last_x_by_side[side]) < min_gap:
            level_by_side[side] += 1
        else:
            level_by_side[side] = 0
        last_x_by_side[side] = x_pos
        placements.append((x_pos, y, event, side, level_by_side[side]))

    max_level = max(level for _, _, _, _, level in placements)
    fig_height = 3.6 + max_level * 0.55
    fig, ax = plt.subplots(figsize=(9.4, fig_height), dpi=220)

    ax.hlines(0, min(years_list) - span * 0.06, max(years_list) + span * 0.06,
              linewidth=2, color=SLATE, zorder=1)

    for x_pos, y, event, side, level in placements:
        yy = side * (0.20 + level * 0.20)
        ax.scatter([x_pos], [0], s=55, color=GOLD, zorder=3)
        short = event if len(event) <= 58 else event[:55] + "..."
        ax.annotate(f"{y}  •  {short}", xy=(x_pos, 0), xytext=(x_pos, yy), ha="center",
                    va="bottom" if side > 0 else "top", fontsize=8.5, textcoords="data", color=NAVY)
        ax.plot([x_pos, x_pos], [0, yy], linewidth=1, color=SLATE, zorder=2)

    pad = 0.20 + (max_level + 1) * 0.20
    ax.set_ylim(-pad, pad)
    ax.set_yticks([])
    ax.set_xlabel("Year")
    # Only show whole-year tick marks (the jitter above can create
    # fractional x-positions, which we don't want visible on the axis).
    ax.set_xticks(range(int(min(years_list)), int(max(years_list)) + 1))
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x)}"))
    title(ax, f"{company_name(data)} — Verified Company Timeline")
    ax.grid(axis="x", alpha=0.18)
    for spine in ("left", "right", "top"):
        ax.spines[spine].set_visible(False)
    source_caption(fig, [{"source_title": ""}])
    plt.tight_layout()
    return save(fig, f"{safe_filename(company_name(data))}_company_timeline.png")


# ============================================================
# 11. SECTION MAP + MAIN ENTRY POINT
# ============================================================

# Maps each chart to the report section it should appear next to.
CHART_SECTION_MAP = {
    "employee_metric": "company overview",
    "revenue_five_year": "financial performance",
    "revenue_outlook": "financial performance",
    "quarterly_revenue": "financial performance",
    "margin_trend": "financial performance",
    "fcf_trend": "financial performance",
    "segment_revenue": "business model",
    "segment_growth": "business model",
    "geographic_revenue": "business model",
    "customer_metric": "target customers",
    "market_size": "competitive landscape",
    "market_composition": "competitive landscape",
    "market_share_trend": "competitive landscape",
    "competitor_comparison": "competitive landscape",
    "company_timeline": "recent developments",
}


def generate_all_charts(structured_data):
    """Try to build every chart type. Returns {chart_key: file_path} --
    only for charts that had enough data. Never fakes a chart."""
    data = structured_data if isinstance(structured_data, dict) else {}

    generators = [
        ("revenue_five_year", revenue_five_year),
        ("revenue_outlook", revenue_outlook),
        ("quarterly_revenue", quarterly_revenue),
        ("margin_trend", margin_trend),
        ("fcf_trend", free_cash_flow_trend),
        ("employee_metric", employee_metric),
        ("segment_revenue", segment_revenue),
        ("segment_growth", segment_growth),
        ("geographic_revenue", geographic_revenue),
        ("customer_metric", customer_metric),
        ("market_size", market_size),
        ("market_composition", market_composition),
        ("market_share_trend", market_share_trend),
        ("competitor_comparison", competitor_comparison),
        ("company_timeline", timeline),
    ]

    charts = {}
    for key, generator in generators:
        try:
            path = generator(data)
        except Exception:
            path = None
        if path:
            charts[key] = path

    return charts

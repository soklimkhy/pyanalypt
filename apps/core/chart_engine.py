import numpy as np
import pandas as pd

AGGREGATIONS = ("sum", "mean", "count", "min", "max")
_MAX_LINE_POINTS = 5_000
_MAX_GROUPS = 20


def _s(v):
    """Serialize a scalar: NaN → None, numpy scalar → Python native."""
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    return v.item() if isinstance(v, np.generic) else v


def fmt_bar(df, x_col, y_col, agg="sum", group_by=None, limit=20):
    """
    Aggregate y_col by x_col and return an ECharts bar option dict.
    If group_by is given, returns one series per group (grouped bar).
    Returns the top `limit` x categories by total y magnitude.
    """
    if group_by:
        pivot = df.groupby([x_col, group_by])[y_col].agg(agg).unstack(fill_value=0)
        try:
            # Try to find top X by magnitude
            top_x = pivot.sum(axis=1).astype(float).abs().nlargest(limit).index
        except (ValueError, TypeError):
            top_x = pivot.index[:limit]
            
        pivot = pivot.loc[pivot.index.isin(top_x)].reindex(top_x)
        
        try:
            # Limit groups to prevent ECharts series explosion
            top_groups = pivot.astype(float).abs().sum(axis=0).nlargest(_MAX_GROUPS).index
            pivot = pivot[top_groups]
        except (ValueError, TypeError, KeyError):
            pass

        x_data = [str(v) for v in pivot.index.tolist()]
        series = [
            {
                "name": str(grp),
                "type": "bar",
                "data": [_s(v) for v in pivot[grp].tolist()],
            }
            for grp in pivot.columns
        ]
    else:
        grouped = df.groupby(x_col)[y_col].agg(agg)
        try:
            top_x = grouped.astype(float).abs().nlargest(limit).index
        except (ValueError, TypeError):
            top_x = grouped.index[:limit]
            
        grouped = grouped.reindex(top_x)
        x_data = [str(v) for v in grouped.index.tolist()]
        series = [
            {
                "name": y_col,
                "type": "bar",
                "data": [_s(v) for v in grouped.tolist()],
            }
        ]

    return {
        "chart_type": "bar",
        "xAxis": {"type": "category", "name": x_col, "data": x_data},
        "yAxis": {"type": "value", "name": f"{agg}({y_col})"},
        "series": series,
    }


def fmt_line(df, x_col, y_cols, sort=True):
    """
    Return an ECharts line option for one or more y_cols against x_col.
    Truncates to _MAX_LINE_POINTS after optional sort.
    """
    sub = df[[x_col] + y_cols].dropna(subset=[x_col])
    if sort:
        try:
            sub = sub.sort_values(x_col)
        except TypeError:
            pass
    if len(sub) > _MAX_LINE_POINTS:
        sub = sub.iloc[:_MAX_LINE_POINTS]

    x_data = [str(v) for v in sub[x_col].tolist()]
    series = [
        {
            "name": col,
            "type": "line",
            "data": [_s(v) for v in sub[col].tolist()],
        }
        for col in y_cols
    ]

    return {
        "chart_type": "line",
        "xAxis": {"type": "category", "name": x_col, "data": x_data},
        "yAxis": {"type": "value"},
        "series": series,
    }


def fmt_scatter(df, col_x, col_y, color_by=None, sample=500):
    """
    Return an ECharts scatter option.
    Pearson r is computed on the full valid set before sampling.
    If color_by is given, returns one series per group.
    """
    cols = [col_x, col_y] + ([color_by] if color_by else [])
    base = df[cols].dropna()

    corr_val = None
    if len(base) >= 3:
        try:
            corr_val = round(float(base[col_x].corr(base[col_y])), 4)
        except Exception:
            pass

    def _points(frame):
        xs = frame[col_x].tolist()
        ys = frame[col_y].tolist()
        return [[_s(x), _s(y)] for x, y in zip(xs, ys)]

    if color_by:
        series = []
        for grp_val, grp_df in base.groupby(color_by):
            if len(grp_df) > sample:
                grp_df = grp_df.sample(n=sample, random_state=42)
            series.append({
                "name": str(grp_val),
                "type": "scatter",
                "data": _points(grp_df),
            })
    else:
        if len(base) > sample:
            base = base.sample(n=sample, random_state=42)
        series = [
            {
                "name": f"{col_x} vs {col_y}",
                "type": "scatter",
                "data": _points(base),
            }
        ]

    return {
        "chart_type": "scatter",
        "xAxis": {"type": "value", "name": col_x},
        "yAxis": {"type": "value", "name": col_y},
        "pearson_r": corr_val,
        "series": series,
    }


def fmt_histogram(distribution_data):
    """
    Convert eda_distribution() output → dict of ECharts bar options keyed by column.
    Each column gets its own chart_type=histogram entry with bin labels and counts.
    """
    result = {}
    for col, stats in distribution_data.items():
        bins = stats.get("bins", [])
        x_data = [f"{b['range_start']}–{b['range_end']}" for b in bins]
        counts = [b["count"] for b in bins]
        result[col] = {
            "chart_type": "histogram",
            "xAxis": {"type": "category", "name": col, "data": x_data},
            "yAxis": {"type": "value", "name": "count"},
            "series": [{"name": col, "type": "bar", "data": counts}],
            "stats": {k: stats[k] for k in ("count", "mean", "std", "min", "max", "skewness", "kurtosis") if k in stats},
        }
    return result

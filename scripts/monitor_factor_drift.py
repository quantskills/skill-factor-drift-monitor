"""Monitor distribution and predictive drift for a multi-factor panel."""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

DEFAULT_INPUT = Path(__file__).resolve().parents[1] / "tests" / "synthetic_panel.csv"


def load_frame(source: str, query: str | None = None, sheet: str | int = 0, key: str | None = None) -> pd.DataFrame:
    lower = source.lower()
    if lower.startswith("sqlite:///"):
        if not query or not query.lstrip().lower().startswith("select"):
            raise ValueError("SQLite input requires a read-only SELECT query")
        with closing(sqlite3.connect(source[10:])) as connection:
            return pd.read_sql_query(query, connection)
    if "://" in source:
        if not query or not query.lstrip().lower().startswith("select"):
            raise ValueError("SQL input requires a read-only SELECT query")
        try:
            from sqlalchemy import create_engine
        except ImportError as exc:
            raise RuntimeError("Non-SQLite databases require SQLAlchemy and a database driver") from exc
        return pd.read_sql_query(query, create_engine(source))

    path = Path(source)
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    try:
        if suffix in {".xlsx", ".xls"}:
            return pd.read_excel(path, sheet_name=sheet)
        if suffix == ".parquet":
            return pd.read_parquet(path)
        if suffix in {".h5", ".hdf", ".hdf5"}:
            return pd.read_hdf(path, key=key)
    except ImportError as exc:
        raise RuntimeError(f"Missing optional dependency for {suffix}: {exc}") from exc
    if suffix in {".pkl", ".pickle"}:
        return pd.read_pickle(path)
    raise ValueError(f"Unsupported input format: {suffix or source}")


def normalize_panel(frame: pd.DataFrame, date_col: str, symbol_col: str) -> pd.DataFrame:
    if isinstance(frame.index, pd.MultiIndex) and {date_col, symbol_col}.issubset(frame.index.names):
        panel = frame.copy()
    else:
        missing = {date_col, symbol_col} - set(frame.columns)
        if missing:
            raise ValueError(f"Missing index columns: {sorted(missing)}")
        panel = frame.set_index([date_col, symbol_col])
    if panel.index.duplicated().any():
        examples = panel.index[panel.index.duplicated()].unique()[:5].tolist()
        raise ValueError(f"Duplicate (date, symbol) rows, examples: {examples}")
    raw_dates = panel.index.get_level_values(date_col)
    date_text = pd.Series(raw_dates.astype(str), dtype="string")
    if date_text.str.fullmatch(r"\d{8}").all():
        dates = pd.to_datetime(date_text, format="%Y%m%d", errors="raise")
    else:
        dates = pd.to_datetime(raw_dates, errors="raise")
    symbols = panel.index.get_level_values(symbol_col).astype(str)
    panel.index = pd.MultiIndex.from_arrays([dates, symbols], names=[date_col, symbol_col])
    return panel.sort_index().replace([np.inf, -np.inf], np.nan)


def display_order(panel: pd.DataFrame, date_col: str = "date", symbol_col: str = "symbol") -> pd.DataFrame:
    ordered = panel.reset_index().sort_values([symbol_col, date_col], ascending=[True, False])
    return ordered.set_index([date_col, symbol_col])


def ensure_return_columns(panel: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    """Create forward 1-day/20-day returns from close when needed for IC."""
    if "return_20" in panel.columns:
        return panel, "return_20"
    if "close" not in panel.columns:
        raise ValueError(
            "IC requires return_20. The input has neither return_20 nor close; "
            "please provide one of these columns."
        )

    result = panel.sort_index(level=[1, 0]).copy()
    close = pd.to_numeric(result["close"], errors="coerce")
    grouped = close.groupby(level=1, sort=False)
    if "return" not in result.columns:
        result["return"] = grouped.shift(-1) / close - 1
    result["return_20"] = grouped.shift(-20) / close - 1
    return result, "return_20"


def psi(reference: pd.Series, current: pd.Series, bins: int = 10) -> float:
    ref = reference.dropna().to_numpy(dtype=float)
    cur = current.dropna().to_numpy(dtype=float)
    if len(ref) < bins * 2 or len(cur) < bins * 2:
        return math.nan
    edges = np.unique(np.quantile(ref, np.linspace(0, 1, bins + 1)))
    if len(edges) < 3:
        return 0.0 if np.allclose(np.nanmean(ref), np.nanmean(cur)) else math.nan
    edges[0], edges[-1] = -np.inf, np.inf
    ref_count = np.histogram(ref, bins=edges)[0] / len(ref)
    cur_count = np.histogram(cur, bins=edges)[0] / len(cur)
    ref_count = np.clip(ref_count, 1e-6, None)
    cur_count = np.clip(cur_count, 1e-6, None)
    return float(np.sum((cur_count - ref_count) * np.log(cur_count / ref_count)))


def ks_distance(reference: pd.Series, current: pd.Series) -> float:
    ref = np.sort(reference.dropna().to_numpy(dtype=float))
    cur = np.sort(current.dropna().to_numpy(dtype=float))
    if not len(ref) or not len(cur):
        return math.nan
    points = np.sort(np.unique(np.concatenate([ref, cur])))
    return float(np.max(np.abs(np.searchsorted(ref, points, side="right") / len(ref) - np.searchsorted(cur, points, side="right") / len(cur))))


def daily_rank_ic(panel: pd.DataFrame, factor: str, return_col: str) -> pd.Series:
    def correlation(group: pd.DataFrame) -> float:
        valid = group[[factor, return_col]].dropna()
        if len(valid) < 5 or valid[factor].nunique() < 2 or valid[return_col].nunique() < 2:
            return math.nan
        return float(valid[factor].rank().corr(valid[return_col].rank()))

    return panel.groupby(level=0, sort=True).apply(correlation, include_groups=False)


def status_for(row: dict[str, Any], has_return: bool) -> tuple[str, list[str]]:
    reasons: list[str] = []
    severity = 0
    if row["missing_rate"] >= 0.20 or row["missing_rate_change"] >= 0.10:
        severity = max(severity, 2)
        reasons.append(f"missing_rate={row['missing_rate']:.1%}")
    if not math.isnan(row["psi"]) and row["psi"] >= 0.10:
        severity = max(severity, 1 if row["psi"] < 0.25 else 2)
        reasons.append(f"PSI={row['psi']:.3f}")
    if not math.isnan(row["ks"]) and row["ks"] >= 0.20:
        severity = max(severity, 2)
        reasons.append(f"KS={row['ks']:.3f}")
    if not math.isnan(row["mean_shift_std"]) and abs(row["mean_shift_std"]) >= 1:
        severity = max(severity, 2)
        reasons.append(f"mean_shift={row['mean_shift_std']:.2f}sd")
    if has_return and not math.isnan(row["baseline_ic"]) and not math.isnan(row["window_ic"]):
        if row["baseline_ic"] * row["window_ic"] < 0 and abs(row["baseline_ic"]) >= 0.01:
            severity = max(severity, 3)
            reasons.append("IC sign reversal")
        elif abs(row["baseline_ic"]) >= 0.01 and row["ic_retention"] < 0.5:
            severity = max(severity, 2)
            reasons.append(f"IC retention={row['ic_retention']:.2f}")
    low_confidence = row["symbols"] < 5 or row["rows"] < 100
    if low_confidence:
        reasons.append("low confidence: small sample")
        # Distribution statistics alone are not enough for a warning on tiny universes.
        distribution_only = all(reason.startswith(("PSI=", "KS=", "mean_shift=")) for reason in reasons[:-1])
        severity = 1 if distribution_only else max(severity, 1)
    return ("normal", "watch", "warning", "failed")[severity], reasons


def quality_summary(panel: pd.DataFrame) -> dict[str, Any]:
    """Return panel-level checks that distribution statistics cannot represent."""
    columns = set(panel.columns)
    summary: dict[str, Any] = {
        "rows": int(len(panel)),
        "symbols": int(panel.index.get_level_values(1).nunique()),
        "start": str(panel.index.get_level_values(0).min().date()),
        "end": str(panel.index.get_level_values(0).max().date()),
        "duplicate_keys": int(panel.index.duplicated().sum()),
        "missing_cells": int(panel.isna().sum().sum()),
    }
    price_columns = [column for column in ("open", "high", "low", "close") if column in columns]
    summary["nonpositive_price_rows"] = int((panel[price_columns] <= 0).any(axis=1).sum()) if price_columns else 0
    if {"open", "high", "low", "close"}.issubset(columns):
        high_floor = panel[["open", "low", "close"]].max(axis=1)
        low_ceiling = panel[["open", "high", "close"]].min(axis=1)
        summary["ohlc_violation_rows"] = int(((panel["high"] < high_floor) | (panel["low"] > low_ceiling)).sum())
    else:
        summary["ohlc_violation_rows"] = None
    return summary


def monitor(panel: pd.DataFrame, factors: list[str], return_col: str | None, baseline_end: str | None, freq: str) -> pd.DataFrame:
    panel = panel.sort_index(level=[1, 0])
    dates = panel.index.get_level_values(0).unique().sort_values()
    if len(dates) < 4:
        raise ValueError("At least four distinct dates are required")
    cutoff = pd.Timestamp(baseline_end) if baseline_end else dates[len(dates) // 2 - 1]
    baseline = panel.loc[panel.index.get_level_values(0) <= cutoff]
    monitored = panel.loc[panel.index.get_level_values(0) > cutoff]
    if baseline.empty or monitored.empty:
        raise ValueError("Baseline and monitoring periods must both contain rows")
    period_groups = monitored.groupby(monitored.index.get_level_values(0).to_period(freq))
    rows: list[dict[str, Any]] = []
    for factor in factors:
        base_values = baseline[factor]
        base_std = float(base_values.std())
        base_ic_series = daily_rank_ic(baseline, factor, return_col) if return_col else pd.Series(dtype=float)
        base_ic = float(base_ic_series.mean()) if not base_ic_series.empty else math.nan
        for period, window in period_groups:
            values = window[factor]
            window_ic_series = daily_rank_ic(window, factor, return_col) if return_col else pd.Series(dtype=float)
            window_ic = float(window_ic_series.mean()) if not window_ic_series.empty else math.nan
            row: dict[str, Any] = {
                "factor": factor,
                "window": str(period),
                "start": str(window.index.get_level_values(0).min().date()),
                "end": str(window.index.get_level_values(0).max().date()),
                "rows": int(len(window)),
                "symbols": int(window.index.get_level_values(1).nunique()),
                "confidence": "low" if window.index.get_level_values(1).nunique() < 5 or len(window) < 100 else "standard",
                "missing_rate": float(values.isna().mean()),
                "missing_rate_change": float(values.isna().mean() - base_values.isna().mean()),
                "mean_shift_std": float((values.mean() - base_values.mean()) / base_std) if base_std > 0 else math.nan,
                "std_ratio": float(values.std() / base_std) if base_std > 0 else math.nan,
                "psi": psi(base_values, values),
                "ks": ks_distance(base_values, values),
                "baseline_ic": base_ic,
                "window_ic": window_ic,
                "ic_retention": float(abs(window_ic) / abs(base_ic)) if return_col and abs(base_ic) > 1e-12 else math.nan,
                "ic_days": int(window_ic_series.notna().sum()),
            }
            row["status"], row["reasons"] = status_for(row, return_col is not None)
            rows.append(row)
    return pd.DataFrame(rows)


def json_value(value: Any) -> Any:
    if isinstance(value, (np.integer, np.floating)):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        default=str(DEFAULT_INPUT),
        help=f"File path or SQLAlchemy/SQLite URI (default: {DEFAULT_INPUT})",
    )
    parser.add_argument("--query", help="Read-only SELECT query for SQL input")
    parser.add_argument("--sheet", default=0, help="Excel sheet name or index")
    parser.add_argument("--key", help="HDF5 key")
    parser.add_argument("--date-col", default="date")
    parser.add_argument("--symbol-col", default="symbol")
    parser.add_argument("--factors", help="Comma-separated factor columns; defaults to numeric columns")
    parser.add_argument(
        "--return-col",
        help="IC target column; defaults to return_20, derived from close when absent",
    )
    parser.add_argument("--baseline-end", help="Inclusive baseline end date; default is first 50%% of dates")
    parser.add_argument("--freq", default="M", help="Pandas period frequency, e.g. M or Q")
    parser.add_argument("--output", default="factor_drift_report", help="Output path prefix")
    args = parser.parse_args()

    sheet: str | int = int(args.sheet) if str(args.sheet).isdigit() else args.sheet
    panel = normalize_panel(load_frame(args.input, args.query, sheet, args.key), args.date_col, args.symbol_col)
    if args.return_col:
        return_col = args.return_col
        if return_col == "return_20" and return_col not in panel.columns:
            panel, return_col = ensure_return_columns(panel)
    elif "close" in panel.columns or "return_20" in panel.columns:
        panel, return_col = ensure_return_columns(panel)
    else:
        return_col = None
    panel = display_order(panel, args.date_col, args.symbol_col)
    quality = quality_summary(panel)
    excluded = {"return", "return_20", return_col}
    factors = [x.strip() for x in args.factors.split(",") if x.strip()] if args.factors else [c for c in panel.select_dtypes(include="number").columns if c not in excluded]
    required = factors + ([return_col] if return_col else [])
    missing = set(required) - set(panel.columns)
    if missing:
        raise ValueError(f"Missing requested columns: {sorted(missing)}")
    if not factors:
        raise ValueError("No numeric factor columns found")

    report = monitor(panel, factors, return_col, args.baseline_end, args.freq)
    output = Path(args.output)
    report.to_csv(output.with_suffix(".csv"), index=False, encoding="utf-8-sig")
    payload = {
        "input": args.input,
        "index": [args.date_col, args.symbol_col],
        "factors": factors,
        "return_col": return_col,
        "baseline_end": args.baseline_end,
        "frequency": args.freq,
        "quality": quality,
        "results": [{key: json_value(value) for key, value in row.items()} for row in report.to_dict("records")],
    }
    output.with_suffix(".json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(report.to_string(index=False))
    print(f"Wrote {output.with_suffix('.csv')} and {output.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""
Performance metrics – mirrors PerformanceMetrics from the notebook.
"""

import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


def _daily_returns(values: np.ndarray) -> np.ndarray:
    r = np.diff(values) / np.where(values[:-1] == 0, np.nan, values[:-1])
    return r[np.isfinite(r)]


def compute_metrics(daily_values: list[dict],
                    initial_capital: float,
                    bench_df=None,
                    risk_free: float = 0.0) -> dict:
    """Compute comprehensive performance metrics matching the notebook."""

    if len(daily_values) < 5:
        return {}

    values = np.array([d["portfolio"] for d in daily_values], dtype=float)
    dates  = [d["date"] for d in daily_values]
    dr     = _daily_returns(values)

    if len(dr) == 0:
        return {}

    rf_daily = (1 + risk_free) ** (1 / 252) - 1

    # ── Returns ───────────────────────────────────────────────────────────────
    total_return = (values[-1] / initial_capital - 1) * 100
    years        = len(values) / 252
    cagr         = ((values[-1] / initial_capital) ** (1 / max(years, 0.01)) - 1) * 100

    # ── Risk ──────────────────────────────────────────────────────────────────
    volatility   = dr.std() * np.sqrt(252) * 100

    # ── Sharpe ────────────────────────────────────────────────────────────────
    sharpe = ((dr.mean() - rf_daily) / dr.std() * np.sqrt(252)
              if dr.std() > 0 else 0.0)

    # Rolling Sharpe (last 63 trading days ≈ 3 months)
    roll_window = min(63, len(dr))
    roll_dr     = dr[-roll_window:]
    rolling_sharpe = ((roll_dr.mean() - rf_daily) / roll_dr.std() * np.sqrt(252)
                      if roll_dr.std() > 0 else sharpe)

    # ── Drawdown ──────────────────────────────────────────────────────────────
    peaks     = np.maximum.accumulate(values)
    dd_series = (values - peaks) / peaks * 100
    max_dd    = float(dd_series.min())
    calmar    = cagr / abs(max_dd) if abs(max_dd) > 0.01 else 0.0

    # Current drawdown
    current_dd = float(dd_series[-1])
    max_today_dd = float(dd_series[-min(5, len(dd_series)):].min())

    # ── Downside risk ─────────────────────────────────────────────────────────
    downside = dr[dr < 0]
    sortino  = ((dr.mean() - rf_daily) / downside.std() * np.sqrt(252)
                if len(downside) > 1 else 0.0)

    # Omega ratio
    threshold = 0.0
    gains  = (dr - threshold)[dr > threshold].sum()
    losses = abs((dr - threshold)[dr < threshold].sum())
    omega  = gains / losses if losses > 0 else float("inf")

    # VaR / CVaR
    var_95  = float(np.percentile(dr, 5) * 100)
    cvar_95 = float(dr[dr <= np.percentile(dr, 5)].mean() * 100)

    # ── Beta / Alpha (vs benchmark) ───────────────────────────────────────────
    beta, alpha = 0.0, 0.0
    if bench_df is not None and len(bench_df) > 10:
        if isinstance(bench_df, pd.Series):
            bench_close = bench_df
        else:
            bench_close = bench_df["close"] if "close" in bench_df.columns else bench_df
        bench_r     = _daily_returns(bench_close.values)
        min_len     = min(len(dr), len(bench_r))
        if min_len > 10:
            p = dr[-min_len:]
            b = bench_r[-min_len:]
            cov_mat = np.cov(p, b)
            beta    = cov_mat[0, 1] / cov_mat[1, 1] if cov_mat[1, 1] > 0 else 0.0
            alpha   = (p.mean() * 252 - risk_free) - beta * (b.mean() * 252 - risk_free)

    # ── Month-to-date ─────────────────────────────────────────────────────────
    # Find start of current month in daily_values
    today = pd.Timestamp(dates[-1])
    month_start = today.replace(day=1)
    mtd_values = [d["portfolio"] for d in daily_values
                  if pd.Timestamp(d["date"]) >= month_start]
    if len(mtd_values) >= 2:
        mtd_pct = round((mtd_values[-1] / mtd_values[0] - 1) * 100, 2)
    else:
        mtd_pct = round((values[-1] / values[max(0, len(values) - 22)] - 1) * 100, 2)

    # ── Win / loss from trades ─────────────────────────────────────────────────
    # These are computed separately if trades are passed in

    return {
        "totalReturn":      round(total_return, 2),
        "cagr":             round(cagr, 2),
        "sharpe":           round(sharpe, 3),
        "rollingSharpe":    round(rolling_sharpe, 3),
        "maxDrawdown":      round(max_dd, 2),
        "currentDrawdown":  round(current_dd, 2),
        "maxTodayDrawdown": round(max_today_dd, 2),
        "calmar":           round(calmar, 3),
        "volatility":       round(volatility, 2),
        "sortino":          round(sortino, 3),
        "omega":            round(omega, 3),
        "var95":            round(var_95, 3),
        "cvar95":           round(cvar_95, 3),
        "beta":             round(beta, 3),
        "alpha":            round(alpha * 100, 3),
        "mtdPct":           mtd_pct,
    }


def trade_stats(trades: list[dict]) -> dict:
    """Win rate, avg P&L, realized P&L today."""
    if not trades:
        return {"winRate": 0.0, "realizedPnL": 0.0, "avgPnL": 0.0, "totalTrades": 0}

    pnls     = [t["pnl"] for t in trades]
    wins     = sum(1 for p in pnls if p > 0)
    win_rate = wins / len(pnls) * 100

    # "Today" = last available trade date
    if trades:
        last_date = trades[-1]["exit_date"]
        today_pnl = sum(t["pnl"] for t in trades if t["exit_date"] == last_date)
    else:
        today_pnl = 0.0

    return {
        "winRate":       round(win_rate, 1),
        "realizedPnL":   round(today_pnl, 2),
        "avgPnL":        round(float(np.mean(pnls)), 2),
        "totalTrades":   len(trades),
    }


def drawdown_series(daily_values: list[dict]) -> list[dict]:
    """Return drawdown % at each date."""
    values = np.array([d["portfolio"] for d in daily_values], dtype=float)
    peaks  = np.maximum.accumulate(values)
    dd     = (values - peaks) / peaks * 100
    return [{"date": daily_values[i]["date"], "drawdown": round(float(dd[i]), 2)}
            for i in range(len(daily_values))]


def sparkline_data(daily_values: list[dict],
                   trades: list[dict],
                   n: int = 12) -> dict:
    """Return last-n data points for dashboard sparklines."""
    recent  = daily_values[-n:]
    port_sp = [round(d["portfolio"] / 1000, 2) for d in recent]

    # P&L sparkline: daily change in thousands
    values  = [d["portfolio"] for d in daily_values]
    diffs   = np.diff(values) / 1000
    pnl_sp  = [round(float(x), 2) for x in diffs[-n + 1:]]
    if len(pnl_sp) < n:
        pnl_sp = [0.0] * (n - len(pnl_sp)) + pnl_sp

    # Sharpe sparkline: rolling 21-day Sharpe
    dr       = np.diff(values) / np.where(np.array(values[:-1]) == 0, 1, values[:-1])
    rf_daily = 0.0
    sharpe_sp = []
    for i in range(max(0, len(dr) - n), len(dr)):
        win = dr[max(0, i - 20): i + 1]
        s = ((win.mean() - rf_daily) / win.std() * np.sqrt(252)
             if win.std() > 0 else 0.0)
        sharpe_sp.append(round(s, 3))

    return {"portfolio": port_sp, "pnl": pnl_sp, "sharpe": sharpe_sp}

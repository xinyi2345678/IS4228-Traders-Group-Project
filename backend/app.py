"""
Flask API – serves trading system data to the React frontend.
Run: python backend/app.py
"""

import os
import sys
import json
import logging
import threading
import time
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from flask import Flask, jsonify, request
from flask_cors import CORS

# Add backend dir to path
sys.path.insert(0, os.path.dirname(__file__))

from trading import (TICKERS, COMPANY_NAMES, SECTOR_MAP, SECTOR_COLORS,
                     DEFAULT_PARAMS, INITIAL_CAPITAL)
from optimizer import optimize_portfolio
from performance import compute_metrics, trade_stats, drawdown_series, sparkline_data
import ai_service

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, origins=["http://localhost:5173", "http://127.0.0.1:5173"])
APP_START = pd.Timestamp("2025-01-01")

# ── In-memory cache ───────────────────────────────────────────────────────────

_cache: dict = {
    "state":      "loading",   # "loading" | "ready" | "error"
    "error":      None,
    "results":    None,
    "opt":        None,
    "metrics":    None,
    "tstats":     None,
    "loaded_at":  None,
}


def _window_daily_values(results: dict) -> list[dict]:
    return [
        row for row in results.get("daily_values", [])
        if pd.Timestamp(row["date"]) >= APP_START
    ]


def _window_benchmark(bench_df):
    if bench_df is None:
        return None
    if isinstance(bench_df, pd.Series):
        return bench_df[bench_df.index >= APP_START]
    if hasattr(bench_df, "loc"):
        return bench_df.loc[bench_df.index >= APP_START]
    return bench_df


def _window_trades(results: dict) -> list[dict]:
    out = []
    for trade in results.get("trades", []):
        exit_date = trade.get("exit_date")
        if exit_date is None or pd.Timestamp(exit_date) >= APP_START:
            out.append(trade)
    return out


def _window_signals(results: dict) -> list[dict]:
    out = []
    for signal in results.get("signals", []):
        signal_date = signal.get("date")
        signal_ts = pd.to_datetime(signal_date, errors="coerce")
        if signal_date is None or pd.isna(signal_ts) or signal_ts >= APP_START:
            out.append(signal)
    return out


def _window_price_returns(results: dict) -> dict:
    out = {}
    for ticker, series in (results.get("price_returns", {}) or {}).items():
        if hasattr(series, "index"):
            out[ticker] = series[series.index >= APP_START]
        else:
            out[ticker] = series
    return out


# ── Background data loader ────────────────────────────────────────────────────

def _load():
    try:
        logger.info("=== Starting full strategy backtest ===")
        from trading import run_full_strategy
        results = run_full_strategy()
        _cache["results"] = results

        logger.info("=== Running portfolio optimiser ===")
        opt = optimize_portfolio(results["optimizer_history"])
        _cache["opt"] = opt

        logger.info("=== Computing performance metrics ===")
        app_daily_values = _window_daily_values(results)
        app_benchmark = _window_benchmark(results.get("bench_df"))
        app_trades = _window_trades(results)
        app_initial_capital = (
            float(app_daily_values[0]["portfolio"])
            if app_daily_values else results["initial_capital"]
        )

        metrics = compute_metrics(
            app_daily_values,
            app_initial_capital,
            app_benchmark,
        )
        tstats  = trade_stats(app_trades)
        metrics.update(tstats)
        _cache["metrics"]   = metrics
        _cache["tstats"]    = tstats
        _cache["state"]     = "ready"
        _cache["loaded_at"] = datetime.now().isoformat()
        logger.info("=== Data ready ===")

    except Exception as exc:
        logger.exception("Data load failed")
        _cache["state"] = "error"
        _cache["error"] = str(exc)


threading.Thread(target=_load, daemon=True).start()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _require_ready():
    if _cache["state"] != "ready":
        return jsonify({"status": _cache["state"],
                        "error":  _cache.get("error")}), 503
    return None


def _format_stocks(opt: dict, current_prices: dict, results: dict) -> list:
    """Build the stocks[] array the frontend expects."""
    allocations = opt.get("allocations", {})
    indiv       = opt.get("individual_metrics", {})
    corr        = opt.get("corr_to_port", {})
    total_val   = results["daily_values"][-1]["portfolio"] if results["daily_values"] else INITIAL_CAPITAL

    stocks = []
    for ticker in TICKERS:
        if ticker not in allocations:
            continue
        w     = allocations[ticker]
        price = current_prices.get(ticker, {}).get("price", 0)
        chg   = current_prices.get(ticker, {}).get("change", 0)
        val   = round(w * total_val, 0)
        shares = int(val / price) if price > 0 else 0

        # Beta: approximate from stock returns
        beta = 1.0
        sr = _window_price_returns(results).get(ticker)
        bench_df = _window_benchmark(results.get("bench_df"))
        if sr is not None and bench_df is not None and len(bench_df) > 10:
            if hasattr(bench_df, "columns") and "close" in bench_df.columns:
                br = bench_df["close"].pct_change().dropna()
            else:
                br = pd.Series(bench_df).pct_change().dropna()
            min_len = min(len(sr), len(br))
            if min_len > 20:
                cov_m = np.cov(sr.values[-min_len:], br.values[-min_len:])
                beta  = round(float(cov_m[0, 1] / cov_m[1, 1]), 3) if cov_m[1, 1] > 0 else 1.0

        stocks.append({
            "ticker":     ticker,
            "name":       COMPANY_NAMES.get(ticker, ticker),
            "weight":     round(w * 100, 1),
            "value":      int(val),
            "sector":     SECTOR_MAP.get(ticker, "Other"),
            "shares":     shares,
            "price":      price,
            "change":     chg,
            "beta":       beta,
            "annReturn":  indiv.get(ticker, {}).get("return", 0),
            "volatility": indiv.get(ticker, {}).get("volatility", 0),
            "corrToPort": corr.get(ticker, 0),
        })

    return sorted(stocks, key=lambda s: s["weight"], reverse=True)


def _format_signals(raw_signals: list, n: int = 20) -> list:
    """Convert simulation signals to frontend shape."""
    out = []
    for s in reversed(raw_signals[-n * 3:]):          # recent first
        out.append({
            "time":     s.get("time", s.get("date", "")),
            "ticker":   s["ticker"],
            "action":   s["action"],
            "type":     s["type"],
            "strength": s.get("strength"),
            "detail":   s.get("detail", ""),
            "entry_price": s.get("entry_price") or s.get("exit_price"),
            "tp":  s.get("tp"),
            "sl":  s.get("sl"),
            "atr": s.get("atr"),
            "pnl": s.get("pnl"),
        })
        if len(out) >= n:
            break
    return out


def _format_positions(final_positions: dict, current_prices: dict,
                       current_atr: dict) -> list:
    out = []
    for ticker, pos in final_positions.items():
        price   = current_prices.get(ticker, {}).get("price", pos["entry_price"])
        if pos["direction"] == "LONG":
            pnl     = round((price - pos["entry_price"]) * pos["shares"], 2)
            pnl_pct = round((price / pos["entry_price"] - 1) * 100, 2)
        else:
            pnl     = round((pos["entry_price"] - price) * pos["shares"], 2)
            pnl_pct = round((1 - price / pos["entry_price"]) * 100, 2)

        out.append({
            "ticker":    ticker,
            "direction": pos["direction"],
            "leg":       pos.get("leg", ""),
            "entry":     pos["entry_price"],
            "current":   price,
            "pnl":       pnl,
            "pnlPercent": pnl_pct,
            "sl":        round(pos["sl"], 2),
            "tp":        round(pos["tp"], 2),
        })
    return sorted(out, key=lambda p: abs(p["pnl"]), reverse=True)


def _sector_breakdown(stocks: list) -> list:
    sector_totals: dict[str, float] = {}
    for s in stocks:
        sector_totals[s["sector"]] = sector_totals.get(s["sector"], 0) + s["weight"]
    return [{"name": k, "value": round(v, 1), "color": SECTOR_COLORS.get(k, "#8B949E")}
            for k, v in sorted(sector_totals.items(), key=lambda x: -x[1])]


def _sector_exposure(final_positions: dict, current_prices: dict, total_val: float) -> list:
    sector_exp: dict[str, float] = {}
    for ticker, pos in final_positions.items():
        sector = SECTOR_MAP.get(ticker, "Other")
        price  = current_prices.get(ticker, {}).get("price", pos["entry_price"])
        val    = price * pos["shares"] / total_val * 100
        sign   = 1 if pos["direction"] == "LONG" else -1
        sector_exp[sector] = sector_exp.get(sector, 0) + sign * val

    return [{"sector": k, "exposure": round(v, 1)}
            for k, v in sorted(sector_exp.items(), key=lambda x: -abs(x[1]))]


def _build_ai_context() -> dict:
    if _cache["state"] != "ready" or not _cache.get("results"):
        return {}

    results = _cache["results"]
    metrics = _cache.get("metrics", {}) or {}
    opt = _cache.get("opt", {}) or {}
    dv = _window_daily_values(results)
    if not dv:
        return {"metrics": metrics}

    latest = dv[-1]
    prev = dv[-2] if len(dv) >= 2 else latest
    first = dv[0]

    latest_portfolio = float(latest.get("portfolio", INITIAL_CAPITAL))
    prev_portfolio = float(prev.get("portfolio", latest_portfolio))
    portfolio_day_change_pct = ((latest_portfolio / prev_portfolio) - 1) * 100 if prev_portfolio else 0.0

    benchmark_now = latest.get("benchmark")
    benchmark_prev = prev.get("benchmark", benchmark_now)
    benchmark_start = first.get("benchmark", benchmark_now)
    benchmark_day_change_pct = 0.0
    benchmark_total_return_pct = 0.0
    if benchmark_now and benchmark_prev:
        benchmark_day_change_pct = ((benchmark_now / benchmark_prev) - 1) * 100 if benchmark_prev else 0.0
    if benchmark_now and benchmark_start:
        benchmark_total_return_pct = ((benchmark_now / benchmark_start) - 1) * 100 if benchmark_start else 0.0

    final_positions = results.get("final_positions", {})
    n_long = sum(1 for p in final_positions.values() if p.get("direction") == "LONG")
    n_short = sum(1 for p in final_positions.values() if p.get("direction") == "SHORT")

    stocks = _format_stocks(opt, results.get("current_prices", {}), results)
    top_holdings = [
        {
            "ticker": s["ticker"],
            "weightPct": round(s["weight"], 1),
            "sector": s["sector"],
            "dayChangePct": round(s["change"], 2),
        }
        for s in stocks[:5]
    ]

    movers = sorted(
        [
            {
                "ticker": ticker,
                "price": round(info.get("price", 0), 2),
                "changePct": round(info.get("change", 0), 2),
            }
            for ticker, info in results.get("current_prices", {}).items()
        ],
        key=lambda item: abs(item["changePct"]),
        reverse=True,
    )[:5]

    recent_signals = [
        {
            "time": signal["time"],
            "ticker": signal["ticker"],
            "action": signal["action"],
            "type": signal["type"],
            "detail": (signal.get("detail") or "")[:140],
        }
        for signal in _format_signals(_window_signals(results), n=5)
    ]

    return {
        "asOf": pd.Timestamp(latest["date"]).strftime("%Y-%m-%d"),
        "metrics": {
            "totalReturnPct": round(metrics.get("totalReturn", 0), 2),
            "mtdPct": round(metrics.get("mtdPct", 0), 2),
            "sharpe": round(metrics.get("sharpe", 0), 2),
            "volatilityPct": round(metrics.get("volatility", 0), 2),
            "currentDrawdownPct": round(metrics.get("currentDrawdown", 0), 2),
            "maxDrawdownPct": round(metrics.get("maxDrawdown", 0), 2),
            "winRatePct": round(metrics.get("winRate", 0), 2),
        },
        "strategy": {
            "name": "MACD-BB-ATR",
            "rebalanceDays": results.get("params", {}).get("rebalance_freq"),
            "selectedTickers": results.get("selected_tickers", []),
        },
        "market": {
            "benchmark": {
                "symbol": "SPY",
                "value": round(float(benchmark_now), 2) if benchmark_now else None,
                "dayChangePct": round(benchmark_day_change_pct, 2),
                "totalReturnPct": round(benchmark_total_return_pct, 2),
            },
            "portfolio": {
                "value": round(latest_portfolio, 2),
                "dayChangePct": round(portfolio_day_change_pct, 2),
                "totalReturnPct": round(metrics.get("totalReturn", 0), 2),
                "mtdPct": round(metrics.get("mtdPct", 0), 2),
                "currentDrawdownPct": round(metrics.get("currentDrawdown", 0), 2),
                "maxDrawdownPct": round(metrics.get("maxDrawdown", 0), 2),
                "sharpe": round(metrics.get("sharpe", 0), 2),
                "volatilityPct": round(metrics.get("volatility", 0), 2),
            },
            "positions": {
                "long": n_long,
                "short": n_short,
                "activeCount": len(final_positions),
                "activeTickers": sorted(final_positions.keys()),
            },
            "topHoldings": top_holdings,
            "topMovers": movers,
            "recentSignals": recent_signals,
        },
    }


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/api/status")
def status():
    return jsonify({
        "status":    _cache["state"],
        "error":     _cache.get("error"),
        "loadedAt":  _cache.get("loaded_at"),
    })


@app.route("/api/dashboard")
def dashboard():
    err = _require_ready()
    if err:
        return err

    results = _cache["results"]
    opt     = _cache["opt"]
    metrics = _cache["metrics"]
    dv      = _window_daily_values(results)
    total   = dv[-1]["portfolio"]
    prev    = dv[-2]["portfolio"] if len(dv) >= 2 else total

    day_pnl     = round(total - prev, 2)
    day_pnl_pct = round((total / prev - 1) * 100, 2) if prev > 0 else 0

    signals  = _format_signals(_window_signals(results), n=10)
    stocks   = _format_stocks(opt, results["current_prices"], results)
    sparks   = sparkline_data(dv, _window_trades(results), n=12)

    chart_rows = dv

    # Equity curve: dashboard display from 2025-01-01 to today
    equity_curve = []
    peak = None
    for row in chart_rows:
        entry = {
            "date":      pd.Timestamp(row["date"]).strftime("%Y-%m-%d"),
            "portfolio": row["portfolio"],
        }
        if "benchmark" in row and row["benchmark"] is not None:
            entry["benchmark"] = row["benchmark"]
        else:
            entry["benchmark"] = row["portfolio"]   # fallback

        peak = row["portfolio"] if peak is None else max(peak, row["portfolio"])
        entry["drawdown"] = round((row["portfolio"] - peak) / peak * 100, 1) if peak else 0.0
        equity_curve.append(entry)

    # Positions summary
    fp      = results["final_positions"]
    n_long  = sum(1 for p in fp.values() if p["direction"] == "LONG")
    n_short = sum(1 for p in fp.values() if p["direction"] == "SHORT")

    alerts = ai_service.generate_alerts(metrics, fp, _window_trades(results),
                                        results["current_atr"])

    # Sharpe trend
    sharpe       = metrics.get("sharpe", 0)
    roll_sharpe  = metrics.get("rollingSharpe", 0)
    sharpe_trend = "up" if roll_sharpe >= sharpe * 0.95 else "down"

    return jsonify({
        "portfolioValue":  round(total, 0),
        "totalReturn":     metrics.get("totalReturn", 0),
        "dayPnL":          day_pnl,
        "dayPnLPercent":   day_pnl_pct,
        "mtdPercent":      metrics.get("mtdPct", 0),
        "sharpeRatio":     sharpe,
        "sharpeTrend":     sharpe_trend,
        "positions":       {"long": n_long, "short": n_short},
        "equityCurve":     equity_curve,
        "stocks":          stocks,
        "signals":         signals,
        "alerts":          alerts,
        "sparklines":      sparks,
    })


@app.route("/api/portfolio")
def portfolio():
    err = _require_ready()
    if err:
        return err

    results = _cache["results"]
    opt     = _cache["opt"]
    dv      = _window_daily_values(results)

    stocks         = _format_stocks(opt, results["current_prices"], results)
    sector_bd      = _sector_breakdown(stocks)
    risk_contrib   = opt.get("risk_contribution", [])
    frontier       = opt.get("frontier", [])
    port_metrics   = opt.get("portfolio_metrics", {})
    indiv          = opt.get("individual_metrics", {})
    corr_matrix    = opt.get("corr_matrix", [])

    individual_stocks = [
        {"ticker": t, "volatility": v["volatility"], "return": v["return"]}
        for t, v in indiv.items()
    ]
    current_portfolio = {
        "volatility": port_metrics.get("volatility", 0),
        "return":     port_metrics.get("return", 0),
    }

    total_val = dv[-1]["portfolio"] if dv else INITIAL_CAPITAL

    return jsonify({
        "portfolioValue":  round(total_val, 0),
        "stocks":          stocks,
        "sectorBreakdown": sector_bd,
        "riskContribution": risk_contrib,
        "efficientFrontier": frontier,
        "individualStocks": individual_stocks,
        "currentPortfolio": current_portfolio,
        "optimizationMetrics": port_metrics,
        "correlationMatrix": corr_matrix,
    })


@app.route("/api/monitoring")
def monitoring():
    err = _require_ready()
    if err:
        return err

    results = _cache["results"]
    metrics = _cache["metrics"]
    dv      = _window_daily_values(results)
    fp      = results["final_positions"]
    cp      = results["current_prices"]
    total   = dv[-1]["portfolio"] if dv else INITIAL_CAPITAL

    signals   = _format_signals(_window_signals(results), n=30)
    positions = _format_positions(fp, cp, results["current_atr"])

    # Monitoring equity history: app window from 2025-01-01 to today
    intraday = [
        {"time": pd.Timestamp(row["date"]).strftime("%b %d"),
         "value": row["portfolio"]}
        for row in dv
    ]

    # Unrealized P&L
    unrealised = sum(p["pnl"] for p in positions)
    realised   = metrics.get("realizedPnL", 0)
    win_rate   = metrics.get("winRate", 0)

    # Net exposure
    long_val  = sum(cp.get(t, {}).get("price", 0) * pos["shares"]
                    for t, pos in fp.items() if pos["direction"] == "LONG")
    short_val = sum(cp.get(t, {}).get("price", 0) * pos["shares"]
                    for t, pos in fp.items() if pos["direction"] == "SHORT")
    net_exp   = round((long_val - short_val) / total * 100, 1) if total > 0 else 0

    # Volatility metrics
    port_vol = metrics.get("volatility", 0)
    avg_atr  = round(sum(results["current_atr"].values()) / max(len(results["current_atr"]), 1), 4)

    # Drawdown
    dd_m = metrics.get("currentDrawdown", 0)
    dd_t = metrics.get("maxTodayDrawdown", 0)
    dd_e = metrics.get("maxDrawdown", 0)

    sector_exp = _sector_exposure(fp, cp, total)

    return jsonify({
        "intradayEquity":  intraday,
        "activePositions": positions,
        "signals":         signals,
        "monitoringKPIs": {
            "unrealizedPnL": round(unrealised, 2),
            "realizedPnL":   round(realised, 2),
            "winRate":       round(win_rate, 1),
            "netExposure":   net_exp,
        },
        "volatilityMetrics": {
            "atr":          avg_atr,
            "vix":          None,
            "portfolioVol": round(port_vol, 2),
        },
        "drawdownMetrics": {
            "current":  round(dd_m, 2),
            "maxToday": round(dd_t, 2),
            "maxEver":  round(dd_e, 2),
        },
        "sectorExposure": sector_exp,
    })


@app.route("/api/alerts")
def alerts():
    err = _require_ready()
    if err:
        return err

    results = _cache["results"]
    metrics = _cache["metrics"]
    a = ai_service.generate_alerts(
        metrics, results["final_positions"],
        _window_trades(results), results["current_atr"]
    )
    return jsonify({"alerts": a})


# ── AI routes ─────────────────────────────────────────────────────────────────

@app.route("/api/ai/explain", methods=["POST"])
def ai_explain():
    body   = request.get_json(force=True, silent=True) or {}
    signal = body.get("signal", {})
    result = ai_service.explain_trade(signal)
    return jsonify(result)


@app.route("/api/ai/summary", methods=["POST"])
def ai_summary():
    if _cache["state"] != "ready":
        return jsonify({
            "summary": "Data still loading, please try again shortly.",
            "provider": ai_service.provider_name(),
            "model": ai_service.current_model(),
        }), 200

    metrics  = _cache["metrics"]
    results  = _cache["results"]
    tickers  = results.get("tickers", TICKERS)
    positions = results.get("final_positions", {})
    context = _build_ai_context()
    summary  = ai_service.market_summary(metrics, positions, tickers, context)
    return jsonify({
        "summary": summary,
        "provider": ai_service.provider_name(),
        "model": ai_service.current_model(),
        "asOf": context.get("asOf"),
        "market": context.get("market", {}),
    })


@app.route("/api/ai/chat", methods=["POST"])
def ai_chat():
    body    = request.get_json(force=True, silent=True) or {}
    message = body.get("message", "")
    history = body.get("history", [])
    context = _build_ai_context() if _cache["state"] == "ready" else {}

    reply = ai_service.chat_response(message, history, context)
    return jsonify({
        "response": reply,
        "provider": ai_service.provider_name(),
        "model": ai_service.current_model(),
    })


@app.route("/api/refresh", methods=["POST"])
def refresh():
    if _cache["state"] == "loading":
        return jsonify({"status": "already loading"}), 200
    _cache["state"] = "loading"
    _cache["error"] = None
    threading.Thread(target=_load, daemon=True).start()
    return jsonify({"status": "loading"})


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5001))
    logger.info(f"Starting Flask API on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

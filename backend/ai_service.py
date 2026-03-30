"""
AI-Assisted Explanations using OpenAI GPT.
API key loaded from OPENAI_API in project .env file.
Falls back to template responses if the key is not available.
"""

import os
import json
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"

# ── Load .env ─────────────────────────────────────────────────────────────────

def _load_env():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    val = val.strip().strip("'\"")
                    os.environ.setdefault(key.strip(), val)

_load_env()


# ── Client ────────────────────────────────────────────────────────────────────

def current_model() -> str:
    for key in ("OPENAI_MODEL", "VITE_OPENAI_MODEL"):
        value = os.getenv(key, "").strip()
        if value:
            return value
    return DEFAULT_MODEL


def provider_name() -> str:
    return "OpenAI"


def _context_json(context: Optional[dict]) -> str:
    if not context:
        return "{}"
    try:
        return json.dumps(context, ensure_ascii=True, default=str, indent=2)
    except Exception:
        return str(context)

def _client():
    api_key = os.getenv("OPENAI_API", "")
    if not api_key:
        return None
    try:
        from openai import OpenAI
        return OpenAI(api_key=api_key, timeout=20.0, max_retries=1)
    except Exception as exc:
        logger.warning(f"Could not initialise OpenAI client: {exc}")
        return None


def _call(messages: list, max_tokens: int = 600) -> str | None:
    client = _client()
    if client is None:
        return None
    try:
        resp = client.chat.completions.create(
            model=current_model(),
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.4,
        )
        return resp.choices[0].message.content
    except Exception as exc:
        logger.warning(f"OpenAI API call failed: {exc}")
        return None


# ── Trade Explainer ───────────────────────────────────────────────────────────

def explain_trade(signal: dict) -> dict:
    action = signal.get("action", "")
    ticker = signal.get("ticker", "")
    leg    = signal.get("type", "")
    entry  = signal.get("entry_price") or signal.get("exit_price", 0)
    tp     = signal.get("tp")
    sl     = signal.get("sl")
    atr    = signal.get("atr", 0)
    detail = signal.get("detail", "")

    strategy_names = {
        "LM": "Long Momentum (LM)",
        "SM": "Short Momentum (SM)",
        "LR": "Long Reversion (LR)",
        "SR": "Short Reversion (SR)",
        "SL": "Stop-Loss (SL)",
        "TP": "Take-Profit (TP)",
        "TIME": "Time-Stop Exit",
        "REBALANCE": "Portfolio Rebalance",
    }
    strategy_name = strategy_names.get(leg, leg)

    system = (
        "You are an expert quantitative trading analyst for a MACD + Bollinger Bands + ATR "
        "strategy on large-cap US equities. Be concise, technical, and data-driven."
    )
    user = f"""Explain this trading signal in structured JSON.

Signal:
- Action: {action} {ticker}
- Strategy: {strategy_name}
- Entry/Exit Price: ${entry}
- Take Profit: ${tp}
- Stop Loss: ${sl}
- ATR: {atr}
- Technical detail: {detail}

Return ONLY valid JSON (no markdown) with these exact keys:
{{
  "why": ["reason 1", "reason 2", "reason 3"],
  "risk": "one paragraph about risk/reward",
  "confidence_note": "one sentence about signal confidence"
}}

Use the actual numbers. Be specific."""

    raw = _call([{"role": "system", "content": system},
                 {"role": "user",   "content": user}], max_tokens=500)

    if raw:
        import json, re
        try:
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            if m:
                parsed = json.loads(m.group())
                return {
                    "action":    action,
                    "ticker":    ticker,
                    "time":      signal.get("time", signal.get("date", "")),
                    "strategy":  strategy_name,
                    "why":       parsed.get("why", [detail]),
                    "risk":      parsed.get("risk", ""),
                    "confidence": signal.get("strength"),
                }
        except Exception:
            pass

    # Fallback templates
    if action == "LONG":
        why = [
            "MACD histogram entered the momentum zone (0 to mid threshold), confirming bullish impulse.",
            f"Price (${entry}) is above the Bollinger mid-band, supporting the upward trend.",
            f"ATR ({atr}) is within normal range – breakout occurring in stable volatility.",
        ]
        rr = round(abs((tp - entry) / (entry - sl)), 1) if tp and sl and entry != sl else "N/A"
        risk = f"Stop-loss at ${sl}, take-profit at ${tp}. Risk-reward ratio 1:{rr}."
    elif action == "SHORT":
        why = [
            f"MACD histogram in extreme zone beyond the reversion threshold.",
            f"Price (${entry}) is {'above upper' if leg == 'SR' else 'below lower'} Bollinger Band.",
            f"Mean-reversion conditions detected. ATR ({atr}) confirms the setup.",
        ]
        risk = f"Stop-loss at ${sl}, take-profit at ${tp}. Short position with bounded downside."
    else:
        why = [
            f"{'Stop-loss' if leg == 'SL' else 'Take-profit' if leg == 'TP' else 'Time-stop'} triggered.",
            f"Exit at ${entry}.",
            "Position closed to protect capital / lock in gains.",
        ]
        risk = "Position fully closed. No remaining exposure."

    return {
        "action":     action,
        "ticker":     ticker,
        "time":       signal.get("time", signal.get("date", "")),
        "strategy":   strategy_name,
        "why":        why,
        "risk":       risk,
        "confidence": signal.get("strength"),
    }


# ── Market Summary ────────────────────────────────────────────────────────────

def market_summary(metrics: dict, positions: dict, tickers: list,
                   context: Optional[dict] = None) -> str:
    n_long  = sum(1 for p in positions.values() if p.get("direction") == "LONG")
    n_short = sum(1 for p in positions.values() if p.get("direction") == "SHORT")
    context_json = _context_json(context)

    system = (
        "You are an OpenAI market assistant for a live quantitative trading dashboard. "
        "Use only the supplied live context. Do not invent dates, macro events, or catalysts "
        "that are not explicitly present in the context. If a detail is unavailable, say so. "
        "When naming active positions, only use tickers present in the live context."
    )
    user = f"""Write a current market and portfolio update in 3 short paragraphs.

Use these rules:
- Anchor the update to the live dashboard snapshot only.
- Mention the as-of date from context if it exists.
- Cover SPY/benchmark tone, portfolio positioning, and current risk.
- Quote concrete numbers from the context.
- Keep it concise and data-driven.

Fallback portfolio statistics:
- Total Return: {metrics.get('totalReturn', 0):.1f}%
- CAGR: {metrics.get('cagr', 0):.1f}%
- Sharpe Ratio: {metrics.get('sharpe', 0):.2f}
- Max Drawdown: {metrics.get('maxDrawdown', 0):.1f}%
- Current Drawdown: {metrics.get('currentDrawdown', 0):.1f}%
- Annualised Volatility: {metrics.get('volatility', 0):.1f}%
- Win Rate: {metrics.get('winRate', 0):.1f}%
- Active Positions: {n_long} long, {n_short} short
- Universe: {', '.join(tickers)}

Live context JSON:
{context_json}"""

    result = _call([{"role": "system", "content": system},
                    {"role": "user",   "content": user}], max_tokens=400)
    if result:
        return result

    market = (context or {}).get("market", {})
    portfolio = market.get("portfolio", {})
    benchmark = market.get("benchmark", {})
    as_of = (context or {}).get("asOf", "the latest snapshot")
    regime = "trending bullish" if metrics.get("rollingSharpe", 0) > 1.0 else "mixed"
    return (
        f"As of {as_of}, the dashboard snapshot points to a {regime} regime. "
        f"SPY is {benchmark.get('dayChangePct', 0):+.2f}% on the day and "
        f"{benchmark.get('totalReturnPct', 0):+.1f}% since the backtest start, while the "
        f"portfolio is {portfolio.get('dayChangePct', 0):+.2f}% on the day with "
        f"{portfolio.get('totalReturnPct', 0):+.1f}% total return.\n\n"
        f"The portfolio currently holds {n_long} long and {n_short} short positions across "
        f"{len(tickers)} large-cap US equities. Sharpe is {metrics.get('sharpe', 0):.2f}, "
        f"annualised volatility is {metrics.get('volatility', 0):.1f}%, and current drawdown "
        f"is {metrics.get('currentDrawdown', 0):.1f}%.\n\n"
        f"Key risks to monitor are drawdown control, any deterioration in the recent signal mix, "
        f"and whether benchmark momentum remains supportive of the current long-biased book."
    )


# ── Risk Alerts ───────────────────────────────────────────────────────────────

def generate_alerts(metrics: dict, positions: dict, trades: list,
                    current_atr: dict) -> list[dict]:
    from datetime import datetime
    now    = datetime.now().strftime("%I:%M %p")
    alerts = []

    cur_dd = abs(metrics.get("currentDrawdown", 0))
    if cur_dd > 3.0:
        sev = "critical" if cur_dd > 5 else "warning"
        alerts.append({
            "severity": sev, "time": now, "title": "DRAWDOWN WARNING",
            "message":  (f"Portfolio drawdown reached -{cur_dd:.1f}% from peak. "
                         f"Max historical: {abs(metrics.get('maxDrawdown', 0)):.1f}%."),
            "recommendation": "Consider reducing position sizes if drawdown exceeds 7%." if sev == "critical" else None,
        })

    win_rate = metrics.get("winRate", 0)
    if win_rate > 60:
        alerts.append({
            "severity": "info", "time": now, "title": "STRONG WIN RATE",
            "message":  f"Strategy win rate at {win_rate:.1f}% – above the 60% threshold. Both momentum and reversion legs performing within expected parameters.",
            "recommendation": None,
        })

    if not positions:
        alerts.append({
            "severity": "info", "time": now, "title": "NO ACTIVE POSITIONS",
            "message":  "No open positions. Strategy is in cash, awaiting entry signals.",
            "recommendation": None,
        })

    alerts.append({
        "severity": "info", "time": now, "title": "STRATEGY STATUS",
        "message":  (f"MACD-BB-ATR regime-adaptive strategy active. "
                     f"Total Return: {metrics.get('totalReturn', 0):.1f}% | "
                     f"Sharpe: {metrics.get('sharpe', 0):.2f} | "
                     f"Drawdown: {metrics.get('currentDrawdown', 0):.1f}%."),
        "recommendation": None,
    })

    return alerts[:4]


# ── Chat ──────────────────────────────────────────────────────────────────────

def chat_response(message: str, history: list,
                  context: Optional[dict] = None) -> str:
    system = (
        "You are an OpenAI AI Assistant for a live quantitative trading dashboard using a "
        "MACD + Bollinger Bands + ATR strategy on a large-cap US equity universe. "
        "Four strategy legs: Long Momentum (LM), Short Momentum (SM), "
        "Long Reversion (LR), Short Reversion (SR). "
        "Portfolio optimised via Modern Portfolio Theory (Ledoit-Wolf + tangent portfolio). "
        "Be concise, data-driven, and helpful. Never mention Claude. "
        "Never invent dates, market catalysts, or macro events that are not explicitly present in the live context. "
        "When naming current holdings or active positions, only use tickers present in the live context."
    )
    if context:
        system += f"\n\nLive dashboard context JSON:\n{_context_json(context)}"

    messages = [{"role": "system", "content": system}]
    for h in history[-8:]:
        messages.append({"role": h.get("role", "user"), "content": h.get("content", "")})
    messages.append({"role": "user", "content": message})

    result = _call(messages, max_tokens=600)
    if result:
        return result

    # Fallback
    msg_lower = message.lower()
    market = (context or {}).get("market", {})
    portfolio = market.get("portfolio", {})
    benchmark = market.get("benchmark", {})
    positions = market.get("positions", {})
    as_of = (context or {}).get("asOf", "the latest dashboard snapshot")
    if any(w in msg_lower for w in ["market", "overview", "summary", "spy", "benchmark"]):
        return (
            f"As of {as_of}, SPY is {benchmark.get('dayChangePct', 0):+.2f}% on the day and "
            f"{benchmark.get('totalReturnPct', 0):+.1f}% since the backtest start. "
            f"The portfolio is {portfolio.get('dayChangePct', 0):+.2f}% on the day, "
            f"{portfolio.get('totalReturnPct', 0):+.1f}% since start, with "
            f"{portfolio.get('currentDrawdownPct', 0):.1f}% current drawdown and "
            f"{positions.get('long', 0)} long / {positions.get('short', 0)} short positions."
        )
    if any(w in msg_lower for w in ["macd", "indicator", "signal"]):
        return ("The strategy uses MACD histogram thresholds scaled by robust MAD. "
                "Moderate zones trigger momentum trades (LM/SM); extreme zones trigger reversion (LR/SR). "
                "Bollinger Bands on log-price confirm signal direction.")
    if any(w in msg_lower for w in ["portfolio", "allocation", "weight"]):
        return ("Allocation uses Modern Portfolio Theory: Ledoit-Wolf shrinkage covariance "
                "+ max-Sharpe tangent portfolio (long-only). Rebalances every 120 trading days.")
    if any(w in msg_lower for w in ["risk", "drawdown", "stop"]):
        return ("Risk is managed with ATR-scaled stop-losses and take-profits plus a 26-bar time stop. "
                "The current notebook-aligned setup does not use trailing stops by default, "
                "and portfolio drawdown is monitored against the live dashboard snapshot.")
    return ("I can help with trading signals, portfolio allocation, risk management, "
            "or performance metrics. What would you like to know?")

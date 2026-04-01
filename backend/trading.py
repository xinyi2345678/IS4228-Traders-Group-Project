"""
Notebook-faithful trading pipeline for the dashboard backend.

The dashboard uses a live-ish test window (2025-01-01 -> today), and the
strategy logic, optimizer inputs, and tuned parameters are aligned to the
project notebook.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf
from ta.trend import MACD
from ta.volatility import AverageTrueRange

logger = logging.getLogger(__name__)


TICKERS = ["AAPL", "AMZN", "META", "GOOG", "GOOGL", "NVDA", "MSFT", "AVGO", "TSLA", "BRK-B"]

COMPANY_NAMES = {
    "AAPL": "Apple Inc.",
    "AMZN": "Amazon.com Inc.",
    "META": "Meta Platforms",
    "GOOG": "Alphabet Inc. (C)",
    "GOOGL": "Alphabet Inc. (A)",
    "NVDA": "NVIDIA Corp.",
    "MSFT": "Microsoft Corp.",
    "AVGO": "Broadcom Inc.",
    "TSLA": "Tesla Inc.",
    "BRK-B": "Berkshire Hathaway",
}

SECTOR_MAP = {
    "AAPL": "Technology",
    "AVGO": "Technology",
    "NVDA": "Technology",
    "MSFT": "Technology",
    "META": "Communication",
    "GOOG": "Communication",
    "GOOGL": "Communication",
    "AMZN": "Consumer",
    "TSLA": "Consumer",
    "BRK-B": "Financial",
}

SECTOR_COLORS = {
    "Technology": "#58A6FF",
    "Communication": "#A371F7",
    "Consumer": "#3FB950",
    "Financial": "#D29922",
    "Healthcare": "#F85149",
}

# Tuned params from the notebook's best_params cells.
DEFAULT_PARAMS = {
    "macd_fast": 20,
    "macd_slow": 35,
    "macd_signal": 6,
    "macd_std_window": 73,
    "macd_k": 2.0,
    "macd_k_mid": 0.8,
    "bb_window": 24,
    "bb_std_dev": 1.75,
    "atr_window": 19,
    "tp_mult_lm": 4.6,
    "sl_mult_lm": 1.7000000000000002,
    "tp_mult_sm": 4.3,
    "sl_mult_sm": 1.9500000000000002,
    "tp_mult_lr": 12.600000000000001,
    "sl_mult_lr": 2.2,
    "tp_mult_sr": 4.3,
    "sl_mult_sr": 3.1,
    "use_trailing": True,
    "trail_mult": 3.4000000000000004,
    "trail_tp": True,
    "time_stop": 29,
    "cooldown": 1,
    "rebounce_block": 4,
    "rebalance_freq": 90,
}

INITIAL_CAPITAL = 1_000_000
SIM_START = "2025-01-01"
WARMUP_DAYS = 150
BENCHMARK = "SPY"


def _detail_for_signal(leg: str, close: float, hist: float, z_mid: float, z_pos: float,
                       upper: float, mid: float, lower: float, atr: float) -> str:
    bb_range = max(upper - lower, 1e-9)
    bb_pct = (close - lower) / bb_range * 100

    if leg == "LM":
        return (
            f"Long Momentum - MACD histogram {hist:.4f} within 0 to {z_mid:.4f}. "
            f"Price above mid-band at {bb_pct:.0f}% BB position. ATR {atr:.2f}."
        )
    if leg == "SM":
        return (
            f"Short Momentum - MACD histogram {hist:.4f} within -{z_mid:.4f} to 0. "
            f"Price below mid-band at {bb_pct:.0f}% BB position. ATR {atr:.2f}."
        )
    if leg == "LR":
        return (
            f"Long Reversion - MACD histogram {hist:.4f} below -{z_pos:.4f}. "
            f"Price below lower Bollinger Band. ATR {atr:.2f}."
        )
    if leg == "SR":
        return (
            f"Short Reversion - MACD histogram {hist:.4f} above {z_pos:.4f}. "
            f"Price above upper Bollinger Band. ATR {atr:.2f}."
        )
    if leg == "SL":
        return "Stop-loss threshold breached on the prior bar; exited on next open."
    if leg == "TP":
        return "Take-profit threshold reached on the prior bar; exited on next open."
    if leg == "TIME":
        return "Time-based exit triggered; position closed on next open."
    if leg == "REBALANCE":
        return "Position closed for scheduled portfolio rebalance."
    return ""


class CommonClass:
    def __init__(
        self,
        symbols,
        start,
        end,
        interval,
        capital,
        transaction_cost,
        allocations=None,
        verbose=False,
        rebalance_freq=None,
        warmup_days=WARMUP_DAYS,
        leverage: float = 0.0,
        params=None,
    ):
        self.symbols = list(symbols)
        self.start = start
        self.end = end
        self.interval = interval
        self.initial_capital = float(capital)
        self.warmup_days = warmup_days
        self.rebalance_freq = rebalance_freq
        self.leverage = float(leverage)
        self.params = dict(params or {})

        start_ts = pd.to_datetime(start)
        self.data_start = (start_ts - timedelta(days=warmup_days)).strftime("%Y-%m-%d")
        self.trading_start = pd.to_datetime(start)

        if allocations is None:
            self.allocations = {s: 1.0 / len(self.symbols) for s in self.symbols}
        else:
            total = sum(allocations.values())
            self.allocations = {s: float(v) / total for s, v in allocations.items()}

        self.capital = {s: self.initial_capital * self.allocations[s] for s in self.symbols}
        self.transaction_cost = float(transaction_cost)
        self.verbose = verbose

        self.all_data: dict[str, pd.DataFrame] = {}
        self.position = {s: 0 for s in self.symbols}
        self.quantity = {s: 0 for s in self.symbols}
        self.trades = {s: 0 for s in self.symbols}

        self.stored_data = pd.DataFrame(
            columns=["trade", "date", "position", "price", "symbol", "quantity", "capital", "portfolio_value"]
        )
        self.portfolio_history: list[tuple] = []
        self.portfolio_df: pd.DataFrame | None = None
        self.stock_equity_history = {s: [] for s in self.symbols}
        self.signals: list[dict] = []
        self.closed_trades: list[dict] = []
        self.final_positions: dict[str, dict] = {}

        self.prepare_data()

    def prepare_data(self):
        for symbol in self.symbols:
            try:
                hist = yf.Ticker(symbol).history(
                    start=self.data_start,
                    end=self.end,
                    interval=self.interval,
                    auto_adjust=False,
                )
                if hist.empty:
                    logger.warning(f"No data for {symbol}")
                    self.all_data[symbol] = pd.DataFrame()
                    continue

                df = pd.DataFrame(index=hist.index)
                df["Open"] = hist["Open"]
                df["High"] = hist["High"]
                df["Low"] = hist["Low"]
                df["Close"] = hist["Close"]
                df["Close_Price"] = hist["Close"]
                df["Volume"] = hist["Volume"]
                df["Return"] = np.log(df["Close"] / df["Close"].shift(1))
                df = df.dropna()

                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)

                self.all_data[symbol] = df
            except Exception as exc:
                logger.warning(f"Error loading {symbol}: {exc}")
                self.all_data[symbol] = pd.DataFrame()

    def _get_date_price(self, bar, price_type="Open", symbol=None):
        df = self.all_data[symbol]
        if df.empty or bar >= len(df):
            raise IndexError(f"Bar {bar} out of range for {symbol}")
        date = df.index[bar]
        return date, float(df[price_type].iloc[bar])

    def _record_stock_equity(self, bar_dict):
        for symbol in self.symbols:
            df = self.all_data[symbol]
            bar = bar_dict.get(symbol, 0)
            if df.empty or bar >= len(df):
                continue

            date = df.index[bar]
            price = float(df["Close"].iloc[bar])
            cash = float(self.capital[symbol])
            position_value = float(self.quantity[symbol] * price)
            equity = cash + position_value

            history = self.stock_equity_history[symbol]
            if not history:
                strategy_logreturn = 0.0
                stock_logreturn = 0.0
            else:
                _, prev_price, prev_equity, _, _ = history[-1]
                strategy_logreturn = np.log(equity / prev_equity) if prev_equity > 0 and equity > 0 else 0.0
                stock_logreturn = np.log(price / prev_price) if prev_price > 0 and price > 0 else 0.0

            self.stock_equity_history[symbol].append(
                (date, price, equity, strategy_logreturn, stock_logreturn)
            )

    def get_portfolio_value(self, bar):
        total_value = 0.0
        if isinstance(bar, dict):
            bar_dict = bar
        else:
            bar_dict = {s: bar for s in self.symbols}

        for symbol in self.symbols:
            total_value += float(self.capital[symbol])
            df = self.all_data[symbol]
            if df.empty:
                continue
            b = bar_dict.get(symbol, 0)
            if b < 0 or b >= len(df):
                continue
            total_value += self.quantity[symbol] * float(df["Close_Price"].iloc[b])

        return float(total_value)

    def _store_trade(self, trade, date, position, price, symbol, quantity, capital, portfolio_value):
        row = pd.DataFrame(
            {
                "trade": [trade],
                "date": [pd.to_datetime(date)],
                "position": [position],
                "price": [float(price)],
                "symbol": [symbol],
                "quantity": [int(quantity)],
                "capital": [float(capital)],
                "portfolio_value": [float(portfolio_value)],
            }
        )
        self.stored_data = pd.concat([self.stored_data, row], ignore_index=True)

    def buy_order(self, bar, symbol, quantity=None, dollar=None):
        date, price = self._get_date_price(bar + 1, "Open", symbol)
        if quantity is None:
            dollar = self.capital[symbol] if dollar is None else dollar
            cost_per_share = price * (1.0 + self.transaction_cost)
            base_qty = int(dollar / cost_per_share) if cost_per_share > 0 else 0
        else:
            base_qty = int(quantity)

        qty = int(base_qty * (1.0 + max(self.leverage, 0.0)))
        cost = qty * price * (1.0 + self.transaction_cost)

        if qty <= 0:
            return
        if self.leverage <= 0.0 and cost > self.capital[symbol]:
            return

        self.capital[symbol] -= cost
        self.quantity[symbol] += qty
        self.trades[symbol] += 1
        self.position[symbol] = 1 if self.quantity[symbol] > 0 else 0

        portfolio_value = self.get_portfolio_value(bar + 1)
        self._store_trade(
            trade=sum(self.trades.values()),
            date=date,
            position=1,
            price=price,
            symbol=symbol,
            quantity=qty,
            capital=self.capital[symbol],
            portfolio_value=portfolio_value,
        )

    def sell_order(self, bar, symbol, last=False, quantity=None, dollar=None):
        if not last:
            date, price = self._get_date_price(bar + 1, "Open", symbol)
            held = self.quantity[symbol]
            if held <= 0:
                return

            if quantity is None:
                qty = held if dollar is None else min(int(dollar / price) if price > 0 else 0, held)
            else:
                qty = min(int(quantity), held)

            if qty <= 0:
                return

            proceeds = qty * price * (1.0 - self.transaction_cost)
            self.capital[symbol] += proceeds
            self.quantity[symbol] -= qty
            self.trades[symbol] += 1
            self.position[symbol] = 1 if self.quantity[symbol] > 0 else 0
            portfolio_value = self.get_portfolio_value(bar + 1)
        else:
            date, price = self._get_date_price(bar, "Close", symbol)
            held = self.quantity[symbol]
            if held <= 0:
                return
            qty = held
            proceeds = qty * price * (1.0 - self.transaction_cost)
            self.capital[symbol] += proceeds
            self.quantity[symbol] -= qty
            self.trades[symbol] += 1
            self.position[symbol] = 0
            portfolio_value = self.get_portfolio_value(bar)

        self._store_trade(
            trade=sum(self.trades.values()),
            date=date,
            position=-1,
            price=price,
            symbol=symbol,
            quantity=qty,
            capital=self.capital[symbol],
            portfolio_value=portfolio_value,
        )

    def short_order(self, bar, symbol, quantity=None, dollar=None):
        date, price = self._get_date_price(bar + 1, "Open", symbol)
        if quantity is None:
            dollar = self.capital[symbol] if dollar is None else dollar
            proceeds_per_share = price * (1.0 - self.transaction_cost)
            base_qty = int(dollar / proceeds_per_share) if proceeds_per_share > 0 else 0
        else:
            base_qty = int(quantity)

        qty = int(base_qty * (1.0 + max(self.leverage, 0.0)))
        if qty <= 0:
            return

        proceeds = qty * price * (1.0 - self.transaction_cost)
        self.capital[symbol] += proceeds
        self.quantity[symbol] -= qty
        self.trades[symbol] += 1
        self.position[symbol] = -1

        portfolio_value = self.get_portfolio_value(bar + 1)
        self._store_trade(
            trade=sum(self.trades.values()),
            date=date,
            position=-1,
            price=price,
            symbol=symbol,
            quantity=-qty,
            capital=self.capital[symbol],
            portfolio_value=portfolio_value,
        )

    def cover_order(self, bar, symbol, last=False, quantity=None, dollar=None):
        if not last:
            date, price = self._get_date_price(bar + 1, "Open", symbol)
            held = self.quantity[symbol]
            if held >= 0:
                return
            shorted_qty = abs(held)

            if quantity is None:
                qty = (
                    shorted_qty
                    if dollar is None
                    else min(int(dollar / (price * (1.0 + self.transaction_cost))) if price > 0 else 0, shorted_qty)
                )
            else:
                qty = min(int(quantity), shorted_qty)

            if qty <= 0:
                return

            cost = qty * price * (1.0 + self.transaction_cost)
            if self.leverage <= 0.0 and cost > self.capital[symbol]:
                return

            self.capital[symbol] -= cost
            self.quantity[symbol] += qty
            self.trades[symbol] += 1
            self.position[symbol] = -1 if self.quantity[symbol] < 0 else 0
            portfolio_value = self.get_portfolio_value(bar + 1)
        else:
            date, price = self._get_date_price(bar, "Close", symbol)
            held = self.quantity[symbol]
            if held >= 0:
                return
            qty = abs(held)
            cost = qty * price * (1.0 + self.transaction_cost)
            if self.leverage <= 0.0 and cost > self.capital[symbol]:
                return

            self.capital[symbol] -= cost
            self.quantity[symbol] += qty
            self.trades[symbol] += 1
            self.position[symbol] = 0
            portfolio_value = self.get_portfolio_value(bar)

        self._store_trade(
            trade=sum(self.trades.values()),
            date=date,
            position=1,
            price=price,
            symbol=symbol,
            quantity=qty,
            capital=self.capital[symbol],
            portfolio_value=portfolio_value,
        )

    def rebalance(self, total_cash, new_allocations=None):
        if new_allocations is not None:
            total = sum(new_allocations.values())
            self.allocations = {s: float(v) / total for s, v in new_allocations.items()}

        for symbol in self.symbols:
            self.capital[symbol] = total_cash * self.allocations[symbol]
            self.quantity[symbol] = 0
            self.position[symbol] = 0


class MACDBBATRStrategy(CommonClass):
    def __init__(self, symbols, start, end, params=None, rebalance_freq=90, warmup_days=WARMUP_DAYS, **kwargs):
        strategy_params = dict(params or {})
        if "rebalance_freq" in strategy_params:
            rebalance_freq = strategy_params.pop("rebalance_freq")

        merged_params = DEFAULT_PARAMS.copy()
        merged_params.update(strategy_params)

        super().__init__(
            symbols,
            start,
            end,
            interval=kwargs.pop("interval", "1d"),
            capital=kwargs.pop("capital", INITIAL_CAPITAL),
            transaction_cost=kwargs.pop("transaction_cost", 0.0),
            allocations=kwargs.pop("allocations", None),
            verbose=kwargs.pop("verbose", False),
            rebalance_freq=rebalance_freq,
            warmup_days=warmup_days,
            leverage=kwargs.pop("leverage", 0.0),
            params=merged_params,
        )
        self.rebalance_freq = int(rebalance_freq)

        for symbol in self.symbols:
            df = self.all_data[symbol].copy()
            self.all_data[symbol] = self._compute_indicators(df)

    def _compute_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df

        close = df["Close"]
        high = df["High"]
        low = df["Low"]

        macd = MACD(
            close=close,
            window_slow=int(self.params["macd_slow"]),
            window_fast=int(self.params["macd_fast"]),
            window_sign=int(self.params["macd_signal"]),
            fillna=False,
        )
        df["MACD_Hist"] = macd.macd_diff()

        def calc_mad(arr):
            if len(arr) == 0:
                return np.nan
            median_val = np.median(arr)
            return np.median(np.abs(arr - median_val))

        rolling_mad = df["MACD_Hist"].rolling(
            int(self.params["macd_std_window"]),
            min_periods=int(self.params["macd_std_window"]),
        ).apply(calc_mad, raw=False)

        robust_scale = 1.4826 * rolling_mad
        df["MACD_Z_Pos"] = float(self.params["macd_k"]) * robust_scale
        df["MACD_Z_Mid"] = float(self.params["macd_k_mid"]) * robust_scale
        df["MACD_Z_Neg"] = -float(self.params["macd_k"]) * robust_scale

        atr = AverageTrueRange(
            high=high,
            low=low,
            close=close,
            window=int(self.params["atr_window"]),
            fillna=False,
        )
        df["ATR"] = atr.average_true_range()

        log_price = np.log(df["Close"].where(df["Close"] > 0.0, np.nan)).astype(float)
        mean_log = log_price.rolling(
            int(self.params["bb_window"]),
            min_periods=int(self.params["bb_window"]),
        ).mean()
        std_log = log_price.rolling(
            int(self.params["bb_window"]),
            min_periods=int(self.params["bb_window"]),
        ).std(ddof=0)

        df["BB_Upper"] = np.exp(mean_log + float(self.params["bb_std_dev"]) * std_log)
        df["BB_Mid"] = np.exp(mean_log)
        df["BB_Lower"] = np.exp(mean_log - float(self.params["bb_std_dev"]) * std_log)
        return df

    def _record_entry_signal(self, symbol, direction, leg, trade_date, entry_price, atr_value,
                             close_price, macd_hist, z_mid, z_pos, upper_band, mid_band, lower_band,
                             tp_price, sl_price):
        strength = min(0.99, abs(close_price - mid_band) / (atr_value * 2 + 1e-9)) if np.isfinite(atr_value) else None
        self.signals.append(
            {
                "date": trade_date.strftime("%Y-%m-%d"),
                "time": trade_date.strftime("%b %d"),
                "ticker": symbol,
                "action": direction,
                "type": leg,
                "strength": round(float(strength), 2) if strength is not None else None,
                "entry_price": round(float(entry_price), 2),
                "tp": round(float(tp_price), 2),
                "sl": round(float(sl_price), 2),
                "atr": round(float(atr_value), 4),
                "detail": _detail_for_signal(
                    leg, close_price, macd_hist, z_mid, z_pos, upper_band, mid_band, lower_band, atr_value
                ),
            }
        )

    def _record_exit_event(self, symbol, state_row, exit_type, exit_date, exit_price):
        qty = int(abs(state_row["entry_qty"]))
        if qty <= 0:
            return

        direction = "LONG" if state_row["position"] == 1 else "SHORT"
        entry_price = float(state_row["entry_price"])
        pnl = (
            (exit_price - entry_price) * qty
            if direction == "LONG"
            else (entry_price - exit_price) * qty
        )
        denom = entry_price * qty if entry_price > 0 else 1.0

        self.closed_trades.append(
            {
                "ticker": symbol,
                "direction": direction,
                "leg": state_row["entry_leg"],
                "entry_price": round(entry_price, 2),
                "entry_date": pd.Timestamp(state_row["entry_date"]).strftime("%Y-%m-%d"),
                "exit_price": round(float(exit_price), 2),
                "exit_date": pd.Timestamp(exit_date).strftime("%Y-%m-%d"),
                "exit_type": exit_type,
                "pnl": round(float(pnl), 2),
                "pnl_pct": round(float(pnl / denom * 100), 2),
                "shares": qty,
            }
        )

        self.signals.append(
            {
                "date": pd.Timestamp(exit_date).strftime("%Y-%m-%d"),
                "time": pd.Timestamp(exit_date).strftime("%b %d"),
                "ticker": symbol,
                "action": "EXIT",
                "type": exit_type,
                "strength": None,
                "entry_price": round(entry_price, 2),
                "exit_price": round(float(exit_price), 2),
                "pnl": round(float(pnl), 2),
                "detail": _detail_for_signal(exit_type, exit_price, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
            }
        )

    def _snapshot_open_positions(self, state):
        snapshot = {}
        for symbol in self.symbols:
            qty = int(abs(self.quantity[symbol]))
            if qty <= 0:
                continue
            st = state[symbol]
            snapshot[symbol] = {
                "direction": "LONG" if st["position"] == 1 else "SHORT",
                "leg": st["entry_leg"],
                "entry_price": float(st["entry_price"]),
                "shares": qty,
                "tp": float(st["tp_price"]) if np.isfinite(st["tp_price"]) else np.nan,
                "sl": float(st["sl_price"]) if np.isfinite(st["sl_price"]) else np.nan,
                "entry_bar": int(st["entry_bar"]),
                "entry_date": pd.Timestamp(st["entry_date"]).strftime("%Y-%m-%d") if st["entry_date"] is not None else None,
            }
        self.final_positions = snapshot

    def run_strategy(self):
        all_dates = sorted(set().union(*[df.index for df in self.all_data.values() if not df.empty]))
        trading_dates = [d for d in all_dates if d >= self.trading_start]

        state = {}
        for symbol in self.symbols:
            state[symbol] = {
                "position": 0,
                "tp_price": np.nan,
                "sl_price": np.nan,
                "entry_price": np.nan,
                "run_max": np.nan,
                "run_min": np.nan,
                "buy_trend_counter": 0,
                "sell_trend_counter": 0,
                "bars_in_trade": 0,
                "bars_since_close": 10**9,
                "bars_since_long": 10**9,
                "bars_since_short": 10**9,
                "entry_leg": None,
                "entry_date": None,
                "entry_qty": 0,
                "entry_bar": -1,
            }

        days_since_rebalance = 0
        for cur_date in trading_dates:
            days_since_rebalance += 1
            if days_since_rebalance >= self.rebalance_freq:
                bar_dict = {
                    symbol: df.index.get_loc(cur_date) if cur_date in df.index else 0
                    for symbol, df in self.all_data.items()
                }

                for symbol in self.symbols:
                    df = self.all_data[symbol]
                    bar = bar_dict.get(symbol, 0)
                    if df.empty or bar <= 0:
                        continue
                    st = state[symbol]
                    if st["position"] == 0 or self.quantity[symbol] == 0:
                        continue

                    exit_price = float(df["Open"].iloc[bar])
                    self._record_exit_event(symbol, st, "REBALANCE", cur_date, exit_price)
                    if self.quantity[symbol] > 0:
                        self.sell_order(bar - 1, symbol, quantity=self.quantity[symbol])
                    else:
                        self.cover_order(bar - 1, symbol, quantity=abs(self.quantity[symbol]))

                total_cash = sum(self.capital.values())
                self.rebalance(total_cash)

                for symbol in self.symbols:
                    state[symbol].update(
                        {
                            "position": 0,
                            "tp_price": np.nan,
                            "sl_price": np.nan,
                            "entry_price": np.nan,
                            "run_max": np.nan,
                            "run_min": np.nan,
                            "bars_in_trade": 0,
                            "bars_since_close": int(self.params["cooldown"]),
                            "bars_since_long": int(self.params["rebounce_block"]),
                            "bars_since_short": int(self.params["rebounce_block"]),
                            "entry_leg": None,
                            "entry_date": None,
                            "entry_qty": 0,
                            "entry_bar": -1,
                        }
                    )
                days_since_rebalance = 0

            for symbol in self.symbols:
                df = self.all_data[symbol]
                if df.empty or cur_date not in df.index:
                    continue

                bar = df.index.get_loc(cur_date)
                has_next = (bar + 1) < len(df)
                if bar < 1:
                    continue

                close_price = float(df["Close"].iloc[bar])
                upper_band = float(df["BB_Upper"].iloc[bar]) if pd.notna(df["BB_Upper"].iloc[bar]) else np.nan
                mid_band = float(df["BB_Mid"].iloc[bar]) if pd.notna(df["BB_Mid"].iloc[bar]) else np.nan
                lower_band = float(df["BB_Lower"].iloc[bar]) if pd.notna(df["BB_Lower"].iloc[bar]) else np.nan
                macd_hist = float(df["MACD_Hist"].iloc[bar]) if pd.notna(df["MACD_Hist"].iloc[bar]) else np.nan
                macd_zpos = float(df["MACD_Z_Pos"].iloc[bar]) if pd.notna(df["MACD_Z_Pos"].iloc[bar]) else np.nan
                macd_zmid = float(df["MACD_Z_Mid"].iloc[bar]) if pd.notna(df["MACD_Z_Mid"].iloc[bar]) else np.nan
                macd_zneg = float(df["MACD_Z_Neg"].iloc[bar]) if pd.notna(df["MACD_Z_Neg"].iloc[bar]) else np.nan
                atr_value = float(df["ATR"].iloc[bar]) if pd.notna(df["ATR"].iloc[bar]) else np.nan

                st = state[symbol]
                prev_pos = st["position"]

                st["bars_since_close"] += 1
                st["bars_since_long"] += 1
                st["bars_since_short"] += 1
                st["bars_in_trade"] = (st["bars_in_trade"] + 1) if prev_pos != 0 else 0

                short_reversion = (
                    np.isfinite([macd_hist, macd_zpos, upper_band]).all()
                    and macd_hist > macd_zpos
                    and close_price > upper_band
                )
                long_reversion = (
                    np.isfinite([macd_hist, macd_zneg, lower_band]).all()
                    and macd_hist < macd_zneg
                    and close_price < lower_band
                )
                long_momentum = (
                    np.isfinite([macd_hist, macd_zmid, mid_band]).all()
                    and 0 <= macd_hist <= macd_zmid
                    and close_price > mid_band
                )
                short_momentum = (
                    np.isfinite([macd_hist, macd_zmid, mid_band]).all()
                    and -macd_zmid <= macd_hist <= 0
                    and close_price < mid_band
                )

                if prev_pos != 0 and self.params["use_trailing"] and np.isfinite(atr_value):
                    if prev_pos == 1:
                        st["run_max"] = close_price if not np.isfinite(st["run_max"]) else max(st["run_max"], close_price)
                        new_sl = st["run_max"] - float(self.params["trail_mult"]) * atr_value
                        st["sl_price"] = max(st["sl_price"], new_sl) if np.isfinite(st["sl_price"]) else new_sl
                        if self.params["trail_tp"]:
                            new_tp = st["run_max"] - (float(self.params["trail_mult"]) / 2.0) * atr_value
                            st["tp_price"] = max(st["tp_price"], new_tp) if np.isfinite(st["tp_price"]) else new_tp
                    else:
                        st["run_min"] = close_price if not np.isfinite(st["run_min"]) else min(st["run_min"], close_price)
                        new_sl = st["run_min"] + float(self.params["trail_mult"]) * atr_value
                        st["sl_price"] = min(st["sl_price"], new_sl) if np.isfinite(st["sl_price"]) else new_sl
                        if self.params["trail_tp"]:
                            new_tp = st["run_min"] + (float(self.params["trail_mult"]) / 2.0) * atr_value
                            st["tp_price"] = min(st["tp_price"], new_tp) if np.isfinite(st["tp_price"]) else new_tp

                if prev_pos == 1:
                    sl_ok = (not np.isfinite(st["sl_price"])) or (close_price >= st["sl_price"])
                    tp_ok = (not np.isfinite(st["tp_price"])) or (close_price <= st["tp_price"])

                    if sl_ok and tp_ok:
                        if int(self.params["time_stop"]) > 0 and st["bars_in_trade"] >= int(self.params["time_stop"]):
                            if has_next:
                                exit_price = float(df["Open"].iloc[bar + 1])
                                exit_date = df.index[bar + 1]
                                self.sell_order(bar, symbol)
                                self._record_exit_event(symbol, st, "TIME", exit_date, exit_price)
                                st.update({
                                    "position": 0,
                                    "tp_price": np.nan,
                                    "sl_price": np.nan,
                                    "entry_price": np.nan,
                                    "run_max": np.nan,
                                    "run_min": np.nan,
                                    "bars_since_close": 0,
                                    "entry_leg": None,
                                    "entry_date": None,
                                    "entry_qty": 0,
                                    "entry_bar": -1,
                                })
                            continue
                    else:
                        if has_next:
                            exit_type = "SL" if np.isfinite(st["sl_price"]) and close_price < st["sl_price"] else "TP"
                            exit_price = float(df["Open"].iloc[bar + 1])
                            exit_date = df.index[bar + 1]
                            self.sell_order(bar, symbol)
                            self._record_exit_event(symbol, st, exit_type, exit_date, exit_price)
                            st.update({
                                "position": 0,
                                "tp_price": np.nan,
                                "sl_price": np.nan,
                                "entry_price": np.nan,
                                "run_max": np.nan,
                                "run_min": np.nan,
                                "bars_since_close": 0,
                                "entry_leg": None,
                                "entry_date": None,
                                "entry_qty": 0,
                                "entry_bar": -1,
                            })
                        continue

                elif prev_pos == -1:
                    sl_ok = (not np.isfinite(st["sl_price"])) or (close_price <= st["sl_price"])
                    tp_ok = (not np.isfinite(st["tp_price"])) or (close_price >= st["tp_price"])

                    if sl_ok and tp_ok:
                        if int(self.params["time_stop"]) > 0 and st["bars_in_trade"] >= int(self.params["time_stop"]):
                            if has_next:
                                exit_price = float(df["Open"].iloc[bar + 1])
                                exit_date = df.index[bar + 1]
                                self.cover_order(bar, symbol)
                                self._record_exit_event(symbol, st, "TIME", exit_date, exit_price)
                                st.update({
                                    "position": 0,
                                    "tp_price": np.nan,
                                    "sl_price": np.nan,
                                    "entry_price": np.nan,
                                    "run_max": np.nan,
                                    "run_min": np.nan,
                                    "bars_since_close": 0,
                                    "entry_leg": None,
                                    "entry_date": None,
                                    "entry_qty": 0,
                                    "entry_bar": -1,
                                })
                            continue
                    else:
                        if has_next:
                            exit_type = "SL" if np.isfinite(st["sl_price"]) and close_price > st["sl_price"] else "TP"
                            exit_price = float(df["Open"].iloc[bar + 1])
                            exit_date = df.index[bar + 1]
                            self.cover_order(bar, symbol)
                            self._record_exit_event(symbol, st, exit_type, exit_date, exit_price)
                            st.update({
                                "position": 0,
                                "tp_price": np.nan,
                                "sl_price": np.nan,
                                "entry_price": np.nan,
                                "run_max": np.nan,
                                "run_min": np.nan,
                                "bars_since_close": 0,
                                "entry_leg": None,
                                "entry_date": None,
                                "entry_qty": 0,
                                "entry_bar": -1,
                            })
                        continue

                if prev_pos == 0:
                    if st["bars_since_close"] < int(self.params["cooldown"]):
                        continue

                    if int(self.params["rebounce_block"]) > 0:
                        if (short_reversion or short_momentum) and st["bars_since_long"] < int(self.params["rebounce_block"]):
                            continue
                        if (long_reversion or long_momentum) and st["bars_since_short"] < int(self.params["rebounce_block"]):
                            continue

                    if st["buy_trend_counter"] < 4 and long_momentum and np.isfinite(atr_value):
                        if has_next:
                            self.buy_order(bar, symbol)
                            if self.quantity[symbol] > 0:
                                actual_entry = float(df["Open"].iloc[bar + 1])
                                trade_date = df.index[bar + 1]
                                st.update({
                                    "position": 1,
                                    "tp_price": actual_entry + atr_value * float(self.params["tp_mult_lm"]),
                                    "sl_price": actual_entry - atr_value * float(self.params["sl_mult_lm"]),
                                    "entry_price": actual_entry,
                                    "run_max": actual_entry,
                                    "run_min": actual_entry,
                                    "buy_trend_counter": st["buy_trend_counter"] + 1,
                                    "bars_in_trade": 0,
                                    "bars_since_long": 0,
                                    "entry_leg": "LM",
                                    "entry_date": trade_date,
                                    "entry_qty": abs(self.quantity[symbol]),
                                    "entry_bar": bar + 1,
                                })
                                self._record_entry_signal(
                                    symbol, "LONG", "LM", trade_date, actual_entry, atr_value,
                                    close_price, macd_hist, macd_zmid, macd_zpos,
                                    upper_band, mid_band, lower_band, st["tp_price"], st["sl_price"]
                                )
                        continue

                    if st["sell_trend_counter"] < 4 and short_momentum and np.isfinite(atr_value):
                        if has_next:
                            self.short_order(bar, symbol)
                            if self.quantity[symbol] < 0:
                                actual_entry = float(df["Open"].iloc[bar + 1])
                                trade_date = df.index[bar + 1]
                                st.update({
                                    "position": -1,
                                    "tp_price": actual_entry - atr_value * float(self.params["tp_mult_sm"]),
                                    "sl_price": actual_entry + atr_value * float(self.params["sl_mult_sm"]),
                                    "entry_price": actual_entry,
                                    "run_max": actual_entry,
                                    "run_min": actual_entry,
                                    "sell_trend_counter": st["sell_trend_counter"] + 1,
                                    "bars_in_trade": 0,
                                    "bars_since_short": 0,
                                    "entry_leg": "SM",
                                    "entry_date": trade_date,
                                    "entry_qty": abs(self.quantity[symbol]),
                                    "entry_bar": bar + 1,
                                })
                                self._record_entry_signal(
                                    symbol, "SHORT", "SM", trade_date, actual_entry, atr_value,
                                    close_price, macd_hist, macd_zmid, macd_zpos,
                                    upper_band, mid_band, lower_band, st["tp_price"], st["sl_price"]
                                )
                        continue

                    if st["buy_trend_counter"] > 1 and short_reversion and np.isfinite(atr_value):
                        if has_next:
                            self.short_order(bar, symbol)
                            if self.quantity[symbol] < 0:
                                actual_entry = float(df["Open"].iloc[bar + 1])
                                trade_date = df.index[bar + 1]
                                st.update({
                                    "position": -1,
                                    "tp_price": actual_entry - atr_value * float(self.params["tp_mult_sr"]),
                                    "sl_price": actual_entry + atr_value * float(self.params["sl_mult_sr"]),
                                    "entry_price": actual_entry,
                                    "run_max": actual_entry,
                                    "run_min": actual_entry,
                                    "bars_in_trade": 0,
                                    "bars_since_short": 0,
                                    "entry_leg": "SR",
                                    "entry_date": trade_date,
                                    "entry_qty": abs(self.quantity[symbol]),
                                    "entry_bar": bar + 1,
                                })
                                self._record_entry_signal(
                                    symbol, "SHORT", "SR", trade_date, actual_entry, atr_value,
                                    close_price, macd_hist, macd_zmid, macd_zpos,
                                    upper_band, mid_band, lower_band, st["tp_price"], st["sl_price"]
                                )
                        continue

                    if long_reversion and np.isfinite(atr_value):
                        if has_next:
                            self.buy_order(bar, symbol)
                            if self.quantity[symbol] > 0:
                                actual_entry = float(df["Open"].iloc[bar + 1])
                                trade_date = df.index[bar + 1]
                                st.update({
                                    "position": 1,
                                    "tp_price": actual_entry + atr_value * float(self.params["tp_mult_lr"]),
                                    "sl_price": actual_entry - atr_value * float(self.params["sl_mult_lr"]),
                                    "entry_price": actual_entry,
                                    "run_max": actual_entry,
                                    "run_min": actual_entry,
                                    "buy_trend_counter": 0,
                                    "bars_in_trade": 0,
                                    "bars_since_long": 0,
                                    "entry_leg": "LR",
                                    "entry_date": trade_date,
                                    "entry_qty": abs(self.quantity[symbol]),
                                    "entry_bar": bar + 1,
                                })
                                self._record_entry_signal(
                                    symbol, "LONG", "LR", trade_date, actual_entry, atr_value,
                                    close_price, macd_hist, macd_zmid, macd_zpos,
                                    upper_band, mid_band, lower_band, st["tp_price"], st["sl_price"]
                                )
                        continue

            bar_dict = {
                symbol: df.index.get_loc(cur_date) if cur_date in df.index else 0
                for symbol, df in self.all_data.items()
            }
            self.portfolio_history.append((cur_date, self.get_portfolio_value(bar_dict)))
            self._record_stock_equity(bar_dict)

        self._snapshot_open_positions(state)
        self.portfolio_df = pd.DataFrame(self.portfolio_history, columns=["Date", "PortfolioValue"]).set_index("Date")
        return self.portfolio_df


def _run_buy_and_hold_benchmark(ticker: str, start: str, end: str, capital: float) -> pd.Series | None:
    hist = yf.Ticker(ticker).history(start=start, end=end, interval="1d", auto_adjust=False)
    if hist.empty:
        return None

    df = hist.copy()
    if df.index.tz is not None:
        df.index = df.index.tz_localize(None)

    df = df[df.index >= pd.to_datetime(start)]
    if df.empty:
        return None

    first_open = float(df["Open"].iloc[0])
    qty = int(capital / first_open) if first_open > 0 else 0
    cash = capital - qty * first_open
    series = cash + qty * df["Close"].astype(float)
    series.name = ticker
    return series


def _price_returns_from_data(price_data: dict[str, pd.DataFrame], start_ts: pd.Timestamp) -> dict[str, pd.Series]:
    returns = {}
    for symbol, df in price_data.items():
        if df.empty:
            continue
        close = df[df.index >= start_ts]["Close"].pct_change().dropna()
        if not close.empty:
            returns[symbol] = close
    return returns


def _build_current_prices(price_data: dict[str, pd.DataFrame]) -> dict[str, dict]:
    out = {}
    for symbol, df in price_data.items():
        if len(df) < 2:
            continue
        out[symbol] = {
            "price": round(float(df["Close"].iloc[-1]), 2),
            "change": round(float((df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1) * 100), 2),
        }
    return out


def _build_current_atr(price_data: dict[str, pd.DataFrame]) -> dict[str, float]:
    out = {}
    for symbol, df in price_data.items():
        if "ATR" not in df.columns:
            continue
        valid = df["ATR"].dropna()
        out[symbol] = round(float(valid.iloc[-1]), 4) if not valid.empty else 0.0
    return out


def _attach_benchmark(daily_values: list[dict], benchmark_series: pd.Series | None):
    if benchmark_series is None or len(benchmark_series) == 0:
        for row in daily_values:
            row["benchmark"] = None
        return

    aligned = benchmark_series.reindex(pd.to_datetime([row["date"] for row in daily_values])).ffill()
    for row, value in zip(daily_values, aligned):
        row["benchmark"] = round(float(value), 2) if pd.notna(value) else None


def _annual_windows(start: str, end: str) -> list[tuple[int, str, str, str, str]]:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    windows = []

    for year in range(start_ts.year, end_ts.year + 1):
        prev_start = f"{year - 1}-01-01"
        prev_end = f"{year - 1}-12-31"
        trade_start_ts = max(pd.Timestamp(f"{year}-01-01"), start_ts)
        trade_end_ts = min(pd.Timestamp(f"{year}-12-31"), end_ts)
        if trade_start_ts > trade_end_ts:
            continue
        windows.append(
            (
                year,
                prev_start,
                prev_end,
                trade_start_ts.strftime("%Y-%m-%d"),
                trade_end_ts.strftime("%Y-%m-%d"),
            )
        )

    return windows


def run_full_strategy(params: dict | None = None) -> dict:
    params = dict(DEFAULT_PARAMS if params is None else params)
    params.setdefault("rebalance_freq", DEFAULT_PARAMS["rebalance_freq"])

    end_date = datetime.today().strftime("%Y-%m-%d")
    from optimizer import optimize_portfolio
    logger.info("Running notebook-faithful walk-forward backtest")

    running_capital = float(INITIAL_CAPITAL)
    combined_portfolios: list[pd.DataFrame] = []
    combined_trades: list[dict] = []
    combined_signals: list[dict] = []

    latest_universe = None
    latest_universe_portfolio = None
    latest_deployed = None
    selected_tickers = list(TICKERS)
    allocations = {t: round(1 / len(selected_tickers), 4) for t in selected_tickers}

    for year, prev_start, prev_end, trade_start, trade_end in _annual_windows(SIM_START, end_date):
        logger.info(
            "Walk-forward %s: allocate from %s -> %s, trade %s -> %s",
            year, prev_start, prev_end, trade_start, trade_end,
        )

        universe = MACDBBATRStrategy(
            TICKERS,
            prev_start,
            prev_end,
            params=params,
            rebalance_freq=int(params["rebalance_freq"]),
            interval="1d",
            capital=running_capital,
            transaction_cost=0.0,
            verbose=False,
            leverage=0.0,
        )
        universe_portfolio = universe.run_strategy()

        opt = optimize_portfolio(universe.stock_equity_history, risk_free=0.0, top_k=6)
        selected_tickers = opt.get("selected_tickers") or list(TICKERS)
        allocations = opt.get("allocations") or {t: round(1 / len(selected_tickers), 4) for t in selected_tickers}

        deployed = MACDBBATRStrategy(
            selected_tickers,
            trade_start,
            trade_end,
            params=params,
            rebalance_freq=int(params["rebalance_freq"]),
            interval="1d",
            capital=running_capital,
            transaction_cost=0.0,
            allocations=allocations,
            verbose=False,
            leverage=0.0,
        )
        deployed_portfolio = deployed.run_strategy()
        if deployed_portfolio is None or deployed_portfolio.empty:
            logger.warning("Walk-forward segment %s returned empty deployed portfolio", year)
            continue

        combined_portfolios.append(deployed_portfolio)
        combined_trades.extend(deployed.closed_trades)
        combined_signals.extend(deployed.signals)
        running_capital = float(deployed_portfolio["PortfolioValue"].iloc[-1])

        latest_universe = universe
        latest_universe_portfolio = universe_portfolio
        latest_deployed = deployed

    if not combined_portfolios or latest_deployed is None or latest_universe is None:
        raise RuntimeError("Walk-forward backtest produced no portfolio data.")

    combined_df = pd.concat(combined_portfolios)
    combined_df = combined_df[~combined_df.index.duplicated(keep="last")].sort_index()

    daily_values = [
        {"date": idx, "portfolio": round(float(value), 2)}
        for idx, value in combined_df["PortfolioValue"].items()
    ]

    benchmark_series = _run_buy_and_hold_benchmark(BENCHMARK, SIM_START, end_date, INITIAL_CAPITAL)
    _attach_benchmark(daily_values, benchmark_series)

    start_ts = pd.Timestamp(SIM_START)
    return {
        "daily_values": daily_values,
        "trades": combined_trades,
        "signals": combined_signals,
        "final_positions": latest_deployed.final_positions,
        "final_equity": dict(latest_deployed.capital),
        "stock_returns": _price_returns_from_data(latest_deployed.all_data, start_ts),
        "price_returns": _price_returns_from_data(latest_deployed.all_data, start_ts),
        "stock_equity_history": latest_deployed.stock_equity_history,
        "optimizer_history": latest_universe.stock_equity_history,
        "current_prices": _build_current_prices(latest_deployed.all_data),
        "current_atr": _build_current_atr(latest_deployed.all_data),
        "price_data": latest_deployed.all_data,
        "bench_df": benchmark_series,
        "initial_capital": INITIAL_CAPITAL,
        "params": params,
        "tickers": selected_tickers,
        "selected_tickers": selected_tickers,
        "optimizer_allocations": allocations,
        "optimizer_universe_portfolio": latest_universe_portfolio,
    }

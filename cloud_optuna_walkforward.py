"""
Standalone cloud tuning script for the notebook-faithful MACD-BB-ATR strategy.

What this script does:
1. Download OHLCV data once and reuse it across all trials.
2. Tune strategy parameters with Optuna on 4 chronological folds across 2020-2024.
3. Optimize for the highest average Sharpe across the 4 folds.
4. Run annual walk-forward portfolio allocation for 2025 -> now:
   - before each target year, run the strategy on the previous year over all 10 tickers
   - run portfolio optimization on that previous-year strategy history
   - trade the target year with the selected tickers and allocations

Example:
python cloud_optuna_walkforward.py \
  --n-trials 200 \
  --n-jobs 4 \
  --output-dir cloud_tuning_run
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import math
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from threading import Lock

import numpy as np
import optuna
import pandas as pd
import yfinance as yf
from sklearn.covariance import LedoitWolf
from ta.trend import MACD
from ta.volatility import AverageTrueRange


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("cloud_optuna_walkforward")


TICKERS = ["AAPL", "AMZN", "META", "GOOG", "GOOGL", "NVDA", "MSFT", "AVGO", "TSLA", "BRK-B"]
DEFAULT_PARAMS = {
    "macd_fast": 13,
    "macd_slow": 35,
    "macd_signal": 8,
    "macd_std_window": 83,
    "macd_k": 1.15,
    "macd_k_mid": 0.85,
    "bb_window": 15,
    "bb_std_dev": 1.4,
    "atr_window": 18,
    "tp_mult_lm": 3.5,
    "sl_mult_lm": 2.1,
    "tp_mult_sm": 5.9,
    "sl_mult_sm": 1.55,
    "tp_mult_lr": 10.6,
    "sl_mult_lr": 2.9,
    "tp_mult_sr": 5.5,
    "sl_mult_sr": 3.1,
    "use_trailing": False,
    "trail_mult": 3.7,
    "trail_tp": False,
    "time_stop": 26,
    "cooldown": 0,
    "rebounce_block": 2,
    "rebalance_freq": 120,
}
WARMUP_DAYS = 150
INITIAL_CAPITAL = 1_000_000.0
TOP_K = 6
RISK_FREE = 0.0
NOTEBOOK_SEARCH_SPACE = {
    "macd_fast": {"kind": "int", "low": 10, "high": 20},
    "macd_slow": {"kind": "int", "low": 35, "high": 44},
    "macd_signal": {"kind": "int", "low": 5, "high": 10},
    "macd_std_window": {"kind": "int", "low": 70, "high": 100},
    "macd_k": {"kind": "float", "low": 1.0, "high": 2.0, "step": 0.05},
    "macd_k_mid": {"kind": "float", "low": 0.5, "high": 1.0, "step": 0.05},
    "bb_window": {"kind": "int", "low": 14, "high": 25},
    "bb_std_dev": {"kind": "float", "low": 1.4, "high": 2.5, "step": 0.05},
    "atr_window": {"kind": "int", "low": 10, "high": 20},
    "tp_mult_lm": {"kind": "float", "low": 3.5, "high": 6.0, "step": 0.1},
    "sl_mult_lm": {"kind": "float", "low": 1.0, "high": 2.2, "step": 0.05},
    "tp_mult_sm": {"kind": "float", "low": 3.0, "high": 7.0, "step": 0.1},
    "sl_mult_sm": {"kind": "float", "low": 1.0, "high": 2.0, "step": 0.05},
    "tp_mult_lr": {"kind": "float", "low": 8.0, "high": 17.0, "step": 0.2},
    "sl_mult_lr": {"kind": "float", "low": 2.0, "high": 5.0, "step": 0.1},
    "tp_mult_sr": {"kind": "float", "low": 3.0, "high": 7.0, "step": 0.1},
    "sl_mult_sr": {"kind": "float", "low": 1.5, "high": 3.5, "step": 0.1},
    "use_trailing": {"kind": "categorical", "choices": [True, False]},
    "trail_mult": {"kind": "float", "low": 1.5, "high": 4.0, "step": 0.1},
    "trail_tp": {"kind": "categorical", "choices": [True, False]},
    "time_stop": {"kind": "int", "low": 0, "high": 30},
    "cooldown": {"kind": "int", "low": 0, "high": 5},
    "rebounce_block": {"kind": "int", "low": 0, "high": 6},
    "rebalance_freq": {"kind": "int", "low": 30, "high": 180, "step": 30},
}


@dataclass
class Fold:
    name: str
    start: str
    end: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Standalone Optuna + walk-forward tuning script.")
    parser.add_argument("--train-start", default="2020-01-01")
    parser.add_argument("--train-end", default="2024-12-31")
    parser.add_argument("--n-folds", type=int, default=4)
    parser.add_argument("--test-start-year", type=int, default=2025)
    parser.add_argument("--top-k", type=int, default=TOP_K)
    parser.add_argument("--initial-capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--n-trials", type=int, default=200)
    parser.add_argument("--n-jobs", type=int, default=1)
    parser.add_argument("--timeout", type=int, default=0, help="Seconds. 0 means no timeout.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--storage", default="", help="Optional Optuna storage. Leave empty to keep everything in memory and export CSV only.")
    parser.add_argument("--study-name", default="macd_bb_atr_cloud_tuning")
    parser.add_argument("--output-dir", default="cloud_tuning_output")
    return parser.parse_args()


def build_time_folds(train_start: str, train_end: str, n_folds: int) -> list[Fold]:
    start_ts = pd.Timestamp(train_start)
    end_ts = pd.Timestamp(train_end)
    if end_ts <= start_ts:
        raise ValueError("train-end must be after train-start")

    if train_start == "2020-01-01" and train_end == "2024-12-31" and n_folds == 4:
        return [
            Fold(name="fold_1", start="2020-01-01", end="2021-03-31"),
            Fold(name="fold_2", start="2021-04-01", end="2022-06-30"),
            Fold(name="fold_3", start="2022-07-01", end="2023-09-30"),
            Fold(name="fold_4", start="2023-10-01", end="2024-12-31"),
        ]

    if train_start == "2020-01-01" and n_folds == 5 and end_ts >= pd.Timestamp("2025-01-01"):
        return [
            Fold(name="fold_1", start="2020-01-01", end="2021-03-31"),
            Fold(name="fold_2", start="2021-04-01", end="2022-06-30"),
            Fold(name="fold_3", start="2022-07-01", end="2023-09-30"),
            Fold(name="fold_4", start="2023-10-01", end="2024-12-31"),
            Fold(name="fold_5", start="2025-01-01", end=end_ts.strftime("%Y-%m-%d")),
        ]

    boundaries = pd.date_range(start=start_ts, end=end_ts + pd.Timedelta(days=1), periods=n_folds + 1)
    folds: list[Fold] = []
    for idx in range(n_folds):
        fold_start = boundaries[idx].normalize()
        if idx == n_folds - 1:
            fold_end = end_ts
        else:
            fold_end = (boundaries[idx + 1].normalize() - pd.Timedelta(days=1))
        folds.append(
            Fold(
                name=f"fold_{idx + 1}",
                start=fold_start.strftime("%Y-%m-%d"),
                end=fold_end.strftime("%Y-%m-%d"),
            )
        )
    return folds


def build_calendar_year_segments(start: str, end: str) -> list[tuple[int, str, str]]:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if end_ts < start_ts:
        return []

    segments: list[tuple[int, str, str]] = []
    current = start_ts
    while current <= end_ts:
        segment_end = min(pd.Timestamp(f"{current.year}-12-31"), end_ts)
        segments.append(
            (
                current.year,
                current.strftime("%Y-%m-%d"),
                segment_end.strftime("%Y-%m-%d"),
            )
        )
        current = segment_end + pd.Timedelta(days=1)
    return segments


def data_download_start(train_start: str, test_start_year: int) -> str:
    train_prev_year = pd.Timestamp(f"{pd.Timestamp(train_start).year - 1}-01-01")
    earliest_needed = min(train_prev_year, pd.Timestamp(f"{test_start_year - 1}-01-01"))
    return (earliest_needed - pd.Timedelta(days=WARMUP_DAYS + 45)).strftime("%Y-%m-%d")


def download_data(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    logger.info("Downloading market data from %s to %s", start, end)
    out: dict[str, pd.DataFrame] = {}
    for ticker in tickers:
        hist = yf.Ticker(ticker).history(start=start, end=end, interval="1d", auto_adjust=False)
        if hist.empty:
            logger.warning("No data for %s", ticker)
            out[ticker] = pd.DataFrame()
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

        out[ticker] = df
        logger.info("Loaded %s bars for %s", len(df), ticker)
    return out


class CommonClass:
    def __init__(
        self,
        data_cache: dict[str, pd.DataFrame],
        symbols: list[str],
        start: str,
        end: str,
        interval: str,
        capital: float,
        transaction_cost: float,
        allocations: dict[str, float] | None = None,
        verbose: bool = False,
        rebalance_freq: int | None = None,
        warmup_days: int = WARMUP_DAYS,
        leverage: float = 0.0,
        params: dict | None = None,
    ):
        self.data_cache = data_cache
        self.symbols = list(symbols)
        self.start = pd.Timestamp(start)
        self.end = pd.Timestamp(end)
        self.interval = interval
        self.initial_capital = float(capital)
        self.warmup_days = int(warmup_days)
        self.rebalance_freq = rebalance_freq
        self.leverage = float(leverage)
        self.params = dict(params or {})
        self.data_start = self.start - pd.Timedelta(days=self.warmup_days)

        if allocations is None:
            self.allocations = {s: 1.0 / len(self.symbols) for s in self.symbols}
        else:
            total = sum(float(v) for v in allocations.values())
            self.allocations = {s: float(allocations[s]) / total for s in self.symbols}

        self.capital = {s: self.initial_capital * self.allocations[s] for s in self.symbols}
        self.transaction_cost = float(transaction_cost)
        self.verbose = verbose

        self.all_data: dict[str, pd.DataFrame] = {}
        self.position = {s: 0 for s in self.symbols}
        self.quantity = {s: 0 for s in self.symbols}
        self.trades = {s: 0 for s in self.symbols}
        self.portfolio_history: list[tuple[pd.Timestamp, float]] = []
        self.portfolio_df: pd.DataFrame | None = None
        self.stock_equity_history = {s: [] for s in self.symbols}
        self.closed_trades: list[dict] = []
        self.final_positions: dict[str, dict] = {}

        self.prepare_data()

    def prepare_data(self) -> None:
        for symbol in self.symbols:
            base = self.data_cache.get(symbol, pd.DataFrame()).copy()
            if base.empty:
                self.all_data[symbol] = pd.DataFrame()
                continue
            df = base[(base.index >= self.data_start) & (base.index <= self.end)].copy()
            self.all_data[symbol] = df

    def _get_date_price(self, bar: int, price_type: str = "Open", symbol: str | None = None) -> tuple[pd.Timestamp, float]:
        df = self.all_data[symbol]
        if df.empty or bar >= len(df):
            raise IndexError(f"Bar {bar} out of range for {symbol}")
        date = df.index[bar]
        return date, float(df[price_type].iloc[bar])

    def _record_stock_equity(self, bar_dict: dict[str, int]) -> None:
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

            self.stock_equity_history[symbol].append((date, price, equity, strategy_logreturn, stock_logreturn))

    def get_portfolio_value(self, bar: int | dict[str, int]) -> float:
        total_value = 0.0
        bar_dict = bar if isinstance(bar, dict) else {s: bar for s in self.symbols}
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

    def buy_order(self, bar: int, symbol: str, quantity: int | None = None, dollar: float | None = None) -> None:
        _, price = self._get_date_price(bar + 1, "Open", symbol)
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

    def sell_order(self, bar: int, symbol: str, quantity: int | None = None) -> None:
        _, price = self._get_date_price(bar + 1, "Open", symbol)
        held = self.quantity[symbol]
        if held <= 0:
            return
        qty = held if quantity is None else min(int(quantity), held)
        if qty <= 0:
            return

        proceeds = qty * price * (1.0 - self.transaction_cost)
        self.capital[symbol] += proceeds
        self.quantity[symbol] -= qty
        self.trades[symbol] += 1
        self.position[symbol] = 1 if self.quantity[symbol] > 0 else 0

    def short_order(self, bar: int, symbol: str, quantity: int | None = None, dollar: float | None = None) -> None:
        _, price = self._get_date_price(bar + 1, "Open", symbol)
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

    def cover_order(self, bar: int, symbol: str, quantity: int | None = None) -> None:
        _, price = self._get_date_price(bar + 1, "Open", symbol)
        held = self.quantity[symbol]
        if held >= 0:
            return
        shorted_qty = abs(held)
        qty = shorted_qty if quantity is None else min(int(quantity), shorted_qty)
        if qty <= 0:
            return

        cost = qty * price * (1.0 + self.transaction_cost)
        if self.leverage <= 0.0 and cost > self.capital[symbol]:
            return

        self.capital[symbol] -= cost
        self.quantity[symbol] += qty
        self.trades[symbol] += 1
        self.position[symbol] = -1 if self.quantity[symbol] < 0 else 0

    def rebalance(self, total_cash: float, new_allocations: dict[str, float] | None = None) -> None:
        if new_allocations is not None:
            total = sum(new_allocations.values())
            self.allocations = {s: float(v) / total for s, v in new_allocations.items()}
        for symbol in self.symbols:
            self.capital[symbol] = total_cash * self.allocations[symbol]
            self.quantity[symbol] = 0
            self.position[symbol] = 0


class MACDBBATRStrategy(CommonClass):
    def __init__(self, data_cache: dict[str, pd.DataFrame], symbols: list[str], start: str, end: str,
                 params: dict | None = None, rebalance_freq: int = 90, warmup_days: int = WARMUP_DAYS, **kwargs):
        strategy_params = dict(params or {})
        if "rebalance_freq" in strategy_params:
            rebalance_freq = int(strategy_params.pop("rebalance_freq"))

        merged_params = DEFAULT_PARAMS.copy()
        merged_params.update(strategy_params)

        super().__init__(
            data_cache=data_cache,
            symbols=symbols,
            start=start,
            end=end,
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
            self.all_data[symbol] = self._compute_indicators(self.all_data[symbol].copy())

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

        def calc_mad(arr: np.ndarray) -> float:
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

    def _record_exit_event(self, symbol: str, state_row: dict, exit_type: str, exit_date: pd.Timestamp, exit_price: float) -> None:
        qty = int(abs(state_row["entry_qty"]))
        if qty <= 0:
            return

        direction = "LONG" if state_row["position"] == 1 else "SHORT"
        entry_price = float(state_row["entry_price"])
        pnl = ((exit_price - entry_price) * qty) if direction == "LONG" else ((entry_price - exit_price) * qty)
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

    def _snapshot_open_positions(self, state: dict[str, dict]) -> None:
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
                "entry_date": pd.Timestamp(st["entry_date"]).strftime("%Y-%m-%d") if st["entry_date"] is not None else None,
            }
        self.final_positions = snapshot

    def run_strategy(self) -> pd.DataFrame:
        all_dates = sorted(set().union(*[df.index for df in self.all_data.values() if not df.empty]))
        trading_dates = [d for d in all_dates if d >= self.start]

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
                        if int(self.params["time_stop"]) > 0 and st["bars_in_trade"] >= int(self.params["time_stop"]) and has_next:
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
                            })
                        continue
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
                        })
                    continue

                if prev_pos == -1:
                    sl_ok = (not np.isfinite(st["sl_price"])) or (close_price <= st["sl_price"])
                    tp_ok = (not np.isfinite(st["tp_price"])) or (close_price >= st["tp_price"])
                    if sl_ok and tp_ok:
                        if int(self.params["time_stop"]) > 0 and st["bars_in_trade"] >= int(self.params["time_stop"]) and has_next:
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
                            })
                        continue
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
                                    "entry_date": df.index[bar + 1],
                                    "entry_qty": abs(self.quantity[symbol]),
                                })
                        continue

                    if st["sell_trend_counter"] < 4 and short_momentum and np.isfinite(atr_value):
                        if has_next:
                            self.short_order(bar, symbol)
                            if self.quantity[symbol] < 0:
                                actual_entry = float(df["Open"].iloc[bar + 1])
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
                                    "entry_date": df.index[bar + 1],
                                    "entry_qty": abs(self.quantity[symbol]),
                                })
                        continue

                    if st["buy_trend_counter"] > 1 and short_reversion and np.isfinite(atr_value):
                        if has_next:
                            self.short_order(bar, symbol)
                            if self.quantity[symbol] < 0:
                                actual_entry = float(df["Open"].iloc[bar + 1])
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
                                    "entry_date": df.index[bar + 1],
                                    "entry_qty": abs(self.quantity[symbol]),
                                })
                        continue

                    if long_reversion and np.isfinite(atr_value):
                        if has_next:
                            self.buy_order(bar, symbol)
                            if self.quantity[symbol] > 0:
                                actual_entry = float(df["Open"].iloc[bar + 1])
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
                                    "entry_date": df.index[bar + 1],
                                    "entry_qty": abs(self.quantity[symbol]),
                                })
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


def compute_sharpe(portfolio_df: pd.DataFrame, risk_free: float = 0.0) -> float:
    if portfolio_df is None or portfolio_df.empty or len(portfolio_df) < 60:
        return float("-inf")
    returns = portfolio_df["PortfolioValue"].pct_change().dropna()
    if returns.empty or returns.std() <= 0:
        return float("-inf")
    rf_daily = (1 + risk_free) ** (1 / 252) - 1
    return float(np.sqrt(252) * (returns.mean() - rf_daily) / returns.std())


def compute_summary(portfolio_df: pd.DataFrame, initial_capital: float, risk_free: float = 0.0) -> dict:
    if portfolio_df is None or portfolio_df.empty:
        return {}
    values = portfolio_df["PortfolioValue"].astype(float)
    returns = values.pct_change().dropna()
    peaks = values.cummax()
    dd = (values / peaks - 1.0) * 100
    years = max((values.index[-1] - values.index[0]).days / 365.25, 1 / 365.25)
    total_return = (values.iloc[-1] / initial_capital - 1.0) * 100
    cagr = ((values.iloc[-1] / initial_capital) ** (1 / years) - 1) * 100 if initial_capital > 0 else 0.0
    rf_daily = (1 + risk_free) ** (1 / 252) - 1
    sharpe = (np.sqrt(252) * (returns.mean() - rf_daily) / returns.std()) if len(returns) > 1 and returns.std() > 0 else 0.0
    return {
        "start": values.index[0].strftime("%Y-%m-%d"),
        "end": values.index[-1].strftime("%Y-%m-%d"),
        "start_capital": round(float(initial_capital), 2),
        "end_value": round(float(values.iloc[-1]), 2),
        "total_return_pct": round(float(total_return), 2),
        "cagr_pct": round(float(cagr), 2),
        "sharpe": round(float(sharpe), 4),
        "max_drawdown_pct": round(float(dd.min()), 2),
        "current_drawdown_pct": round(float(dd.iloc[-1]), 2),
    }


def run_multi_stock_backtest_unified(
    data_cache: dict[str, pd.DataFrame],
    tickers: list[str],
    start: str,
    end: str,
    interval: str,
    initial_capital: float,
    strategy_class,
    tuning: bool = False,
    show_each_stock: bool = False,
    buyandhold: bool = False,
    benchmark_ticker: str = "SPY",
    benchmark_column: str = "Adj Close",
    **kwargs,
):
    """
    Notebook-style wrapper used to instantiate the strategy and return:
    portfolio_df, strategy, stock_performances
    """
    del tuning, show_each_stock, buyandhold, benchmark_ticker, benchmark_column

    allocations = kwargs.get("allocations", None)
    params_dict = dict(kwargs.get("params", {}) or {})
    rebalance_freq = int(params_dict.pop("rebalance_freq", kwargs.get("rebalance_freq", DEFAULT_PARAMS["rebalance_freq"])))
    leverage = kwargs.get("leverage", 0.0)

    strategy = strategy_class(
        data_cache=data_cache,
        symbols=tickers,
        start=start,
        end=end,
        interval=interval,
        capital=initial_capital,
        transaction_cost=kwargs.get("transaction_cost", 0.0),
        allocations=allocations,
        rebalance_freq=rebalance_freq,
        leverage=leverage,
        verbose=kwargs.get("verbose", False),
        params=params_dict,
    )
    portfolio_df = strategy.run_strategy()

    if portfolio_df is None or portfolio_df.empty:
        return None, strategy, {}

    allocs = strategy.allocations
    stock_performances = {}
    for symbol in strategy.symbols:
        df = strategy.all_data[symbol]
        if df.empty:
            stock_performances[symbol] = {
                "initial_capital": 0.0,
                "final_value": 0.0,
                "return_pct": 0.0,
                "trades": 0,
            }
            continue

        alloc_weight = float(allocs.get(symbol, 1.0 / len(strategy.symbols)))
        init_cap = strategy.initial_capital * alloc_weight
        symbol_equity = strategy.capital[symbol]
        trades = int(strategy.trades.get(symbol, 0))
        stock_return = ((symbol_equity - init_cap) / init_cap) * 100 if init_cap > 0 else 0.0

        stock_performances[symbol] = {
            "initial_capital": round(float(init_cap), 2),
            "final_value": round(float(symbol_equity), 2),
            "return_pct": round(float(stock_return), 2),
            "trades": trades,
        }

    return portfolio_df, strategy, stock_performances


class PerformanceMetrics:
    """
    Notebook-style performance metrics class.
    """

    def __init__(self, portfolio_df: pd.DataFrame, initial_capital: float,
                 benchmark_series: pd.Series | None = None, risk_free_rate: float = 0.0):
        self.df = portfolio_df.copy()
        self.initial_capital = float(initial_capital)
        self.risk_free_rate = float(risk_free_rate)

        self.df["Return"] = self.df["PortfolioValue"].pct_change().fillna(0.0)

        self.benchmark = None
        if benchmark_series is not None:
            bench = benchmark_series.reindex(self.df.index).ffill()
            self.benchmark = bench
            self.df["BenchmarkReturn"] = bench.pct_change().fillna(0.0)
        else:
            self.df["BenchmarkReturn"] = np.nan

    def sharpe(self, annualization_factor: int = 252) -> float:
        std = self.df["Return"].std()
        if std <= 0:
            return np.nan
        rf_daily = (1 + self.risk_free_rate) ** (1 / annualization_factor) - 1
        excess_ret = self.df["Return"] - rf_daily
        return np.sqrt(annualization_factor) * excess_ret.mean() / std

    def max_drawdown(self) -> float:
        roll_max = self.df["PortfolioValue"].cummax()
        dd = (self.df["PortfolioValue"] / roll_max) - 1.0
        return dd.min()

    def calmar(self) -> float:
        total_ret = self.df["PortfolioValue"].iloc[-1] / self.df["PortfolioValue"].iloc[0] - 1
        mdd = abs(self.max_drawdown())
        return total_ret / mdd if mdd != 0 else np.nan

    def total_return(self) -> float:
        return (self.df["PortfolioValue"].iloc[-1] / self.df["PortfolioValue"].iloc[0] - 1) * 100

    def cagr(self) -> float:
        days = (self.df.index[-1] - self.df.index[0]).days
        years = days / 365.25
        if years <= 0:
            return 0.0
        return ((self.df["PortfolioValue"].iloc[-1] / self.initial_capital) ** (1 / years) - 1) * 100

    def volatility(self, annualization_factor: int = 252) -> float:
        return self.df["Return"].std() * np.sqrt(annualization_factor) * 100

    def beta(self) -> float:
        if self.benchmark is None:
            return np.nan
        r_p = self.df["Return"]
        r_m = self.df["BenchmarkReturn"]
        cov = np.cov(r_p, r_m)[0, 1]
        var_m = np.var(r_m)
        return cov / var_m if var_m > 0 else np.nan

    def alpha(self, annualization_factor: int = 252) -> float:
        if self.benchmark is None:
            return np.nan
        beta = self.beta()
        if np.isnan(beta):
            return np.nan
        r_p = self.df["Return"].mean()
        r_m = self.df["BenchmarkReturn"].mean()
        rf_period = (1 + self.risk_free_rate) ** (1 / annualization_factor) - 1
        exp_rp = rf_period + beta * (r_m - rf_period)
        alpha_period = r_p - exp_rp
        return alpha_period * annualization_factor * 100

    def sortino(self, annualization_factor: int = 252) -> float:
        rf_period = (1 + self.risk_free_rate) ** (1 / annualization_factor) - 1
        excess = self.df["Return"] - rf_period
        downside = excess[excess < 0]
        if len(downside) == 0:
            return np.nan
        downside_std = downside.std()
        if downside_std == 0:
            return np.nan
        return np.sqrt(annualization_factor) * excess.mean() / downside_std

    def omega_ratio(self, threshold: float = 0.0) -> float:
        r = self.df["Return"]
        gains = np.clip(r - threshold, 0, None).sum()
        losses = np.clip(threshold - r, 0, None).sum()
        return gains / losses if losses > 0 else np.nan

    def ulcer_index(self) -> float:
        cummax = self.df["PortfolioValue"].cummax()
        drawdown_pct = (self.df["PortfolioValue"] / cummax - 1) * 100.0
        return np.sqrt(np.mean(drawdown_pct ** 2))

    def upside_potential_ratio(self, threshold: float = 0.0) -> float:
        r = self.df["Return"]
        excess = r - threshold
        upside = np.clip(excess, 0, None)
        downside = np.clip(excess, None, 0)
        downside_mean_sq = (downside ** 2).mean()
        if downside_mean_sq == 0:
            return np.nan
        return upside.mean() / np.sqrt(downside_mean_sq)

    def skewness(self) -> float:
        return self.df["Return"].skew()

    def kurtosis(self) -> float:
        return self.df["Return"].kurtosis()

    def var(self, level: float = 0.95) -> float:
        r = self.df["Return"].dropna()
        if len(r) == 0:
            return np.nan
        var_ret = np.quantile(r, 1 - level)
        return -var_ret * 100

    def cvar(self, level: float = 0.95) -> float:
        r = self.df["Return"].dropna()
        if len(r) == 0:
            return np.nan
        var_ret = np.quantile(r, 1 - level)
        tail_losses = r[r <= var_ret]
        if len(tail_losses) == 0:
            return np.nan
        return -tail_losses.mean() * 100

    def to_dict(self) -> dict:
        return {
            "total_return_pct": round(float(self.total_return()), 2),
            "cagr_pct": round(float(self.cagr()), 2),
            "volatility_pct": round(float(self.volatility()), 2),
            "sharpe": round(float(self.sharpe()), 4) if np.isfinite(self.sharpe()) else None,
            "max_drawdown_pct": round(float(self.max_drawdown() * 100), 2) if np.isfinite(self.max_drawdown()) else None,
            "calmar": round(float(self.calmar()), 4) if np.isfinite(self.calmar()) else None,
            "beta": round(float(self.beta()), 4) if np.isfinite(self.beta()) else None,
            "alpha_pct": round(float(self.alpha()), 2) if np.isfinite(self.alpha()) else None,
            "sortino": round(float(self.sortino()), 4) if np.isfinite(self.sortino()) else None,
            "omega": round(float(self.omega_ratio()), 4) if np.isfinite(self.omega_ratio()) else None,
            "ulcer_index": round(float(self.ulcer_index()), 4) if np.isfinite(self.ulcer_index()) else None,
            "upi": round(float(self.upside_potential_ratio()), 4) if np.isfinite(self.upside_potential_ratio()) else None,
            "skewness": round(float(self.skewness()), 4) if np.isfinite(self.skewness()) else None,
            "kurtosis": round(float(self.kurtosis()), 4) if np.isfinite(self.kurtosis()) else None,
            "var95_pct": round(float(self.var()), 2) if np.isfinite(self.var()) else None,
            "cvar95_pct": round(float(self.cvar()), 2) if np.isfinite(self.cvar()) else None,
        }


class ModernPortfolioOptimizerPro:
    """
    Notebook-faithful optimizer class.
    """

    def __init__(self, stock_equity_history=None, return_matrix: pd.DataFrame | None = None,
                 top_k=None, weight_threshold=0.05, verbose=True):
        self.verbose = verbose
        self._strategy_hist = stock_equity_history or {}
        self._return_matrix = return_matrix.copy() if return_matrix is not None else None
        self.symbols = list(self._return_matrix.columns) if self._return_matrix is not None else sorted(self._strategy_hist.keys())
        self.top_k = top_k
        self.weight_threshold = weight_threshold

        self.mean_returns = None
        self.cov_matrix = None
        self.weights = None
        self.portfolio_df = None
        self.risk_free_rate = 0.0

    def _prepare_inputs(self):
        if self._return_matrix is not None:
            return _clean_return_matrix(self._return_matrix, "No valid return series available.")
        return _build_strategy_return_matrix(self._strategy_hist)

    def compute_statistics(self, data, annualize=True, ridge_alpha=1e-5, winsorize=True):
        if winsorize:
            data = data.clip(lower=data.quantile(0.01), upper=data.quantile(0.99), axis=1)

        weights = np.exp(np.linspace(-1, 0, len(data)))
        weights /= weights.sum()
        self.mean_returns = (data * weights[:, None]).sum(axis=0).values

        lw = LedoitWolf().fit(data.values)
        self.cov_matrix = lw.covariance_

        if annualize:
            self.mean_returns *= 252
            self.cov_matrix *= 252

        ridge = ridge_alpha * np.trace(self.cov_matrix) / len(self.cov_matrix)
        self.cov_matrix += ridge * np.eye(len(self.cov_matrix))

    def tangent_portfolio(self, risk_free_rate=0.0, long_only=True, lambda_reg=1e-3):
        mu = self.mean_returns
        sigma = self.cov_matrix + lambda_reg * np.eye(len(self.cov_matrix))
        mu_excess = mu - risk_free_rate
        inv_sigma = np.linalg.pinv(sigma)
        weights = inv_sigma @ mu_excess
        if long_only:
            weights = np.maximum(weights, 0)
        total = weights.sum()
        if total <= 0:
            weights = np.repeat(1.0 / len(weights), len(weights))
        else:
            weights /= total
        self.weights = weights
        self.risk_free_rate = risk_free_rate
        return weights

    def portfolio_metrics(self, weights):
        mu, sigma, rf = self.mean_returns, self.cov_matrix, self.risk_free_rate
        ret = mu @ weights
        vol = np.sqrt(weights @ sigma @ weights)
        sharpe = (ret - rf) / vol if vol > 0 else 0.0
        return ret, vol, sharpe

    def efficient_frontier(self, num_points=30):
        mu, sigma = self.mean_returns, self.cov_matrix
        inv_sigma = np.linalg.pinv(sigma)
        ones = np.ones(len(mu))

        a = ones @ inv_sigma @ ones
        b = ones @ inv_sigma @ mu
        c = mu @ inv_sigma @ mu
        d = a * c - b ** 2

        target_returns = np.linspace(mu.min(), mu.max(), num_points)
        frontier = []
        for target in target_returns:
            weights = inv_sigma @ ((c - b * target) * ones + (a * target - b) * mu) / d
            weights = np.maximum(weights, 0)
            total = weights.sum()
            if total <= 0:
                weights = np.repeat(1.0 / len(weights), len(weights))
            else:
                weights /= total
            ret, vol, sharpe = self.portfolio_metrics(weights)
            frontier.append({"Return": ret, "Volatility": vol, "Sharpe": sharpe})
        return pd.DataFrame(frontier)

    def get_allocations(self):
        df = pd.DataFrame({"Stock": self.symbols, "Weight": self.weights})
        df = df.sort_values("Weight", ascending=False)

        if self.top_k and self.top_k > 0:
            df = df.iloc[:self.top_k]
        else:
            df = df[df["Weight"].abs() > self.weight_threshold]

        total = df["Weight"].sum()
        df["Weight"] = (df["Weight"] / total).round(4)
        allocations = dict(zip(df["Stock"], df["Weight"]))
        return df["Stock"].tolist(), allocations

    def run(self, mode="tangent", long_only=True, risk_free_rate=0.0):
        del mode
        data = self._prepare_inputs()
        self.symbols = list(data.columns)
        self.compute_statistics(data)
        self.risk_free_rate = risk_free_rate
        self.tangent_portfolio(risk_free_rate=risk_free_rate, long_only=long_only)
        frontier = self.efficient_frontier()
        selected_stocks, allocations = self.get_allocations()
        self.portfolio_df = (
            pd.DataFrame({"Stock": self.symbols, "Weight": self.weights})
            .sort_values("Weight", ascending=False)
            .round(4)
        )
        return frontier, selected_stocks, allocations


def logging_callback(study: optuna.Study, frozen_trial: optuna.Trial) -> None:
    logger.info("Trial %s finished with value=%s", frozen_trial.number, frozen_trial.value)
    if study.best_trial.number == frozen_trial.number:
        logger.info("New best trial %s | value=%.6f | params=%s", frozen_trial.number, frozen_trial.value, frozen_trial.params)


def build_trial_csv_callback(output_dir: Path):
    csv_lock = Lock()
    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "optuna_trials_live.csv"
    fieldnames = [
        "number",
        "value",
        "state",
        "datetime_start",
        "datetime_complete",
        "duration_seconds",
        "params_json",
        "fold_sharpes_json",
        "avg_cv_sharpe",
    ]

    def callback(study: optuna.Study, frozen_trial: optuna.trial.FrozenTrial) -> None:
        del study
        row = {
            "number": frozen_trial.number,
            "value": frozen_trial.value,
            "state": str(frozen_trial.state),
            "datetime_start": frozen_trial.datetime_start.isoformat() if frozen_trial.datetime_start else "",
            "datetime_complete": frozen_trial.datetime_complete.isoformat() if frozen_trial.datetime_complete else "",
            "duration_seconds": (
                (frozen_trial.datetime_complete - frozen_trial.datetime_start).total_seconds()
                if frozen_trial.datetime_start and frozen_trial.datetime_complete
                else ""
            ),
            "params_json": json.dumps(frozen_trial.params, sort_keys=True),
            "fold_sharpes_json": json.dumps(frozen_trial.user_attrs.get("fold_sharpes", {}), sort_keys=True),
            "avg_cv_sharpe": frozen_trial.user_attrs.get("avg_cv_sharpe", ""),
        }
        with csv_lock:
            file_exists = csv_path.exists()
            with csv_path.open("a", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(row)

    return callback


def _clean_return_matrix(return_matrix: pd.DataFrame, empty_error: str) -> pd.DataFrame:
    if return_matrix is None or return_matrix.empty:
        raise ValueError(empty_error)

    merged = return_matrix.sort_index().fillna(0.0).astype(float)
    var = merged.var(axis=0)
    keep = var[var > 1e-12].index
    merged = merged[keep]
    if merged.shape[1] == 0:
        raise ValueError("All return series have near-zero variance.")
    return merged


def _build_strategy_return_matrix(stock_equity_history: dict[str, list]) -> pd.DataFrame:
    dfs = []
    for symbol, history in (stock_equity_history or {}).items():
        if not history:
            continue
        df = pd.DataFrame(history, columns=["Date", "Price", "Equity", "StrategyRet", "StockRet"])
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).sort_values("Date")
        df = df.groupby("Date", as_index=True).agg({"StrategyRet": "sum"})
        dfs.append(df.rename(columns={"StrategyRet": symbol}))

    merged = pd.concat(dfs, axis=1, join="outer") if dfs else pd.DataFrame()
    return _clean_return_matrix(merged, "No valid strategy histories available.")


def _build_raw_stock_return_matrix(
    data_cache: dict[str, pd.DataFrame],
    tickers: list[str],
    start: str,
    end: str,
) -> pd.DataFrame:
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    dfs = []
    for symbol in tickers:
        base = data_cache.get(symbol, pd.DataFrame())
        if base.empty or "Return" not in base.columns:
            continue
        df = base[(base.index >= start_ts) & (base.index <= end_ts)][["Return"]].copy()
        if df.empty:
            continue
        dfs.append(df.rename(columns={"Return": symbol}))

    merged = pd.concat(dfs, axis=1, join="outer") if dfs else pd.DataFrame()
    return _clean_return_matrix(merged, "No valid raw stock return series available.")


def optimize_portfolio(
    stock_equity_history: dict[str, list] | None = None,
    risk_free: float = 0.0,
    top_k: int = 6,
    return_matrix: pd.DataFrame | None = None,
) -> dict:
    optimizer = ModernPortfolioOptimizerPro(
        stock_equity_history=stock_equity_history,
        return_matrix=return_matrix,
        top_k=top_k,
        verbose=False,
    )
    frontier, selected_tickers, allocations = optimizer.run(
        mode="tangent",
        risk_free_rate=risk_free,
        long_only=True,
    )
    raw_weights = optimizer.portfolio_df.rename(columns={"Stock": "ticker", "Weight": "weight"}).to_dict("records")
    return {
        "selected_tickers": selected_tickers,
        "allocations": allocations,
        "frontier": frontier.to_dict("records"),
        "raw_weights": raw_weights,
    }


def optimize_raw_portfolio(
    data_cache: dict[str, pd.DataFrame],
    tickers: list[str],
    start: str,
    end: str,
    risk_free: float = 0.0,
    top_k: int = 6,
) -> dict:
    return_matrix = _build_raw_stock_return_matrix(data_cache, tickers, start, end)
    return optimize_portfolio(
        stock_equity_history=None,
        risk_free=risk_free,
        top_k=top_k,
        return_matrix=return_matrix,
    )


def suggest_params(trial: optuna.Trial) -> dict:
    params = {}
    for name, spec in NOTEBOOK_SEARCH_SPACE.items():
        kind = spec["kind"]
        if kind == "int":
            step = spec.get("step")
            params[name] = (
                trial.suggest_int(name, spec["low"], spec["high"], step=step)
                if step is not None
                else trial.suggest_int(name, spec["low"], spec["high"])
            )
        elif kind == "float":
            params[name] = trial.suggest_float(name, spec["low"], spec["high"], step=spec.get("step"))
        elif kind == "categorical":
            params[name] = trial.suggest_categorical(name, spec["choices"])
        else:
            raise ValueError(f"Unsupported search space kind for {name}: {kind}")
    if params["macd_signal"] > params["macd_fast"]:
        params["macd_signal"] = params["macd_fast"]
    return params


def valid_params(params: dict) -> bool:
    if not (params["macd_fast"] < params["macd_slow"] and 8 <= params["macd_slow"] - params["macd_fast"] <= 22):
        return False
    if params["macd_k_mid"] >= params["macd_k"]:
        return False
    if params["tp_mult_lm"] < params["sl_mult_lm"]:
        return False
    if params["tp_mult_sm"] < params["sl_mult_sm"]:
        return False
    if params["tp_mult_lr"] <= params["sl_mult_lr"]:
        return False
    if params["tp_mult_sr"] <= params["sl_mult_sr"]:
        return False
    return True


def select_yearly_allocation(
    data_cache: dict[str, pd.DataFrame],
    params: dict,
    target_year: int,
    selection_capital: float,
    top_k: int,
    first_training_year: int,
) -> tuple[dict, str]:
    lookback_start = f"{target_year - 1}-01-01"
    lookback_end = f"{target_year - 1}-12-31"

    if target_year == first_training_year:
        return (
            optimize_raw_portfolio(
                data_cache=data_cache,
                tickers=TICKERS,
                start=lookback_start,
                end=lookback_end,
                risk_free=RISK_FREE,
                top_k=top_k,
            ),
            "raw_stock_returns",
        )

    _, universe, _ = run_multi_stock_backtest_unified(
        data_cache=data_cache,
        tickers=TICKERS,
        start=lookback_start,
        end=lookback_end,
        interval="1d",
        initial_capital=selection_capital,
        strategy_class=MACDBBATRStrategy,
        tuning=True,
        params=params,
        transaction_cost=0.0,
        verbose=False,
        leverage=0.0,
    )
    return (
        optimize_portfolio(
            stock_equity_history=universe.stock_equity_history,
            risk_free=RISK_FREE,
            top_k=top_k,
        ),
        "strategy_returns",
    )


def run_yearly_mpt_fold_backtest(
    data_cache: dict[str, pd.DataFrame],
    fold: Fold,
    params: dict,
    initial_capital: float,
    top_k: int,
    first_training_year: int,
) -> tuple[pd.DataFrame | None, list[dict]]:
    running_capital = float(initial_capital)
    combined_frames: list[pd.DataFrame] = []
    yearly_rows: list[dict] = []

    for year, segment_start, segment_end in build_calendar_year_segments(fold.start, fold.end):
        opt, allocation_source = select_yearly_allocation(
            data_cache=data_cache,
            params=params,
            target_year=year,
            selection_capital=running_capital,
            top_k=top_k,
            first_training_year=first_training_year,
        )

        portfolio_df, deployed, _ = run_multi_stock_backtest_unified(
            data_cache=data_cache,
            tickers=opt["selected_tickers"],
            start=segment_start,
            end=segment_end,
            interval="1d",
            initial_capital=running_capital,
            strategy_class=MACDBBATRStrategy,
            tuning=False,
            params=params,
            transaction_cost=0.0,
            allocations=opt["allocations"],
            verbose=False,
            leverage=0.0,
        )
        del deployed

        if portfolio_df is None or portfolio_df.empty:
            logger.warning("Empty fold portfolio for %s in year %s", fold.name, year)
            return None, yearly_rows

        yearly_summary = compute_summary(portfolio_df, running_capital, risk_free=RISK_FREE)
        yearly_summary.update(
            {
                "year": year,
                "segment_start": segment_start,
                "segment_end": segment_end,
                "allocation_source": allocation_source,
                "allocation_lookback_start": f"{year - 1}-01-01",
                "allocation_lookback_end": f"{year - 1}-12-31",
                "selected_tickers": opt["selected_tickers"],
                "allocations": opt["allocations"],
            }
        )
        yearly_rows.append(yearly_summary)
        combined_frames.append(portfolio_df)
        running_capital = float(portfolio_df["PortfolioValue"].iloc[-1])

    if not combined_frames:
        return None, yearly_rows

    combined_df = pd.concat(combined_frames)
    combined_df = combined_df[~combined_df.index.duplicated(keep="last")].sort_index()
    return combined_df, yearly_rows


def evaluate_fold(
    data_cache: dict[str, pd.DataFrame],
    fold: Fold,
    params: dict,
    initial_capital: float,
    top_k: int,
    first_training_year: int,
) -> tuple[float, pd.DataFrame | None, list[dict]]:
    try:
        portfolio_df, yearly_rows = run_yearly_mpt_fold_backtest(
            data_cache=data_cache,
            fold=fold,
            params=params,
            initial_capital=initial_capital,
            top_k=top_k,
            first_training_year=first_training_year,
        )
    except Exception as exc:
        logger.warning("Fold %s evaluation failed: %s", fold.name, exc)
        return float("-inf"), None, []

    if portfolio_df is None or portfolio_df.empty:
        return float("-inf"), portfolio_df, yearly_rows

    metrics = PerformanceMetrics(portfolio_df, initial_capital=initial_capital, risk_free_rate=RISK_FREE)
    sharpe = metrics.sharpe()
    return sharpe, portfolio_df, yearly_rows


def objective(trial: optuna.Trial, data_cache: dict[str, pd.DataFrame], folds: list[Fold],
              initial_capital: float, top_k: int, first_training_year: int,
              allocations=None, leverage: float = 0.0) -> float:
    del allocations, leverage
    params = suggest_params(trial)
    if not valid_params(params):
        return -1e9

    fold_sharpes = {}
    sharpe_values = []
    for fold in folds:
        sharpe, portfolio_df, yearly_rows = evaluate_fold(
            data_cache,
            fold,
            params,
            initial_capital,
            top_k=top_k,
            first_training_year=first_training_year,
        )
        if portfolio_df is None or portfolio_df.empty or not np.isfinite(sharpe):
            return -1e9
        fold_sharpes[fold.name] = round(float(sharpe), 4)
        del yearly_rows
        sharpe_values.append(float(sharpe))

    avg_sharpe = float(np.mean(sharpe_values))
    trial.set_user_attr("fold_sharpes", fold_sharpes)
    trial.set_user_attr("avg_cv_sharpe", round(avg_sharpe, 4))
    return avg_sharpe


def run_optimization(
    data_cache: dict[str, pd.DataFrame],
    folds: list[Fold],
    initial_capital: float,
    output_dir: Path,
    n_trials: int = 4000,
    top_k: int = TOP_K,
    first_training_year: int = 2020,
    leverage: float = 0.0,
    n_jobs: int = 1,
    timeout: int = 0,
    storage: str = "",
    study_name: str = "macd_bb_atr_cloud_tuning",
    seed: int = 42,
):
    if storage.startswith("sqlite:///") and n_jobs > 1:
        logger.warning(
            "SQLite storage + parallel Optuna jobs often causes 'database is locked'. "
            "Disabling storage and keeping the study in memory. Results will still be exported to CSV."
        )
        storage = ""

    sampler = optuna.samplers.TPESampler(seed=seed)
    study_kwargs = {
        "study_name": study_name,
        "direction": "maximize",
        "sampler": sampler,
        "load_if_exists": True,
    }
    if storage:
        study_kwargs["storage"] = storage

    study = optuna.create_study(**study_kwargs)
    trial_csv_callback = build_trial_csv_callback(output_dir)

    objective_with_params = lambda trial: objective(
        trial,
        data_cache,
        folds,
        initial_capital,
        top_k,
        first_training_year,
        allocations=None,
        leverage=leverage,
    )

    study.optimize(
        objective_with_params,
        n_trials=n_trials,
        n_jobs=n_jobs,
        timeout=None if timeout <= 0 else timeout,
        callbacks=[logging_callback, trial_csv_callback],
        gc_after_trial=True,
        show_progress_bar=False,
    )
    return study


def annual_windows(test_start_year: int, end_date: pd.Timestamp) -> list[tuple[int, str, str, str, str]]:
    windows = []
    for year in range(test_start_year, end_date.year + 1):
        prev_start = f"{year - 1}-01-01"
        prev_end = f"{year - 1}-12-31"
        test_start = f"{year}-01-01"
        test_end_ts = min(pd.Timestamp(f"{year}-12-31"), end_date)
        if pd.Timestamp(test_start) > end_date:
            break
        windows.append((year, prev_start, prev_end, test_start, test_end_ts.strftime("%Y-%m-%d")))
    return windows


def run_walkforward_backtest(
    data_cache: dict[str, pd.DataFrame],
    best_params: dict,
    test_start_year: int,
    end_date: pd.Timestamp,
    initial_capital: float,
    top_k: int,
) -> tuple[pd.DataFrame, list[dict]]:
    running_capital = float(initial_capital)
    yearly_rows: list[dict] = []
    combined_frames: list[pd.DataFrame] = []

    for year, prev_start, prev_end, test_start, test_end in annual_windows(test_start_year, end_date):
        logger.info("Walk-forward %s: allocate from %s -> %s, trade %s -> %s", year, prev_start, prev_end, test_start, test_end)

        _, universe, _ = run_multi_stock_backtest_unified(
            data_cache=data_cache,
            tickers=TICKERS,
            start=prev_start,
            end=prev_end,
            interval="1d",
            initial_capital=running_capital,
            strategy_class=MACDBBATRStrategy,
            tuning=True,
            params=best_params,
            transaction_cost=0.0,
            verbose=False,
            leverage=0.0,
        )
        opt = optimize_portfolio(universe.stock_equity_history, risk_free=RISK_FREE, top_k=top_k)

        portfolio_df, deployed, _ = run_multi_stock_backtest_unified(
            data_cache=data_cache,
            tickers=opt["selected_tickers"],
            start=test_start,
            end=test_end,
            interval="1d",
            initial_capital=running_capital,
            strategy_class=MACDBBATRStrategy,
            tuning=False,
            params=best_params,
            transaction_cost=0.0,
            allocations=opt["allocations"],
            verbose=False,
            leverage=0.0,
        )
        if portfolio_df is None or portfolio_df.empty:
            logger.warning("Empty portfolio for year %s", year)
            continue

        summary = compute_summary(portfolio_df, running_capital, risk_free=RISK_FREE)
        summary.update(
            {
                "year": year,
                "allocation_train_start": prev_start,
                "allocation_train_end": prev_end,
                "trade_start": test_start,
                "trade_end": test_end,
                "selected_tickers": opt["selected_tickers"],
                "allocations": opt["allocations"],
            }
        )
        yearly_rows.append(summary)
        combined_frames.append(portfolio_df)
        running_capital = float(portfolio_df["PortfolioValue"].iloc[-1])

    if not combined_frames:
        return pd.DataFrame(), yearly_rows

    combined = pd.concat(combined_frames)
    combined = combined[~combined.index.duplicated(keep="first")].sort_index()
    return combined, yearly_rows


def save_outputs(output_dir: Path, folds: list[Fold], best_params: dict, study: optuna.Study,
                 oos_df: pd.DataFrame, yearly_rows: list[dict], overall_summary: dict) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "folds.json").write_text(json.dumps([asdict(f) for f in folds], indent=2))
    (output_dir / "search_space.json").write_text(json.dumps(NOTEBOOK_SEARCH_SPACE, indent=2))
    (output_dir / "best_params.json").write_text(json.dumps(best_params, indent=2))
    (output_dir / "overall_summary.json").write_text(json.dumps(overall_summary, indent=2))
    (output_dir / "yearly_walkforward.json").write_text(json.dumps(yearly_rows, indent=2))
    study.trials_dataframe().to_csv(output_dir / "optuna_trials.csv", index=False)

    if not oos_df.empty:
        export_df = oos_df.copy()
        export_df.index.name = "Date"
        export_df.to_csv(output_dir / "oos_equity.csv")


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir)
    end_date = pd.Timestamp.today().normalize()
    train_end_ts = pd.Timestamp(args.train_end)
    first_training_year = pd.Timestamp(args.train_start).year
    folds = build_time_folds(args.train_start, args.train_end, args.n_folds)
    logger.info("Training folds: %s", [asdict(f) for f in folds])

    if args.test_start_year <= train_end_ts.year:
        logger.warning(
            "test-start-year=%s overlaps training window ending %s. Walk-forward output will overlap in-sample data.",
            args.test_start_year,
            args.train_end,
        )

    data_start = data_download_start(args.train_start, args.test_start_year)
    data_end = (end_date + pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    data_cache = download_data(TICKERS, data_start, data_end)

    logger.info("Starting Optuna: n_trials=%s n_jobs=%s timeout=%s", args.n_trials, args.n_jobs, args.timeout)
    study = run_optimization(
        data_cache=data_cache,
        folds=folds,
        initial_capital=args.initial_capital,
        output_dir=output_dir,
        n_trials=args.n_trials,
        top_k=args.top_k,
        first_training_year=first_training_year,
        leverage=0.0,
        n_jobs=args.n_jobs,
        timeout=args.timeout,
        storage=args.storage,
        study_name=args.study_name,
        seed=args.seed,
    )

    best_params = dict(study.best_trial.params)
    if best_params["macd_signal"] > best_params["macd_fast"]:
        best_params["macd_signal"] = best_params["macd_fast"]

    if not np.isfinite(study.best_value) or study.best_value <= -1e8:
        logger.warning("No valid Optuna trial found. Falling back to DEFAULT_PARAMS.")
        best_params = dict(DEFAULT_PARAMS)

    selected_fold_sharpes = {}
    for fold in folds:
        sharpe, _, _ = evaluate_fold(
            data_cache=data_cache,
            fold=fold,
            params=best_params,
            initial_capital=args.initial_capital,
            top_k=args.top_k,
            first_training_year=first_training_year,
        )
        selected_fold_sharpes[fold.name] = round(float(sharpe), 4) if np.isfinite(sharpe) else None
    valid_fold_sharpes = [value for value in selected_fold_sharpes.values() if value is not None]
    selected_avg_sharpe = round(float(np.mean(valid_fold_sharpes)), 4) if valid_fold_sharpes else None

    logger.info("Best value: %.6f", study.best_value)
    logger.info("Best params: %s", best_params)
    logger.info("Fold sharpes: %s", selected_fold_sharpes)
    logger.info("Average CV Sharpe across %s folds: %s", len(selected_fold_sharpes), selected_avg_sharpe)

    oos_df, yearly_rows = run_walkforward_backtest(
        data_cache=data_cache,
        best_params=best_params,
        test_start_year=args.test_start_year,
        end_date=end_date,
        initial_capital=args.initial_capital,
        top_k=args.top_k,
    )
    overall_summary = compute_summary(oos_df, args.initial_capital, risk_free=RISK_FREE) if not oos_df.empty else {}
    overall_summary["best_cv_avg_sharpe"] = selected_avg_sharpe
    overall_summary["study_best_value"] = round(float(study.best_value), 4) if np.isfinite(study.best_value) else None
    overall_summary["fold_sharpes"] = selected_fold_sharpes

    save_outputs(output_dir, folds, best_params, study, oos_df, yearly_rows, overall_summary)

    print("\nBest params")
    print(json.dumps(best_params, indent=2))
    print("\nFold Sharpe")
    print(json.dumps(selected_fold_sharpes, indent=2))
    print("\nWalk-forward summary")
    print(json.dumps(overall_summary, indent=2))
    print(f"\nSaved outputs to: {output_dir.resolve()}")


if __name__ == "__main__":
    main()

"""
Notebook-faithful Modern Portfolio Optimizer.

This mirrors the notebook's ModernPortfolioOptimizerPro:
- strategy equity returns as the optimizer input
- Ledoit-Wolf shrinkage covariance
- exponential weighting on expected returns
- tangent (max-Sharpe) portfolio
- analytical efficient frontier
- top-k stock selection with renormalized weights
"""

import logging

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

try:
    from sklearn.covariance import LedoitWolf
    _HAS_LW = True
except ImportError:
    _HAS_LW = False
    logger.warning("scikit-learn not available; falling back to sample covariance")


def _build_strategy_return_matrix(stock_equity_history: dict[str, list]) -> pd.DataFrame:
    dfs = []
    for symbol, history in (stock_equity_history or {}).items():
        if not history:
            continue

        df = pd.DataFrame(
            history,
            columns=["Date", "Price", "Equity", "StrategyRet", "StockRet"],
        )
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
        df = df.dropna(subset=["Date"]).sort_values("Date")
        df = df.groupby("Date", as_index=True).agg({"StrategyRet": "sum"})
        dfs.append(df.rename(columns={"StrategyRet": symbol}))

    if not dfs:
        raise ValueError("No valid strategy histories available.")

    merged = pd.concat(dfs, axis=1, join="outer").fillna(0.0).astype(float)
    var = merged.var(axis=0)
    keep = var[var > 1e-12].index
    merged = merged[keep]

    if merged.shape[1] == 0:
        raise ValueError("All strategy series have near-zero variance.")

    return merged


def _compute_statistics(
    returns_df: pd.DataFrame,
    annualize: bool = True,
    ridge_alpha: float = 1e-5,
    winsorize: bool = True,
) -> tuple[np.ndarray, np.ndarray]:
    data = returns_df.copy()

    if winsorize:
        data = data.clip(
            lower=data.quantile(0.01),
            upper=data.quantile(0.99),
            axis=1,
        )

    weights = np.exp(np.linspace(-1, 0, len(data)))
    weights /= weights.sum()
    mean_returns = np.asarray((data * weights[:, None]).sum(axis=0).values, dtype=float).copy()

    if _HAS_LW:
        lw = LedoitWolf().fit(data.values)
        cov_matrix = lw.covariance_
    else:
        cov_matrix = np.cov(data.values, rowvar=False)

    if annualize:
        mean_returns *= 252
        cov_matrix *= 252

    ridge = ridge_alpha * np.trace(cov_matrix) / len(cov_matrix)
    cov_matrix += ridge * np.eye(len(cov_matrix))

    return mean_returns, cov_matrix


def _portfolio_metrics(
    weights: np.ndarray,
    mean_returns: np.ndarray,
    cov_matrix: np.ndarray,
    risk_free_rate: float,
) -> tuple[float, float, float]:
    ret = float(mean_returns @ weights)
    vol = float(np.sqrt(weights @ cov_matrix @ weights))
    sharpe = (ret - risk_free_rate) / vol if vol > 0 else 0.0
    return ret, vol, sharpe


def _tangent_portfolio(
    mean_returns: np.ndarray,
    cov_matrix: np.ndarray,
    risk_free_rate: float = 0.0,
    long_only: bool = True,
    lambda_reg: float = 1e-3,
) -> np.ndarray:
    sigma = cov_matrix + lambda_reg * np.eye(len(cov_matrix))
    mu_excess = mean_returns - risk_free_rate

    inv_sigma = np.linalg.pinv(sigma)
    weights = inv_sigma @ mu_excess

    if long_only:
        weights = np.maximum(weights, 0.0)

    if weights.sum() <= 1e-12:
        return np.ones(len(weights)) / len(weights)

    return weights / weights.sum()


def _efficient_frontier(
    mean_returns: np.ndarray,
    cov_matrix: np.ndarray,
    risk_free_rate: float = 0.0,
    num_points: int = 30,
) -> pd.DataFrame:
    inv_sigma = np.linalg.pinv(cov_matrix)
    ones = np.ones(len(mean_returns))

    a = ones @ inv_sigma @ ones
    b = ones @ inv_sigma @ mean_returns
    c = mean_returns @ inv_sigma @ mean_returns
    d = a * c - b ** 2

    target_returns = np.linspace(mean_returns.min(), mean_returns.max(), num_points)
    frontier = []

    for target in target_returns:
        weights = inv_sigma @ ((c - b * target) * ones + (a * target - b) * mean_returns) / d
        weights = np.maximum(weights, 0.0)
        if weights.sum() <= 1e-12:
            continue
        weights /= weights.sum()

        ret, vol, sharpe = _portfolio_metrics(weights, mean_returns, cov_matrix, risk_free_rate)
        frontier.append({
            "volatility": round(vol * 100, 2),
            "return": round(ret * 100, 2),
            "sharpe": round(sharpe, 3),
        })

    return pd.DataFrame(frontier)


def optimize_portfolio(
    stock_equity_history: dict[str, list],
    risk_free: float = 0.0,
    top_k: int = 6,
    weight_threshold: float = 0.05,
) -> dict:
    """
    Optimize allocations from notebook-style stock_equity_history.

    Expected input per symbol:
    [(date, price, equity, strategy_logreturn, stock_logreturn), ...]
    """
    try:
        returns_df = _build_strategy_return_matrix(stock_equity_history)
    except ValueError as exc:
        logger.warning(f"Optimizer fallback to equal weights: {exc}")
        tickers = list((stock_equity_history or {}).keys())
        if not tickers:
            return {
                "allocations": {},
                "selected_tickers": [],
                "frontier": [],
                "portfolio_metrics": {},
                "individual_metrics": {},
                "risk_contribution": [],
                "corr_to_port": {},
            }
        equal = round(1 / len(tickers), 4)
        return {
            "allocations": {t: equal for t in tickers},
            "selected_tickers": tickers,
            "frontier": [],
            "portfolio_metrics": {},
            "individual_metrics": {},
            "risk_contribution": [],
            "corr_to_port": {},
        }

    mean_returns, cov_matrix = _compute_statistics(returns_df)
    symbols = list(returns_df.columns)

    raw_weights = _tangent_portfolio(mean_returns, cov_matrix, risk_free_rate=risk_free, long_only=True)
    raw_df = (
        pd.DataFrame({"Stock": symbols, "Weight": raw_weights})
        .sort_values("Weight", ascending=False)
        .reset_index(drop=True)
    )

    if top_k and top_k > 0:
        selected_df = raw_df.iloc[:top_k].copy()
    else:
        selected_df = raw_df[raw_df["Weight"].abs() > weight_threshold].copy()

    total = float(selected_df["Weight"].sum())
    if total <= 1e-12:
        selected_df = raw_df.iloc[: min(6, len(raw_df))].copy()
        total = float(selected_df["Weight"].sum())

    selected_df["Weight"] = (selected_df["Weight"] / total).round(4)
    selected_tickers = selected_df["Stock"].tolist()
    allocations = dict(zip(selected_df["Stock"], selected_df["Weight"]))

    full_weight_map = {s: raw_weights[i] for i, s in enumerate(symbols)}
    selected_weights = np.array([allocations[s] for s in selected_tickers], dtype=float)
    selected_mu = np.array([mean_returns[symbols.index(s)] for s in selected_tickers], dtype=float)
    selected_idx = [symbols.index(s) for s in selected_tickers]
    selected_cov = cov_matrix[np.ix_(selected_idx, selected_idx)]
    selected_returns = returns_df[selected_tickers].copy()

    frontier_df = _efficient_frontier(mean_returns, cov_matrix, risk_free_rate=risk_free, num_points=30)
    port_ret, port_vol, port_sharpe = _portfolio_metrics(
        selected_weights,
        selected_mu,
        selected_cov,
        risk_free,
    )

    port_var = selected_weights @ selected_cov @ selected_weights
    if port_var > 1e-12:
        mrc = ((selected_cov @ selected_weights) * selected_weights / port_var)
        mrc = mrc / mrc.sum() * 100
    else:
        mrc = np.ones(len(selected_tickers)) / len(selected_tickers) * 100

    individual_metrics = {}
    corr_to_port = {}
    port_series = returns_df[selected_tickers] @ selected_weights
    for symbol in symbols:
        idx = symbols.index(symbol)
        individual_metrics[symbol] = {
            "return": round(float(mean_returns[idx]) * 100, 2),
            "volatility": round(float(np.sqrt(cov_matrix[idx, idx])) * 100, 2),
        }
        corr = np.corrcoef(returns_df[symbol].values, port_series.values)[0, 1]
        corr_to_port[symbol] = round(float(corr), 3) if np.isfinite(corr) else 0.0

    corr_matrix = selected_returns.corr().fillna(0.0)
    corr_matrix_records = []
    for row_ticker in selected_tickers:
        for col_ticker in selected_tickers:
            corr_matrix_records.append({
                "row": row_ticker,
                "col": col_ticker,
                "corr": round(float(corr_matrix.loc[row_ticker, col_ticker]), 3),
            })

    return {
        "allocations": allocations,
        "selected_tickers": selected_tickers,
        "frontier": frontier_df.to_dict("records"),
        "risk_contribution": [
            {"ticker": selected_tickers[i], "risk": round(float(mrc[i]), 1)}
            for i in range(len(selected_tickers))
        ],
        "portfolio_metrics": {
            "return": round(port_ret * 100, 2),
            "volatility": round(port_vol * 100, 2),
            "sharpe": round(port_sharpe, 3),
        },
        "individual_metrics": individual_metrics,
        "corr_to_port": corr_to_port,
        "corr_matrix": corr_matrix_records,
        "raw_weights": {s: round(float(full_weight_map[s]), 4) for s in symbols},
    }

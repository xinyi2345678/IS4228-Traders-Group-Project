# TradeX: A Regime-Adaptive Quantitative Trading System

### Done by: Traders

| **Group Members**  | **Admin No.** |
| ------------------ | ------------- |
| Cao Thi Ha Phuong  | A0266282Y     |
| Ho Xin Yi          | A0281754X     |
| Koh Swee Hong      | A0273207J     |
| Lauren Dana Ho Min | A0278037X     |
| To Bao Chau        | A0276224E     |
| Yee Ting Hwei      | A0257085X     |

A full-stack quantitative trading dashboard for the top 10 large-cap U.S. stocks.

**Backend:** Python Flask API running a MACD + Bollinger Bands + ATR strategy, Modern Portfolio Theory optimisation, and GPT-powered AI explanations.

**Frontend:** React 19 + Vite dashboard with four pages: Dashboard, Portfolio, Monitoring, and AI Insights.

---

## Quick Start

### Prerequisites

| Requirement | Version |
| ----------- | ------- |
| Python      | 3.11+   |
| Node.js     | 18+     |
| npm         | 9+      |

---

### 1. Clone & install dependencies

#### macOS User:

```bash
# Frontend dependencies
npm install

# Python virtual environment (already created)
# Activate and install backend dependencies
source .venv/bin/activate
python -m pip install flask flask-cors scipy scikit-learn ta openai python-dotenv yfinance numpy pandas
```
#### Windows User:
```bash
# Frontend dependencies
npm install

# Python virtual environment (already created)
# Activate and install backend dependencies
python -m venv .venv
python -m pip install flask flask-cors scipy scikit-learn ta openai python-dotenv yfinance numpy pandas
```

---

### 2. Set up environment variables

Copy the `.env.example` file to `.env` in the project root:

```bash
cp .env.example .env
```
Alternatively, create a `.env` file in the project root:
```
OPENAI_API='your-openai-api-key-here'
OPENAI_MODEL='gpt-4o-mini'
VITE_OPENAI_MODEL='gpt-4o-mini'
VITE_API_BASE_URL='http://localhost:5001/api'
FRONTEND_ORIGIN='http://localhost:5173'
```

> The AI features (trade explanations, market summary, chat) use **GPT-4o-mini** via the OpenAI API.
> All other features (strategy, portfolio optimisation, metrics) work without an API key.

---

### 3. Run the backend

#### macOS User:
```bash
# From the project root
PORT=5001 .venv/bin/python backend/app.py
```

#### Windows User:
```bash
# From the project root
$env:PORT=5001 
python backend\app.py
```

On first start the backend will:

1. Download ~5 years of daily price data for all 10 tickers from Yahoo Finance (~15–30 s)
2. Compute MACD, Bollinger Bands, and ATR indicators
3. Run the bar-by-bar strategy simulation
4. Optimise portfolio weights using Modern Portfolio Theory
5. Compute all performance metrics

Once you see `=== Data ready ===` in the terminal, the API is serving on `http://localhost:5001`.

**Check status:**

```bash
curl http://localhost:5001/api/status
# → {"status":"ready", ...}
```

---

### 4. Run the frontend

Open a **second terminal**:

#### Both macOS and Windows Users:
```bash
npm run dev
```

Frontend starts at `http://localhost:5173`. Vite automatically proxies all `/api/*` calls to the Flask backend.

---

### 5. Open the dashboard

Navigate to **http://localhost:5173** in your browser.

> If the backend is still loading data, the frontend will display synthetic placeholder data and switch to live data automatically once the backend is ready.

---

## Project Structure

```
.
├── backend/
│   ├── app.py            # Flask API server (all routes)
│   ├── trading.py        # MACD-BB-ATR strategy + simulation engine
│   ├── optimizer.py      # MPT portfolio optimiser (Ledoit-Wolf + tangent portfolio)
│   ├── performance.py    # Performance metrics (Sharpe, drawdown, CAGR, etc.)
│   └── ai_service.py     # GPT-powered trade explanations, summary, chat
│
├── src/
│   ├── services/
│   │   └── api.js        # Frontend API client (fetches from /api/*)
│   ├── pages/
│   │   ├── Dashboard.jsx   # Overview: KPIs, equity curve, signals, alerts
│   │   ├── Portfolio.jsx   # Allocation, efficient frontier, risk contribution
│   │   ├── Monitoring.jsx  # Live positions, signal feed, drawdown, exposure
│   │   └── AIInsights.jsx  # Trade explainer, market summary, risk alerts, chat
│   ├── components/
│   │   ├── Layout.jsx      # Sidebar + top bar shell
│   │   ├── KPICard.jsx     # Metric card with sparkline
│   │   └── SignalBadge.jsx # LONG / SHORT / EXIT badge
│   └── data/
│       └── synthetic.js    # Fallback placeholder data (used when backend is offline)
│
├── .env                  # OPENAI_API key (not committed)
├── vite.config.js        # Vite config with /api proxy → localhost:5001
└── package.json
```

---

## API Endpoints

| Method | Path              | Description                                                |
| ------ | ----------------- | ---------------------------------------------------------- |
| GET    | `/api/status`     | Backend load state: `loading` / `ready` / `error`          |
| GET    | `/api/dashboard`  | All data for the Dashboard page                            |
| GET    | `/api/portfolio`  | Portfolio allocation, efficient frontier, sector breakdown |
| GET    | `/api/monitoring` | Positions, signals, KPIs, drawdown, sector exposure        |
| GET    | `/api/alerts`     | AI-generated risk alerts                                   |
| POST   | `/api/ai/explain` | Explain a trading signal (GPT)                             |
| POST   | `/api/ai/summary` | Generate market summary (GPT)                              |
| POST   | `/api/ai/chat`    | Chat with AI assistant (GPT)                               |
| POST   | `/api/refresh`    | Re-run the backtest and reload all data                    |

---

## Trading Strategy

The strategy implements four entry mechanisms and two exit mechanisms:

| Code   | Name            | Condition                                                         |
| ------ | --------------- | ----------------------------------------------------------------- |
| **LM** | Long Momentum   | `0 ≤ MACD_hist ≤ Z_mid` AND `price > BB_mid`                     |
| **SM** | Short Momentum  | `−Z_mid ≤ MACD_hist < 0` AND `price < BB_mid`                    |
| **LR** | Long Reversion  | `MACD_hist < −Z_extreme` AND `price < BB_lower`                   |
| **SR** | Short Reversion | `MACD_hist > Z_extreme` AND `price > BB_upper`                    |
| **SL** | Stop-Loss       | Exit triggered when price hits ATR-scaled stop-loss level         |
| **TP** | Take-Profit     | Exit triggered when price hits ATR-scaled take-profit target      |

Exits are ATR-scaled stop-loss / take-profit with optional trailing stops and a time-based exit.
`Z_extreme` and `Z_mid` are dynamically scaled using **Robust MAD** of the MACD histogram.

**Universe:** AAPL, AMZN, META, GOOG, GOOGL, NVDA, MSFT, AVGO, TSLA, BRK-B
**Benchmark:** SPY (buy-and-hold)

---

## Portfolio Optimisation

Uses **Modern Portfolio Theory** (Ledoit-Wolf shrinkage covariance + analytical tangent portfolio) to find the max-Sharpe allocation. The efficient frontier is computed with `scipy` SLSQP.

---

## Tech Stack

| Layer                  | Technology                         |
| ---------------------- | ---------------------------------- |
| Frontend framework     | React 19 + Vite 8                  |
| Styling                | Tailwind CSS v4                    |
| Charts                 | Recharts v3                        |
| Icons                  | Lucide React                       |
| Routing                | React Router v7                    |
| Backend framework      | Flask 3 + flask-cors               |
| Market data            | yfinance                           |
| Technical indicators   | ta (TA-Lib wrapper)                |
| Portfolio optimisation | scipy + scikit-learn (Ledoit-Wolf) |
| AI features            | OpenAI GPT-4o-mini                 |

---

## System Components

The trading system has 4 core components, each mapped to specific pages and sections in the dashboard:

| Component | Description | Primary Page | Also Appears On |
| --------- | ----------- | ------------ | --------------- |
| Algorithmic Trading Strategies | Generates buy/sell signals using MACD, Bollinger Bands, and ATR. Implements 4 mechanisms: Long Momentum (LM), Short Momentum (SM), Long Reversion (LR), Short Reversion (SR). | /monitoring | / (signals table) |
| Portfolio Optimization | Allocates capital across stocks using Modern Portfolio Theory to maximize Sharpe ratio. Outputs target weights, efficient frontier, risk contributions. | /portfolio | / (KPIs, donut chart) |
| Real-Time Monitoring | Tracks live portfolio performance: P&L, equity curve, volatility, drawdowns, sector exposure. | /monitoring | / (equity curve, KPIs) |
| AI-Assisted Explanations | Uses GPT to explain trades, summarize markets, generate risk alerts, and answer questions via chat. | /ai-insights | / (alerts feed) |

> **Important distinction:** Algorithmic Trading decides *when* to buy/sell (signal generation). Portfolio Optimization decides *how much* to allocate (weight distribution). These are separate components that interact: the optimizer sets target weights, while the trading strategy generates entry/exit signals within those allocations.

---

## Page Details

### 1. Dashboard Overview (`/`)

| Section | Component | Data |
| ------- | --------- | ---- |
| KPI: Total Portfolio Value | Portfolio Optimization | `portfolioValue` |
| KPI: Day P&L | Real-Time Monitoring | `dayPnL`, `dayPnLPercent` |
| KPI: Sharpe Ratio | Portfolio Optimization | `sharpeRatio` |
| KPI: Active Positions | Algorithmic Trading | `positions.long`, `positions.short` |
| Equity Curve | Real-Time Monitoring | `equityCurve[]`: `{ date, portfolio, benchmark, drawdown }` |
| Portfolio Donut | Portfolio Optimization | `stocks[]`: `{ ticker, weight }` |
| Recent Signals | Algorithmic Trading | `signals[]`: `{ time, ticker, action, type, strength }` |
| AI Alerts | AI-Assisted Explanations | `alerts[]`: `{ severity, time, title, message }` |

### 2. Portfolio Distribution (`/portfolio`)

| Section | Data |
| ------- | ---- |
| Allocation Treemap | `stocks[]`: `{ ticker, weight, sector }` |
| Efficient Frontier | `efficientFrontier[]`: `{ volatility, return }`, `individualStocks[]`, `currentPortfolio` |
| Optimization Summary | `sharpeRatio`, expected return %, portfolio vol %, max drawdown % |
| Allocation Table | `stocks[]`: all fields |
| Sector Breakdown | `sectorBreakdown[]`: `{ name, value, color }` |
| Risk Contribution | `riskContribution[]`: `{ ticker, risk }` (sums to 100%) |

### 3. Live Monitoring (`/monitoring`)

| Section | Component | Data |
| ------- | --------- | ---- |
| KPI: Unrealized P&L | Monitoring | `monitoringKPIs.unrealizedPnL` |
| KPI: Realized P&L | Monitoring | `monitoringKPIs.realizedPnL` |
| KPI: Win Rate | Monitoring | `monitoringKPIs.winRate` |
| KPI: Net Exposure | Monitoring | `monitoringKPIs.netExposure` |
| Signal Feed | Trading | `signals[]`: `{ time, ticker, action, type, strength, detail }` |
| Position Tracker | Trading + Monitoring | `activePositions[]`: `{ ticker, direction, entry, current, pnl, sl, tp }` |
| Equity Curve (Live) | Monitoring | `intradayEquity[]`: `{ time, value }` |
| Volatility Monitor | Monitoring | `volatilityMetrics`: `{ atr, vix, portfolioVol }` |
| Drawdown Tracker | Monitoring | `drawdownMetrics`: `{ current, maxToday, maxEver }` |
| Sector Exposure | Both | `sectorExposure[]`: `{ sector, exposure }` |

### 4. AI-Assisted Insights (`/ai-insights`)

| Section | Tab | Data |
| ------- | --- | ---- |
| Trade Selector | Trade Explainer | Recent signals as dropdown options |
| AI Explanation Card | Trade Explainer | `{ action, ticker, time, strategy, why[], risk, confidence }` |
| Trade History | Trade Explainer | `signals[]` with `.detail` field |
| AI Market Summary | Market Summary | GPT-generated paragraph |
| Stock Heatmap | Market Summary | Active tickers from signals |
| Risk Alerts | Risk Alerts | `alerts[]`: `{ severity, time, title, message, recommendation }` |
| AI Chat Panel | (floating) | Conversation history, GPT integration |

---

## Troubleshooting

**Port 5000 already in use (macOS)**
macOS AirPlay Receiver uses port 5000. Use `PORT=5001` as shown above, or disable AirPlay Receiver in System Settings → General → AirDrop & Handoff.

**Backend stuck on "loading"**
Check logs in the backend terminal. Yahoo Finance rate-limits may slow data downloads. Wait 30 - 60 seconds.

**AI features return template responses**
Ensure `.env` contains a valid `OPENAI_API` key. The key is loaded automatically at backend startup.

**Frontend shows synthetic data**
The frontend falls back to `src/data/synthetic.js` if the backend is unreachable. Start the Flask server first, then hard-refresh the browser.

// =============================================================================
// SYNTHETIC / PLACEHOLDER DATA - DATA SCHEMA REFERENCE
// =============================================================================
//
// This file defines the data shapes that each UI component expects.
// All values here are PLACEHOLDER examples. Replace with real data from your
// backend (API calls, WebSocket feeds, etc.) when integrating.
//
// Each export is annotated with:
//   - Which SYSTEM COMPONENT it belongs to
//   - Which PAGE(s) consume it
//   - What backend source should provide it
//   - The expected data shape / field descriptions
// =============================================================================


// -----------------------------------------------------------------------------
// COMPONENT: Portfolio Optimization
// USED BY:   Dashboard (KPI cards), Portfolio page
// SOURCE:    Portfolio optimizer output / account balance API
// -----------------------------------------------------------------------------
// {number} Total portfolio value in USD (sum of all position values + cash)
export const portfolioValue = 1245300;

// -----------------------------------------------------------------------------
// COMPONENT: Real-Time Monitoring
// USED BY:   Dashboard (KPI cards)
// SOURCE:    Real-time P&L calculation engine
// -----------------------------------------------------------------------------
// {number} Today's profit/loss in USD (realized + unrealized)
export const dayPnL = 12450;
// {number} Today's P&L as a percentage of portfolio value
export const dayPnLPercent = 1.01;
// {number} Month-to-date return percentage
export const mtdPercent = 4.2;
// {number} Total return since strategy start
export const totalReturn = 24.53;

// -----------------------------------------------------------------------------
// COMPONENT: Portfolio Optimization
// USED BY:   Dashboard (KPI cards), Portfolio page (optimization summary)
// SOURCE:    Portfolio optimizer - calculated from historical returns
// -----------------------------------------------------------------------------
// {number} Portfolio Sharpe ratio (risk-adjusted return metric)
export const sharpeRatio = 1.84;
// {string} 'up' | 'down' - Sharpe trend direction vs previous period
export const sharpeTrend = 'up';

// -----------------------------------------------------------------------------
// COMPONENT: Algorithmic Trading Strategies
// USED BY:   Dashboard (KPI cards), Monitoring page
// SOURCE:    Strategy engine - count of currently open positions
// -----------------------------------------------------------------------------
// {object} Count of active long and short positions
// - long: {number} number of long positions currently held
// - short: {number} number of short positions currently held
export const positions = {
  long: 7,
  short: 3,
};

// -----------------------------------------------------------------------------
// COMPONENT: Portfolio Optimization
// USED BY:   Dashboard (donut chart), Portfolio page (treemap, table, detail modal)
// SOURCE:    Portfolio optimizer output + market data API for live prices
// -----------------------------------------------------------------------------
// Array of stock objects. Each stock represents one holding in the portfolio.
// Fields per stock:
//   - ticker:      {string}  Stock symbol (e.g., 'AAPL')
//   - name:        {string}  Full company name
//   - weight:      {number}  Portfolio weight as % (from optimizer)
//   - value:       {number}  Dollar value of holding (weight * portfolio_value)
//   - sector:      {string}  Market sector classification
//   - shares:      {number}  Number of shares held
//   - price:       {number}  Current market price per share (from market data feed)
//   - change:      {number}  Today's price change in % (from market data feed)
//   - beta:        {number}  Stock beta vs market (from historical calc)
//   - annReturn:   {number}  Annualized return % (from historical calc)
//   - volatility:  {number}  Annualized volatility % (from historical calc)
//   - corrToPort:  {number}  Correlation to overall portfolio (from optimizer)
export const stocks = [
  { ticker: 'AAPL', name: 'Apple Inc.', weight: 18.2, value: 227125, sector: 'Technology', shares: 1240, price: 183.42, change: 1.4, beta: 1.12, annReturn: 24.3, volatility: 18.1, corrToPort: 0.78 },
  { ticker: 'MSFT', name: 'Microsoft Corp.', weight: 15.4, value: 191777, sector: 'Technology', shares: 456, price: 420.59, change: 0.8, beta: 1.05, annReturn: 21.7, volatility: 16.3, corrToPort: 0.82 },
  { ticker: 'NVDA', name: 'NVIDIA Corp.', weight: 14.1, value: 175588, sector: 'Technology', shares: 195, price: 900.45, change: 2.1, beta: 1.45, annReturn: 38.2, volatility: 28.4, corrToPort: 0.71 },
  { ticker: 'GOOGL', name: 'Alphabet Inc.', weight: 12.0, value: 149436, sector: 'Communication', shares: 860, price: 173.77, change: 0.5, beta: 1.08, annReturn: 18.9, volatility: 19.2, corrToPort: 0.76 },
  { ticker: 'AMZN', name: 'Amazon.com Inc.', weight: 11.3, value: 140719, sector: 'Consumer', shares: 720, price: 195.44, change: 0.9, beta: 1.18, annReturn: 22.1, volatility: 21.5, corrToPort: 0.74 },
  { ticker: 'META', name: 'Meta Platforms', weight: 9.5, value: 118303, sector: 'Communication', shares: 220, price: 537.74, change: -0.3, beta: 1.25, annReturn: 28.4, volatility: 24.8, corrToPort: 0.68 },
  { ticker: 'TSLA', name: 'Tesla Inc.', weight: 7.2, value: 89662, sector: 'Consumer', shares: 380, price: 235.95, change: -1.2, beta: 1.82, annReturn: 15.6, volatility: 42.1, corrToPort: 0.52 },
  { ticker: 'BRK.B', name: 'Berkshire Hathaway', weight: 5.8, value: 72227, sector: 'Financial', shares: 160, price: 451.42, change: 0.2, beta: 0.65, annReturn: 12.3, volatility: 12.8, corrToPort: 0.58 },
  { ticker: 'JPM', name: 'JPMorgan Chase', weight: 3.8, value: 47321, sector: 'Financial', shares: 230, price: 205.74, change: -0.4, beta: 0.95, annReturn: 14.8, volatility: 17.6, corrToPort: 0.62 },
  { ticker: 'UNH', name: 'UnitedHealth Group', weight: 2.7, value: 33623, sector: 'Healthcare', shares: 55, price: 611.33, change: 0.1, beta: 0.72, annReturn: 16.2, volatility: 15.4, corrToPort: 0.48 },
];

// -----------------------------------------------------------------------------
// COMPONENT: Portfolio Optimization
// USED BY:   Portfolio page (sector pie chart)
// SOURCE:    Derived from stocks[] - aggregate weights by sector
// -----------------------------------------------------------------------------
// Array of sectors with their total portfolio weight %
// Fields: name {string}, value {number} weight %, color {string} hex color for chart
export const sectorBreakdown = [
  { name: 'Technology', value: 47.7, color: '#58A6FF' },
  { name: 'Communication', value: 21.5, color: '#A371F7' },
  { name: 'Consumer', value: 18.5, color: '#3FB950' },
  { name: 'Financial', value: 9.6, color: '#D29922' },
  { name: 'Healthcare', value: 2.7, color: '#F85149' },
];

// -----------------------------------------------------------------------------
// COMPONENT: Portfolio Optimization
// USED BY:   Portfolio page (risk contribution bar chart)
// SOURCE:    Portfolio optimizer - marginal risk contribution per stock
// -----------------------------------------------------------------------------
// Each stock's % contribution to total portfolio risk (should sum to 100)
// Fields: ticker {string}, risk {number} risk contribution %
export const riskContribution = [
  { ticker: 'NVDA', risk: 22 },
  { ticker: 'TSLA', risk: 18 },
  { ticker: 'META', risk: 15 },
  { ticker: 'AAPL', risk: 12 },
  { ticker: 'AMZN', risk: 10 },
  { ticker: 'GOOGL', risk: 8 },
  { ticker: 'MSFT', risk: 7 },
  { ticker: 'JPM', risk: 4 },
  { ticker: 'BRK.B', risk: 3 },
  { ticker: 'UNH', risk: 1 },
];

// -----------------------------------------------------------------------------
// COMPONENT: Real-Time Monitoring + Portfolio Optimization
// USED BY:   Dashboard (equity curve chart)
// SOURCE:    Historical portfolio tracker - daily snapshots
// -----------------------------------------------------------------------------
// Time-series array of daily portfolio value vs benchmark.
// Fields per point:
//   - date:       {string}  Display label (e.g., 'Mar 15')
//   - portfolio:  {number}  Portfolio value in USD on that date
//   - benchmark:  {number}  Benchmark (SPY) value in USD on that date
//   - drawdown:   {number}  Drawdown % from peak (negative number, 0 = no drawdown)
export const equityCurve = (() => {
  const data = [];
  let portfolio = 1150000;
  let benchmark = 1150000;
  const now = Date.now();
  for (let i = 90; i >= 0; i--) {
    const date = new Date(now - i * 24 * 60 * 60 * 1000);
    portfolio += (Math.random() - 0.45) * 8000;
    benchmark += (Math.random() - 0.47) * 6000;
    const drawdown = Math.min(0, (portfolio - Math.max(...data.map(d => d.portfolio), portfolio)) / Math.max(...data.map(d => d.portfolio), portfolio) * 100);
    data.push({
      date: date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }),
      portfolio: Math.round(portfolio),
      benchmark: Math.round(benchmark),
      drawdown: Math.round(drawdown * 10) / 10,
    });
  }
  return data;
})();

// -----------------------------------------------------------------------------
// COMPONENT: Real-Time Monitoring
// USED BY:   Monitoring page (live equity curve)
// SOURCE:    Real-time portfolio tracker - intraday snapshots (e.g., every 5 min)
// -----------------------------------------------------------------------------
// Intraday time-series of portfolio value during current trading day.
// Fields: time {string} 'HH:MM' format, value {number} portfolio value in USD
export const intradayEquity = (() => {
  const data = [];
  let value = 1238000;
  for (let h = 9; h <= 15; h++) {
    for (let m = h === 9 ? 30 : 0; m < 60; m += 5) {
      value += (Math.random() - 0.45) * 1200;
      data.push({
        time: `${h}:${m.toString().padStart(2, '0')}`,
        value: Math.round(value),
      });
    }
  }
  return data;
})();

// -----------------------------------------------------------------------------
// COMPONENT: Algorithmic Trading Strategies
// USED BY:   Dashboard (recent signals table), Monitoring (signal feed), AI Insights (trade history)
// SOURCE:    Strategy engine - emitted each time a signal is generated
// -----------------------------------------------------------------------------
// Array of trading signals in reverse chronological order.
// Fields per signal:
//   - time:      {string}  Signal timestamp ('HH:MM' format)
//   - ticker:    {string}  Stock symbol
//   - action:    {string}  'LONG' | 'SHORT' | 'EXIT' - the trading action
//   - type:      {string}  Strategy type code:
//                            'LM' = Long Momentum
//                            'SM' = Short Momentum
//                            'LR' = Long Reversion
//                            'SR' = Short Reversion
//                            'SL' = Stop-Loss exit
//                            'TP' = Take-Profit exit
//   - strength:  {number|null}  Signal confidence 0-1 (null for EXIT signals)
//   - detail:    {string}  Human-readable description of why signal was generated
//                           (used by AI module for explanations)
export const signals = [
  { time: '10:32', ticker: 'AAPL', action: 'LONG', type: 'LM', strength: 0.82, detail: 'Long Momentum - MACD crossover with expanding histogram. Price above mid Bollinger Band at 62% position. ATR normal at 3.21.' },
  { time: '10:15', ticker: 'TSLA', action: 'EXIT', type: 'SL', strength: null, detail: 'Stop-loss triggered after sudden reversal. Volatility spike invalidated entry thesis.' },
  { time: '09:45', ticker: 'META', action: 'SHORT', type: 'SR', strength: 0.65, detail: 'Short Reversion - Price at upper Bollinger Band (2.1 std dev). Declining MACD histogram signals overbought reversal.' },
  { time: '09:31', ticker: 'MSFT', action: 'LONG', type: 'LR', strength: 0.71, detail: 'Long Reversion - Price bounced from lower Bollinger Band. MACD histogram turning positive from oversold.' },
  { time: '09:30', ticker: 'NVDA', action: 'LONG', type: 'LM', strength: 0.91, detail: 'Long Momentum - Strong bullish MACD cross at open. Price breaking above 20-day high with below-average ATR.' },
  { time: '09:15', ticker: 'AMZN', action: 'EXIT', type: 'TP', strength: null, detail: 'Take-profit target reached at +4.8%. Position closed with realized gain of $6,720.' },
  { time: '09:01', ticker: 'JPM', action: 'SHORT', type: 'SM', strength: 0.54, detail: 'Short Momentum - MACD crossed below signal line. Price broke below mid Bollinger Band with rising ATR.' },
  { time: '08:45', ticker: 'GOOGL', action: 'LONG', type: 'LM', strength: 0.77, detail: 'Long Momentum - Sustained move above 20-day MA with MACD confirmation.' },
  { time: '08:30', ticker: 'BRK.B', action: 'LONG', type: 'LR', strength: 0.63, detail: 'Long Reversion - Price at lower Bollinger Band, RSI oversold territory.' },
  { time: '08:15', ticker: 'UNH', action: 'LONG', type: 'LM', strength: 0.58, detail: 'Long Momentum - Gentle uptrend confirmed by MACD and volume increase.' },
];

// -----------------------------------------------------------------------------
// COMPONENT: Algorithmic Trading Strategies + Real-Time Monitoring
// USED BY:   Monitoring page (position tracker cards)
// SOURCE:    Strategy engine / order management system - current open positions
// -----------------------------------------------------------------------------
// Array of currently active positions.
// Fields per position:
//   - ticker:      {string}  Stock symbol
//   - direction:   {string}  'LONG' | 'SHORT'
//   - entry:       {number}  Entry price in USD
//   - current:     {number}  Current market price in USD (live feed)
//   - pnl:         {number}  Unrealized P&L in USD
//   - pnlPercent:  {number}  Unrealized P&L as %
//   - sl:          {number}  Stop-loss price level
//   - tp:          {number}  Take-profit price level
export const activePositions = [
  { ticker: 'AAPL', direction: 'LONG', entry: 183.42, current: 184.10, pnl: 842, pnlPercent: 0.37, sl: 177.80, tp: 192.60 },
  { ticker: 'MSFT', direction: 'LONG', entry: 418.20, current: 420.59, pnl: 1090, pnlPercent: 0.57, sl: 405.40, tp: 438.60 },
  { ticker: 'NVDA', direction: 'LONG', entry: 892.10, current: 900.45, pnl: 1627, pnlPercent: 0.94, sl: 865.00, tp: 946.20 },
  { ticker: 'GOOGL', direction: 'LONG', entry: 172.50, current: 173.77, pnl: 1092, pnlPercent: 0.74, sl: 167.30, tp: 181.10 },
  { ticker: 'AMZN', direction: 'LONG', entry: 193.80, current: 195.44, pnl: 1181, pnlPercent: 0.85, sl: 187.90, tp: 203.50 },
  { ticker: 'BRK.B', direction: 'LONG', entry: 449.80, current: 451.42, pnl: 259, pnlPercent: 0.36, sl: 436.00, tp: 472.30 },
  { ticker: 'UNH', direction: 'LONG', entry: 609.50, current: 611.33, pnl: 101, pnlPercent: 0.30, sl: 591.20, tp: 640.00 },
  { ticker: 'META', direction: 'SHORT', entry: 542.30, current: 537.74, pnl: 1003, pnlPercent: 0.84, sl: 558.80, tp: 515.40 },
  { ticker: 'TSLA', direction: 'SHORT', entry: 241.20, current: 235.95, pnl: 1995, pnlPercent: 2.18, sl: 248.40, tp: 221.80 },
  { ticker: 'JPM', direction: 'SHORT', entry: 208.10, current: 205.74, pnl: 543, pnlPercent: 1.13, sl: 214.30, tp: 197.50 },
];

// -----------------------------------------------------------------------------
// COMPONENT: AI-Assisted Explanations
// USED BY:   Dashboard (alerts feed), AI Insights page (risk alerts tab)
// SOURCE:    AI module - generated when risk conditions change
// -----------------------------------------------------------------------------
// Array of AI-generated alerts in reverse chronological order.
// Fields per alert:
//   - severity:        {string}  'critical' | 'warning' | 'info'
//   - time:            {string}  When the alert was generated
//   - title:           {string}  Short alert headline
//   - message:         {string}  Detailed AI-generated explanation
//   - recommendation:  {string|null}  AI's suggested action (null if none)
export const alerts = [
  { severity: 'critical', time: '10:18 AM', title: 'VOLATILITY SPIKE', message: 'TSLA ATR has increased 2.1x above its 20-day average. Current ATR: 8.42 vs Avg: 4.01. System automatically reduced TSLA position size by 40% and tightened stop-loss from -3.5% to -2.0%.', recommendation: 'Monitor TSLA closely. Consider manual exit if ATR exceeds 10.0.' },
  { severity: 'warning', time: '09:55 AM', title: 'DRAWDOWN WARNING', message: 'Portfolio drawdown reached -3.2% from peak. This is approaching the -5% threshold. Contributing factors: TSLA short position moved against us (-1.8%), broad market dip at open (-0.6%).', recommendation: 'The system is maintaining current positions as indicators still support the thesis.' },
  { severity: 'info', time: '09:30 AM', title: 'REBALANCE SUGGESTION', message: 'Portfolio allocation has drifted >2% from optimal weights. NVDA: 14.1% -> 12.8% (overweight), JPM: 3.8% -> 5.1% (underweight).', recommendation: 'Consider running the optimizer to rebalance.' },
  { severity: 'info', time: '09:00 AM', title: 'STRATEGY STARTED', message: 'Regime-Adaptive strategy initialized. Current regime detected: TRENDING (Bullish). 10 stocks loaded, portfolio value: $1,245,300.', recommendation: null },
];

// -----------------------------------------------------------------------------
// COMPONENT: Portfolio Optimization
// USED BY:   Portfolio page (efficient frontier scatter chart)
// SOURCE:    Portfolio optimizer - simulated frontier from covariance matrix
// -----------------------------------------------------------------------------
// Array of points along the efficient frontier curve.
// Fields: volatility {number} annualized vol %, return {number} expected annual return %
export const efficientFrontier = (() => {
  const points = [];
  for (let i = 0; i < 30; i++) {
    const vol = 5 + i * 0.8;
    const ret = 2 + Math.sqrt(vol) * 2.8 - (vol > 20 ? (vol - 20) * 0.15 : 0);
    points.push({ volatility: Math.round(vol * 10) / 10, return: Math.round(ret * 10) / 10 });
  }
  return points;
})();

// -----------------------------------------------------------------------------
// COMPONENT: Portfolio Optimization
// USED BY:   Portfolio page (efficient frontier - individual stock dots)
// SOURCE:    Derived from stocks[] - annualized return and volatility per stock
// -----------------------------------------------------------------------------
export const individualStocks = stocks.map(s => ({
  ticker: s.ticker,
  volatility: s.volatility,
  return: s.annReturn,
}));

// -----------------------------------------------------------------------------
// COMPONENT: Portfolio Optimization
// USED BY:   Portfolio page (efficient frontier - current portfolio marker)
// SOURCE:    Portfolio optimizer - portfolio-level risk/return
// -----------------------------------------------------------------------------
// The current portfolio's position on the risk-return plane
// Fields: volatility {number} portfolio vol %, return {number} portfolio expected return %
export const currentPortfolio = { volatility: 8.2, return: 12.4 };

// -----------------------------------------------------------------------------
// COMPONENT: Real-Time Monitoring
// USED BY:   Monitoring page (KPI cards row)
// SOURCE:    Real-time P&L engine + trade log
// -----------------------------------------------------------------------------
// Intraday monitoring KPI metrics
// Fields:
//   - unrealizedPnL: {number} USD - P&L on positions still open
//   - realizedPnL:   {number} USD - P&L on positions closed today
//   - winRate:       {number} % - winning trades / total trades today
//   - netExposure:   {number} % - (long_value - short_value) / total_value * 100
export const monitoringKPIs = {
  unrealizedPnL: 8230,
  realizedPnL: 4220,
  winRate: 62.3,
  netExposure: 78,
};

// -----------------------------------------------------------------------------
// COMPONENT: Real-Time Monitoring
// USED BY:   Monitoring page (volatility monitor gauges)
// SOURCE:    Technical indicator engine + market data feed
// -----------------------------------------------------------------------------
// Current volatility readings
// Fields:
//   - atr:          {number} Average True Range (14-period) for portfolio
//   - vix:          {number} CBOE VIX index value (from market data)
//   - portfolioVol: {number} % - portfolio-level annualized volatility
export const volatilityMetrics = {
  atr: 2.34,
  vix: 18.2,
  portfolioVol: 12.1,
};

// -----------------------------------------------------------------------------
// COMPONENT: Real-Time Monitoring
// USED BY:   Monitoring page (drawdown tracker)
// SOURCE:    Portfolio tracker - peak-to-trough calculations
// -----------------------------------------------------------------------------
// Drawdown measurements (all negative percentages)
// Fields:
//   - current:  {number} current drawdown from recent peak
//   - maxToday: {number} worst drawdown seen today
//   - maxEver:  {number} worst drawdown since strategy inception
export const drawdownMetrics = {
  current: -1.2,
  maxToday: -2.8,
  maxEver: -6.1,
};

// -----------------------------------------------------------------------------
// COMPONENT: Real-Time Monitoring + Portfolio Optimization
// USED BY:   Monitoring page (sector exposure bar chart)
// SOURCE:    Derived from active positions - net long/short exposure per sector
// -----------------------------------------------------------------------------
// Net exposure per sector (positive = net long, negative = net short)
// Fields: sector {string}, exposure {number} net exposure %
export const sectorExposure = [
  { sector: 'Technology', exposure: 45 },
  { sector: 'Communication', exposure: 15 },
  { sector: 'Consumer', exposure: 12 },
  { sector: 'Financial', exposure: -8 },
  { sector: 'Healthcare', exposure: 0 },
];

// -----------------------------------------------------------------------------
// COMPONENT: Real-Time Monitoring
// USED BY:   Dashboard (KPI card sparklines)
// SOURCE:    Historical snapshots - recent data points for mini trend charts
// -----------------------------------------------------------------------------
// Recent data points for inline sparkline charts in KPI cards.
// Each array should contain ~12 recent values for the mini trend line.
// Fields:
//   - portfolio: {number[]} recent portfolio values (in thousands)
//   - pnl:       {number[]} recent daily P&L values (in thousands)
//   - sharpe:    {number[]} recent Sharpe ratio values
export const sparklines = {
  portfolio: [1180, 1190, 1195, 1200, 1210, 1215, 1225, 1230, 1228, 1235, 1240, 1245],
  pnl: [2, -1, 3, 5, 4, 8, 6, 10, 9, 11, 12, 12.45],
  sharpe: [1.6, 1.62, 1.65, 1.7, 1.72, 1.75, 1.78, 1.8, 1.79, 1.82, 1.83, 1.84],
};

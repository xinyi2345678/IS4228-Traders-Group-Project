// =============================================================================
// PAGE: DASHBOARD OVERVIEW (Landing Page)
// ROUTE: /
// =============================================================================
// This is the landing page. It provides a 30-second snapshot combining data
// from ALL FOUR system components:
//
//   1. PORTFOLIO OPTIMIZATION  -> KPI cards (portfolio value, Sharpe), donut chart
//   2. ALGORITHMIC TRADING     -> Recent signals table, active position counts
//   3. REAL-TIME MONITORING    -> Day P&L, equity curve, sparklines
//   4. AI-ASSISTED EXPLANATIONS-> AI alerts feed
//
// LAYOUT:
// +----------------------------------------------+
// | KPI ROW (4 cards)                            |  <- Row 1
// +----------------------------------------------+
// | EQUITY CURVE (2/3)      | PORTFOLIO DONUT    |  <- Row 2
// |                         | (1/3)              |
// +----------------------------------------------+
// | RECENT SIGNALS (1/2)    | AI ALERTS (1/2)    |  <- Row 3
// +----------------------------------------------+
// =============================================================================

import { useState, useEffect } from 'react';
import KPICard from '../components/KPICard';
import SignalBadge from '../components/SignalBadge';
import * as synthetic from '../data/synthetic';
import { fetchDashboard, fetchStatus, refreshData } from '../services/api';

import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Area, ComposedChart, Legend,
} from 'recharts';
import { TrendingUp, AlertTriangle, Info, RefreshCw } from 'lucide-react';

const COLORS = ['#58A6FF', '#A371F7', '#3FB950', '#D29922', '#F85149', '#8B949E', '#F778BA', '#79C0FF', '#D2A8FF', '#FFA657'];

const alertIcons = {
  critical: <AlertTriangle size={16} className="text-loss" />,
  warning: <AlertTriangle size={16} className="text-warning" />,
  info: <Info size={16} className="text-accent" />,
};

const alertBorders = {
  critical: 'border-l-loss bg-loss/5',
  warning: 'border-l-warning bg-warning/5',
  info: 'border-l-accent bg-accent/5',
};

const formatEquityAxisDate = (value) => {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString([], { month: 'short', year: '2-digit' });
};

const formatEquityTooltipDate = (value) => {
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString([], { year: 'numeric', month: 'short', day: 'numeric' });
};

const formatEquityAxisValue = (value) => {
  if (value >= 1_000_000) return `$${(value / 1_000_000).toFixed(1)}M`;
  return `$${Math.round(value / 1000)}k`;
};

const getSignedCurrency = (value) => `${value >= 0 ? '+' : '-'}$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
const getSignedPercent = (value) => `${value >= 0 ? '+' : '-'}${Math.abs(value).toFixed(2)}%`;
const getPercentColor = (value) => (value >= 0 ? 'text-profit' : 'text-loss');
const getValueColor = (value) => (value >= 0 ? 'text-text-primary' : 'text-loss');

export default function Dashboard() {
  const [live,        setLive]        = useState(null);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [refreshing,  setRefreshing]  = useState(false);

  const load = () =>
    fetchDashboard().then(d => { setLive(d); }).catch(() => {});

  // Initial fetch + poll status every 30 s to pick up backend refreshes
  useEffect(() => {
    load();
    fetchStatus().then(s => s.loadedAt && setLastUpdated(new Date(s.loadedAt))).catch(() => {});

    const id = setInterval(() => {
      fetchStatus().then(s => {
        if (!s.loadedAt) return;
        const t = new Date(s.loadedAt);
        setLastUpdated(prev => {
          if (!prev || t > prev) { load(); return t; }
          return prev;
        });
      }).catch(() => {});
    }, 30_000);

    return () => clearInterval(id);
  }, []); // eslint-disable-line

  const handleRefresh = () => {
    setRefreshing(true);
    refreshData()
      .then(() => {
        // Poll until backend is ready again
        const poll = setInterval(() => {
          fetchStatus().then(s => {
            if (s.status === 'ready') {
              clearInterval(poll);
              setRefreshing(false);
              load();
              setLastUpdated(new Date(s.loadedAt));
            }
          }).catch(() => {});
        }, 3_000);
      })
      .catch(() => setRefreshing(false));
  };

  // Merge live data with synthetic fallback
  const portfolioValue  = live?.portfolioValue  ?? synthetic.portfolioValue;
  const totalReturn     = live?.totalReturn     ?? synthetic.totalReturn;
  const dayPnL          = live?.dayPnL          ?? synthetic.dayPnL;
  const dayPnLPercent   = live?.dayPnLPercent   ?? synthetic.dayPnLPercent;
  const mtdPercent      = live?.mtdPercent      ?? synthetic.mtdPercent;
  const sharpeRatio     = live?.sharpeRatio     ?? synthetic.sharpeRatio;
  const positions       = live?.positions       ?? synthetic.positions;
  const equityCurve     = live?.equityCurve     ?? synthetic.equityCurve;
  const stocks          = live?.stocks          ?? synthetic.stocks;
  const signals         = live?.signals         ?? synthetic.signals;
  const alerts          = live?.alerts          ?? synthetic.alerts;
  const sparklines      = live?.sparklines      ?? synthetic.sparklines;

  const donutData = stocks.map(s => ({ name: s.ticker, value: s.weight }));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-text-primary">Dashboard Overview</h1>
        <div className="flex items-center gap-3">
          {lastUpdated && (
            <span className="text-text-secondary text-xs">
              Data as of {lastUpdated.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 text-accent text-xs bg-accent/10 px-3 py-1.5 rounded hover:bg-accent/20 transition-colors disabled:opacity-50"
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
            {refreshing ? 'Refreshing…' : 'Refresh Data'}
          </button>
        </div>
      </div>

      {/* ================================================================
          ROW 1: KPI CARDS (4 cards in a row)
          Each card shows: label, primary value, subtext, and sparkline.
          ================================================================ */}
      <div className="grid grid-cols-4 gap-4">

        {/* KPI CARD 1: Total Portfolio Value
            COMPONENT: Portfolio Optimization
            DATA: portfolioValue (number, USD), mtdPercent (number, %)
            SPARKLINE: Recent portfolio values (array of ~12 numbers)
            TEMPLATE: "$<portfolio_value>" / "+<mtd_percent>% MTD" */}
        <KPICard
          label="Total Portfolio Value"
          value={`$${portfolioValue.toLocaleString()}`}
          subtext={`${getSignedPercent(totalReturn)} Since Start`}
          subtextColor={getPercentColor(totalReturn)}
          secondarySubtext={`${getSignedPercent(mtdPercent)} MTD`}
          secondarySubtextColor={getPercentColor(mtdPercent)}
          sparklineData={sparklines.portfolio}
        />

        {/* KPI CARD 2: Day P&L (Profit & Loss)
            COMPONENT: Real-Time Monitoring
            DATA: dayPnL (number, USD), dayPnLPercent (number, %)
            SPARKLINE: Recent daily P&L values
            TEMPLATE: "+$<day_pnl>" / "+<day_pnl_percent>%"
            COLOR: Green if positive, red if negative */}
        <KPICard
          label="Day P&L"
          value={getSignedCurrency(dayPnL)}
          valueColor={getValueColor(dayPnL)}
          subtext={getSignedPercent(dayPnLPercent)}
          subtextColor={getPercentColor(dayPnLPercent)}
          sparklineColor={dayPnL >= 0 ? '#58A6FF' : '#F85149'}
          sparklineData={sparklines.pnl}
        />

        {/* KPI CARD 3: Sharpe Ratio
            COMPONENT: Portfolio Optimization
            DATA: sharpeRatio (number), sharpeTrend ('up'|'down')
            SPARKLINE: Recent Sharpe ratio values
            TEMPLATE: "<sharpe_ratio>" / "^/v vs last week" */}
        <KPICard
          label="Sharpe Ratio"
          value={sharpeRatio.toFixed(2)}
          subtext="^ vs last week"
          subtextColor="text-profit"
          sparklineData={sparklines.sharpe}
        />

        {/* KPI CARD 4: Active Positions
            COMPONENT: Algorithmic Trading Strategies
            DATA: positions.long (number), positions.short (number)
            TEMPLATE: "<long + short>" / "<long> Long / <short> Short" */}
        <KPICard
          label="Active Positions"
          value={`${positions.long + positions.short}`}
          subtext={`${positions.long} Long / ${positions.short} Short`}
          subtextColor="text-text-secondary"
        />
      </div>

      {/* ================================================================
          ROW 2: EQUITY CURVE (2/3 width) + PORTFOLIO DONUT (1/3 width)
          ================================================================ */}
      <div className="grid grid-cols-3 gap-4">

        {/* EQUITY CURVE CHART
            COMPONENT: Real-Time Monitoring + Portfolio Optimization
            PURPOSE: Shows portfolio performance over time vs benchmark (SPY).
                     Drawdown is shaded in red below the curve.
            DATA: equityCurve[] array with fields:
              - date (string): x-axis label
              - portfolio (number): portfolio value in USD
              - benchmark (number): benchmark value in USD
              - drawdown (number): drawdown % from peak (negative)
            CHART TYPE: ComposedChart (Line + Area) from Recharts */}
        <div className="col-span-2 bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Equity Curve</h2>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={equityCurve} margin={{ top: 8, right: 8, bottom: 8, left: 20 }}>
                <XAxis
                  dataKey="date"
                  tick={{ fontSize: 10, fill: '#8B949E' }}
                  minTickGap={72}
                  tickFormatter={formatEquityAxisDate}
                />
                <YAxis
                  yAxisId="usd"
                  width={84}
                  tick={{ fontSize: 10, fill: '#8B949E' }}
                  tickFormatter={formatEquityAxisValue}
                  domain={['dataMin - 50000', 'dataMax + 50000']}
                  tickCount={6}
                />
                <YAxis yAxisId="drawdown" hide domain={[-25, 0]} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1C2128', border: '1px solid #30363D', borderRadius: 8, fontSize: 12, color: '#E6EDF3' }}
                  labelFormatter={formatEquityTooltipDate}
                  formatter={(v, name) => [
                    String(name).toLowerCase() === 'drawdown' ? `${v}%` : `$${v.toLocaleString()}`,
                    name,
                  ]}
                />
                <Legend wrapperStyle={{ fontSize: 11, color: '#8B949E' }} />
                {/* Blue solid line = portfolio value */}
                <Line yAxisId="usd" type="monotone" dataKey="portfolio" stroke="#58A6FF" strokeWidth={2} dot={false} name="Portfolio" />
                {/* Gray dashed line = benchmark (SPY) */}
                <Line yAxisId="usd" type="monotone" dataKey="benchmark" stroke="#8B949E" strokeWidth={1.5} dot={false} strokeDasharray="4 4" name="Benchmark (SPY)" />
                {/* Red shaded area = drawdown from peak */}
                <Area yAxisId="drawdown" type="monotone" dataKey="drawdown" fill="#F85149" fillOpacity={0.1} stroke="none" name="Drawdown" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* PORTFOLIO ALLOCATION DONUT CHART
            COMPONENT: Portfolio Optimization
            PURPOSE: Visual breakdown of portfolio weight per stock.
            DATA: stocks[] array -> mapped to { name: ticker, value: weight% }
            CHART TYPE: PieChart (Donut) from Recharts
            BELOW CHART: Legend showing top 6 stocks with color dots */}
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Portfolio Allocation</h2>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={donutData} innerRadius={50} outerRadius={80} dataKey="value" nameKey="name" cx="50%" cy="50%">
                  {donutData.map((_, i) => (
                    <Cell key={i} fill={COLORS[i % COLORS.length]} />
                  ))}
                </Pie>
                <Tooltip
                  contentStyle={{ backgroundColor: '#1C2128', border: '1px solid #30363D', borderRadius: 8, fontSize: 12, color: '#E6EDF3' }}
                  formatter={(v) => [`${v}%`]}
                />
              </PieChart>
            </ResponsiveContainer>
          </div>
          {/* Donut legend - top 6 stocks */}
          <div className="grid grid-cols-2 gap-1 mt-2">
            {stocks.slice(0, 6).map((s, i) => (
              <div key={s.ticker} className="flex items-center gap-1.5 text-xs">
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: COLORS[i] }} />
                <span className="text-text-secondary">{s.ticker}</span>
                <span className="text-text-primary font-mono ml-auto">{s.weight}%</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ================================================================
          ROW 3: RECENT SIGNALS (1/2 width) + AI ALERTS (1/2 width)
          ================================================================ */}
      <div className="grid grid-cols-2 gap-4">

        {/* RECENT SIGNALS TABLE
            COMPONENT: Algorithmic Trading Strategies
            PURPOSE: Shows the most recent trading signals generated by
                     the 4 strategy mechanisms (LM, SM, LR, SR) plus exits (SL, TP).
            DATA: signals[] array (last 7), each with:
              - time (string): signal timestamp
              - action (string): 'LONG' | 'SHORT' | 'EXIT'
              - ticker (string): stock symbol
              - type (string): strategy code (LM/SM/LR/SR/SL/TP)
              - strength (number|null): signal confidence 0-1
            TEMPLATE per row: "<time> [ACTION_BADGE] <ticker> <type> <strength>" */}
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Recent Signals</h2>
          <div className="space-y-2">
            {signals.slice(0, 7).map((s, i) => (
              <div key={i} className="flex items-center gap-3 text-xs py-1.5 border-b border-border/50 last:border-0">
                <span className="text-text-secondary font-mono w-10">{s.time}</span>
                <SignalBadge action={s.action} />
                <span className="text-text-primary font-semibold w-12">{s.ticker}</span>
                <span className="text-text-secondary">{s.type}</span>
                {s.strength && (
                  <span className="ml-auto text-text-secondary font-mono">{s.strength.toFixed(1)}</span>
                )}
              </div>
            ))}
          </div>
          {/* Link to Monitoring page for full signal history */}
          <button className="mt-3 text-accent text-xs hover:underline flex items-center gap-1">
            View All <TrendingUp size={12} />
          </button>
        </div>

        {/* AI ALERTS FEED
            COMPONENT: AI-Assisted Explanations
            PURPOSE: Shows AI-generated alerts about risk conditions, volatility
                     spikes, drawdown warnings, and rebalance suggestions.
            DATA: alerts[] array (last 3), each with:
              - severity (string): 'critical' | 'warning' | 'info'
              - time (string): when alert was generated
              - title (string): alert headline
              - message (string): AI-generated explanation
            STYLING:
              - Critical: red left border + red icon
              - Warning:  amber left border + amber icon
              - Info:     blue left border + blue icon
            TEMPLATE per alert: "[ICON] <title> <time> / <message_truncated>" */}
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">AI Alerts</h2>
          <div className="space-y-3">
            {alerts.slice(0, 3).map((a, i) => (
              <div key={i} className={`border-l-2 rounded-r-lg p-3 ${alertBorders[a.severity]}`}>
                <div className="flex items-center gap-2 mb-1">
                  {alertIcons[a.severity]}
                  <span className="text-text-primary text-xs font-semibold">{a.title}</span>
                  <span className="text-text-secondary text-xs ml-auto">{a.time}</span>
                </div>
                <p className="text-text-secondary text-xs leading-relaxed">{a.message.substring(0, 120)}...</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

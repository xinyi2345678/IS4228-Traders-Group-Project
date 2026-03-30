// =============================================================================
// PAGE: LIVE MONITORING DASHBOARD
// ROUTE: /monitoring
// =============================================================================
// PRIMARY COMPONENTS: Algorithmic Trading Strategies + Real-Time Monitoring
//
// Real-time view of the running strategy. This page is the operational
// center for observing the trading system as it executes.
//
// LAYOUT:
// +----------------------------------------------+
// | STATUS BAR (strategy state, regime, update)  |  <- Status
// +----------------------------------------------+
// | KPI ROW (4 mini KPIs)                        |  <- Row 1
// +----------------------------------------------+
// | SIGNAL FEED (3/5)       | POSITION TRACKER   |  <- Row 2
// |                         | (2/5)              |
// +----------------------------------------------+
// | EQUITY CURVE - LIVE (full width)             |  <- Row 3
// +----------------------------------------------+
// | VOLATILITY (1/3) | DRAWDOWN (1/3) | SECTOR   |  <- Row 4
// |                   |                | (1/3)    |
// +----------------------------------------------+
// | [SIGNAL DETAIL MODAL - opens on row click]   |  <- Modal overlay
// +----------------------------------------------+
// =============================================================================

import { useState, useEffect } from 'react';
import * as synthetic from '../data/synthetic';
import { fetchMonitoring } from '../services/api';
import SignalBadge from '../components/SignalBadge';
import KPICard from '../components/KPICard';
import {
  LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer,
  BarChart, Bar, Cell,
} from 'recharts';
import { Pause, Filter, Radio } from 'lucide-react';

const getSignedCurrency = (value) => `${value >= 0 ? '+' : '-'}$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
const getSignedPercent = (value) => `${value >= 0 ? '+' : '-'}${Math.abs(value).toFixed(2)}%`;
const getMetricColor = (value) => (value >= 0 ? 'text-profit' : 'text-loss');

export default function Monitoring() {
  const [selectedSignal, setSelectedSignal] = useState(null);
  const [live, setLive] = useState(null);

  useEffect(() => {
    fetchMonitoring().then(setLive).catch(() => {});
    // Refresh every 60 s
    const id = setInterval(() => fetchMonitoring().then(setLive).catch(() => {}), 60_000);
    return () => clearInterval(id);
  }, []);

  const signals          = live?.signals          ?? synthetic.signals;
  const activePositions  = live?.activePositions  ?? synthetic.activePositions;
  const intradayEquity   = live?.intradayEquity   ?? synthetic.intradayEquity;
  const monitoringKPIs   = live?.monitoringKPIs   ?? synthetic.monitoringKPIs;
  const volatilityMetrics = live?.volatilityMetrics ?? synthetic.volatilityMetrics;
  const drawdownMetrics  = live?.drawdownMetrics  ?? synthetic.drawdownMetrics;
  const sectorExposure   = live?.sectorExposure   ?? synthetic.sectorExposure;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-text-primary">Live Monitoring</h1>
        {/* LIVE BADGE - indicates WebSocket/data feed connection is active
            TODO: Wire to actual connection status */}
        <span className="flex items-center gap-2 bg-profit/10 text-profit text-xs font-semibold px-3 py-1.5 rounded-full">
          <Radio size={12} className="animate-pulse" /> LIVE
        </span>
      </div>

      {/* ================================================================
          STATUS BAR
          COMPONENT: Algorithmic Trading Strategies + Real-Time Monitoring
          PURPOSE: At-a-glance system state.
          DATA:
            - strategy_status: {string} 'RUNNING' | 'PAUSED' | 'STOPPED'
            - current_regime:  {string} 'TRENDING' | 'MEAN-REVERTING' (from regime detector)
            - update_interval: {string} how often data refreshes (e.g., '2s')
          ================================================================ */}
      <div className="bg-bg-surface border border-border rounded-lg px-4 py-2.5 flex items-center gap-6 text-sm">
        <span className="text-text-secondary">Strategy: <span className="text-profit font-semibold">RUNNING</span></span>
        <span className="text-text-secondary">Regime: <span className="text-accent font-semibold">TRENDING</span></span>
        <span className="text-text-secondary">Update: <span className="text-text-primary font-mono">2s</span></span>
      </div>

      {/* ================================================================
          ROW 1: MONITORING KPI CARDS (4 cards)
          COMPONENT: Real-Time Monitoring
          ================================================================ */}
      <div className="grid grid-cols-4 gap-4">
        {/* KPI: Unrealized P&L
            DATA: monitoringKPIs.unrealizedPnL {number} USD
            Total P&L on positions that are still OPEN.
            TEMPLATE: "+$<unrealized_pnl>" */}
        <KPICard
          label="Unrealized P&L"
          value={getSignedCurrency(monitoringKPIs.unrealizedPnL)}
          valueColor={getMetricColor(monitoringKPIs.unrealizedPnL)}
          subtext="Open positions"
          subtextColor={getMetricColor(monitoringKPIs.unrealizedPnL)}
        />

        {/* KPI: Realized P&L
            DATA: monitoringKPIs.realizedPnL {number} USD
            Total P&L on positions CLOSED today.
            TEMPLATE: "+$<realized_pnl>" */}
        <KPICard
          label="Realized P&L"
          value={getSignedCurrency(monitoringKPIs.realizedPnL)}
          valueColor={getMetricColor(monitoringKPIs.realizedPnL)}
          subtext="Closed today"
          subtextColor={getMetricColor(monitoringKPIs.realizedPnL)}
        />

        {/* KPI: Win Rate
            DATA: monitoringKPIs.winRate {number} %
            Percentage of today's closed trades that were profitable.
            TEMPLATE: "<win_rate>%" */}
        <KPICard label="Win Rate" value={`${monitoringKPIs.winRate}%`} subtext="Today's trades" subtextColor="text-text-secondary" />

        {/* KPI: Net Exposure
            DATA: monitoringKPIs.netExposure {number} %
            (long_value - short_value) / total_value * 100.
            Positive = net long, Negative = net short.
            TEMPLATE: "<net_exposure>% Net Long/Short" */}
        <KPICard
          label="Net Exposure"
          value={getSignedPercent(monitoringKPIs.netExposure)}
          valueColor={monitoringKPIs.netExposure >= 0 ? 'text-accent' : 'text-loss'}
          subtext={monitoringKPIs.netExposure >= 0 ? 'Net Long' : 'Net Short'}
          subtextColor={monitoringKPIs.netExposure >= 0 ? 'text-accent' : 'text-loss'}
        />
      </div>

      {/* ================================================================
          ROW 2: SIGNAL FEED (3/5) + POSITION TRACKER (2/5)
          ================================================================ */}
      <div className="grid grid-cols-5 gap-4">

        {/* LIVE SIGNAL FEED TABLE
            COMPONENT: Algorithmic Trading Strategies
            PURPOSE: Scrolling table of all trading signals generated by the
                     strategy engine in reverse chronological order.
            DATA: signals[] array, each with:
              - time {string}: signal timestamp
              - ticker {string}: stock symbol
              - action {string}: 'LONG' | 'SHORT' | 'EXIT'
              - type {string}: strategy code:
                  LM = Long Momentum, SM = Short Momentum,
                  LR = Long Reversion, SR = Short Reversion,
                  SL = Stop-Loss exit, TP = Take-Profit exit
              - strength {number|null}: confidence 0-1 (null for exits)
            SOURCE: WebSocket feed from strategy engine
            INTERACTION: Click a row to open Signal Detail Modal
            TODO: Wire "Pause Feed" to pause WebSocket updates
            TODO: Wire "Filter" to filter by action/type/ticker */}
        <div className="col-span-3 bg-bg-surface border border-border rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-semibold text-text-primary">Live Signal Feed</h2>
            <div className="flex gap-2">
              <button className="flex items-center gap-1 text-text-secondary text-xs bg-bg-elevated px-2 py-1 rounded border border-border hover:text-text-primary">
                <Pause size={12} /> Pause Feed
              </button>
              <button className="flex items-center gap-1 text-text-secondary text-xs bg-bg-elevated px-2 py-1 rounded border border-border hover:text-text-primary">
                <Filter size={12} /> Filter
              </button>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="border-b border-border text-text-secondary">
                  <th className="text-left py-2 px-2">Time</th>
                  <th className="text-left py-2 px-2">Ticker</th>
                  <th className="text-left py-2 px-2">Action</th>
                  <th className="text-left py-2 px-2">Type</th>
                  <th className="text-right py-2 px-2">Strength</th>
                </tr>
              </thead>
              <tbody>
                {/* TEMPLATE per row: "<time> <ticker> [ACTION_BADGE] <type> <strength>" */}
                {signals.map((s, i) => (
                  <tr
                    key={i}
                    className="border-b border-border/30 hover:bg-bg-elevated cursor-pointer transition-colors"
                    onClick={() => setSelectedSignal(s)}
                  >
                    <td className="py-2 px-2 font-mono text-text-secondary">{s.time}</td>
                    <td className="py-2 px-2 font-semibold text-text-primary">{s.ticker}</td>
                    <td className="py-2 px-2"><SignalBadge action={s.action} /></td>
                    <td className="py-2 px-2 text-text-secondary">{s.type}</td>
                    <td className="py-2 px-2 text-right font-mono text-text-primary">{s.strength ? s.strength.toFixed(2) : '--'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* POSITION TRACKER
            COMPONENT: Algorithmic Trading Strategies + Real-Time Monitoring
            PURPOSE: Card-based view of all currently open positions.
                     Each card shows entry price, current price, P&L,
                     and a progress bar showing position between SL and TP.
            DATA: activePositions[] array, each with:
              - ticker {string}: stock symbol
              - direction {string}: 'LONG' | 'SHORT'
              - entry {number}: entry price USD
              - current {number}: current price USD (live feed)
              - pnl {number}: unrealized P&L USD
              - pnlPercent {number}: unrealized P&L %
              - sl {number}: stop-loss price level
              - tp {number}: take-profit price level
            PROGRESS BAR: Shows how far current price is between SL and TP.
              For LONG: progress = (current - entry) / (tp - entry)
              For SHORT: progress = (entry - current) / (entry - tp)
            FOOTER: Summary count of long/short positions */}
        <div className="col-span-2 bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Position Tracker</h2>
          <div className="space-y-2 overflow-y-auto max-h-[360px]">
            {activePositions.map(p => {
              const isLong = p.direction === 'LONG';
              const progress = isLong
                ? ((p.current - p.entry) / (p.tp - p.entry)) * 100
                : ((p.entry - p.current) / (p.entry - p.tp)) * 100;

              return (
                <div key={p.ticker} className="bg-bg-elevated border border-border/50 rounded-lg p-3">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-text-primary text-sm font-semibold">{p.ticker}</span>
                    <SignalBadge action={p.direction} />
                  </div>
                  {/* TEMPLATE: "Entry: $<entry> | Current: $<current> | P&L: +$<pnl> (+<pnl%>%)" */}
                  <div className="grid grid-cols-3 gap-2 text-xs mb-2">
                    <div>
                      <span className="text-text-secondary">Entry: </span>
                      <span className="text-text-primary font-mono">${p.entry.toFixed(2)}</span>
                    </div>
                    <div>
                      <span className="text-text-secondary">Current: </span>
                      <span className="text-text-primary font-mono">${p.current.toFixed(2)}</span>
                    </div>
                    <div className="text-right">
                      <span className={`font-mono font-semibold ${p.pnl >= 0 ? 'text-profit' : 'text-loss'}`}>
                        {p.pnl >= 0 ? '+' : ''}${p.pnl} ({p.pnlPercent >= 0 ? '+' : ''}{p.pnlPercent}%)
                      </span>
                    </div>
                  </div>
                  {/* Progress bar: position between stop-loss and take-profit */}
                  <div className="relative h-1.5 bg-bg-main rounded-full overflow-hidden">
                    <div
                      className={`absolute left-0 top-0 h-full rounded-full ${p.pnl >= 0 ? 'bg-profit' : 'bg-loss'}`}
                      style={{ width: `${Math.max(0, Math.min(100, progress))}%` }}
                    />
                  </div>
                  <div className="flex justify-between text-xs text-text-secondary mt-1">
                    <span>SL: ${p.sl.toFixed(2)}</span>
                    <span>TP: ${p.tp.toFixed(2)}</span>
                  </div>
                </div>
              );
            })}
          </div>
          {/* Position count summary */}
          <div className="mt-3 text-center text-xs text-text-secondary">
            {activePositions.filter(p => p.direction === 'LONG').length}L / {activePositions.filter(p => p.direction === 'SHORT').length}S
          </div>
        </div>
      </div>

      {/* ================================================================
          ROW 3: EQUITY CURVE - LIVE (full width)
          COMPONENT: Real-Time Monitoring
          PURPOSE: Intraday portfolio value chart. Updates in real-time
                   as the strategy runs during the trading day.
          DATA: intradayEquity[] array with:
            - time {string}: 'HH:MM' format
            - value {number}: portfolio value in USD at that timestamp
          SOURCE: Real-time portfolio tracker (snapshot every ~5 min)
          CHART TYPE: LineChart from Recharts
          TIME RANGE BUTTONS: 1D (default), 1W, 1M, 3M, ALL
            TODO: Wire buttons to fetch different time ranges from backend
          ================================================================ */}
      <div className="bg-bg-surface border border-border rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-text-primary">Equity Curve (Live)</h2>
          <div className="flex gap-1">
            {['1D', '1W', '1M', '3M', 'ALL'].map(t => (
              <button key={t} className={`px-2 py-0.5 rounded text-xs ${t === '1D' ? 'bg-accent/15 text-accent' : 'text-text-secondary hover:text-text-primary'}`}>
                {t}
              </button>
            ))}
          </div>
        </div>
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={intradayEquity}>
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#8B949E' }} interval={11} />
              <YAxis tick={{ fontSize: 10, fill: '#8B949E' }} tickFormatter={v => `$${(v / 1000).toFixed(0)}k`} domain={['dataMin - 2000', 'dataMax + 2000']} />
              <Tooltip contentStyle={{ backgroundColor: '#1C2128', border: '1px solid #30363D', borderRadius: 8, fontSize: 12, color: '#E6EDF3' }} formatter={v => [`$${v.toLocaleString()}`]} />
              <Line type="monotone" dataKey="value" stroke="#58A6FF" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ================================================================
          ROW 4: VOLATILITY (1/3) + DRAWDOWN (1/3) + SECTOR EXPOSURE (1/3)
          These are risk monitoring panels.
          ================================================================ */}
      <div className="grid grid-cols-3 gap-4">

        {/* VOLATILITY MONITOR
            COMPONENT: Real-Time Monitoring
            PURPOSE: Gauge-style display of current volatility metrics.
                     Color shifts from green (low) to amber (medium) to red (high).
            DATA: volatilityMetrics object:
              - atr {number}: Average True Range (14-period) for portfolio
              - vix {number}: CBOE VIX index value
              - portfolioVol {number}: % annualized portfolio volatility
            THRESHOLDS (for color coding):
              - <40% of max: green (normal)
              - 40-70% of max: amber (elevated)
              - >70% of max: red (high risk) */}
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Volatility Monitor</h2>
          <div className="space-y-4">
            {[
              { label: 'ATR (14)', value: volatilityMetrics.atr, max: 5 },
              { label: 'VIX', value: volatilityMetrics.vix, max: 40 },
              { label: 'Portfolio Vol', value: volatilityMetrics.portfolioVol, max: 25 },
            ].map(m => (
              <div key={m.label}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-text-secondary">{m.label}</span>
                  <span className="text-text-primary font-mono">{m.value}</span>
                </div>
                {/* Gauge bar: width = value/max, color = green/amber/red based on ratio */}
                <div className="h-2 bg-bg-main rounded-full overflow-hidden">
                  <div
                    className="h-full rounded-full transition-all"
                    style={{
                      width: `${(m.value / m.max) * 100}%`,
                      backgroundColor: m.value / m.max > 0.7 ? '#F85149' : m.value / m.max > 0.4 ? '#D29922' : '#3FB950',
                    }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* DRAWDOWN TRACKER
            COMPONENT: Real-Time Monitoring
            PURPOSE: Shows current and historical drawdown levels.
                     Drawdown = peak-to-trough decline as %.
            DATA: drawdownMetrics object:
              - current {number}: current drawdown % from recent peak (negative)
              - maxToday {number}: worst drawdown seen today (negative)
              - maxEver {number}: worst drawdown since inception (negative)
            THRESHOLDS: Bar shows how close drawdown is to the alert threshold
              (e.g., -5% for daily, -10% for max ever) */}
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Drawdown Tracker</h2>
          <div className="space-y-4">
            {[
              { label: 'Current', value: drawdownMetrics.current, threshold: -5 },
              { label: 'Max Today', value: drawdownMetrics.maxToday, threshold: -5 },
              { label: 'Max Ever', value: drawdownMetrics.maxEver, threshold: -10 },
            ].map(m => (
              <div key={m.label}>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-text-secondary">{m.label}</span>
                  <span className="text-loss font-mono">{m.value}%</span>
                </div>
                {/* Bar: width = |value / threshold|, always red */}
                <div className="h-2 bg-bg-main rounded-full overflow-hidden">
                  <div
                    className="h-full bg-loss rounded-full"
                    style={{ width: `${Math.abs(m.value / m.threshold) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* SECTOR EXPOSURE BAR CHART
            COMPONENT: Real-Time Monitoring + Portfolio Optimization
            PURPOSE: Shows net long/short exposure per sector.
                     Positive bars = net long, negative bars = net short.
            DATA: sectorExposure[] array:
              - sector {string}: sector name
              - exposure {number}: net exposure % (positive=long, negative=short)
            CHART TYPE: Horizontal BarChart from Recharts
            COLORS: Green for positive (long), red for negative (short) */}
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Sector Exposure</h2>
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={sectorExposure} layout="vertical" margin={{ left: 80 }}>
                <XAxis type="number" tick={{ fontSize: 10, fill: '#8B949E' }} tickFormatter={v => `${v}%`} />
                <YAxis dataKey="sector" type="category" tick={{ fontSize: 10, fill: '#E6EDF3' }} width={75} />
                <Tooltip contentStyle={{ backgroundColor: '#1C2128', border: '1px solid #30363D', borderRadius: 8, fontSize: 12, color: '#E6EDF3' }} formatter={v => [`${v}%`]} />
                <Bar dataKey="exposure" radius={[0, 4, 4, 0]}>
                  {sectorExposure.map((e, i) => (
                    <Cell key={i} fill={e.exposure >= 0 ? '#3FB950' : '#F85149'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* ================================================================
          SIGNAL DETAIL MODAL (overlay)
          COMPONENT: Algorithmic Trading Strategies
          PURPOSE: Detailed view of a single trading signal when clicked
                   from the signal feed table.
          DATA: Single signal object with:
            - action, ticker, time, type, strength, detail
          SECTIONS:
            - Header: action badge + ticker + time
            - Analysis: the signal's detail text (indicator readings)
            - Strength bar: visual 0-1 confidence meter
          TODO: Add indicator snapshot (MACD values, BB position, ATR)
          TODO: Add "Ask AI to Explain" button linking to AI Insights
          ================================================================ */}
      {selectedSignal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setSelectedSignal(null)}>
          <div className="bg-bg-surface border border-border rounded-xl p-6 w-[480px]" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-text-primary">Signal Detail</h2>
              <button onClick={() => setSelectedSignal(null)} className="text-text-secondary hover:text-text-primary text-xl">&times;</button>
            </div>

            <div className="flex items-center gap-3 mb-4">
              <SignalBadge action={selectedSignal.action} />
              <span className="text-text-primary font-semibold text-lg">{selectedSignal.ticker}</span>
              <span className="text-text-secondary text-sm ml-auto">Time: {selectedSignal.time} AM</span>
            </div>

            {/* Signal analysis from strategy engine */}
            <div className="bg-bg-elevated border border-border/50 rounded-lg p-4 mb-4">
              <h3 className="text-xs font-semibold text-text-secondary uppercase mb-2">Analysis</h3>
              <p className="text-text-primary text-sm leading-relaxed">{selectedSignal.detail}</p>
            </div>

            {/* Signal strength progress bar (only for entry signals, not exits) */}
            {selectedSignal.strength && (
              <div>
                <div className="flex justify-between text-sm mb-1">
                  <span className="text-text-secondary">Signal Strength</span>
                  <span className="text-text-primary font-mono">{selectedSignal.strength.toFixed(2)} / 1.00</span>
                </div>
                <div className="h-2.5 bg-bg-main rounded-full overflow-hidden">
                  <div className="h-full bg-accent rounded-full" style={{ width: `${selectedSignal.strength * 100}%` }} />
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

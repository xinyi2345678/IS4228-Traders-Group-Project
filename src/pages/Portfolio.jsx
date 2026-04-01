// =============================================================================
// PAGE: PORTFOLIO DISTRIBUTION
// ROUTE: /portfolio
// =============================================================================
// PRIMARY COMPONENT: Portfolio Optimization
//
// This page shows how capital is allocated across the 10 stocks, the results
// of the mean-variance optimizer, and per-stock risk metrics.
//
// LAYOUT:
// +----------------------------------------------+
// | CONTROL BAR (optimizer selector, run button) |  <- Controls
// +----------------------------------------------+
// | TREEMAP (1/3)   | FRONTIER (1/3) | SUMMARY   |  <- Row 1
// |                  |                | (1/3)     |
// +----------------------------------------------+
// | ALLOCATION TABLE (full width, sortable)      |  <- Row 2
// +----------------------------------------------+
// | SECTOR PIE (1/2) | RISK BARS (1/2)           |  <- Row 3
// +----------------------------------------------+
// | [STOCK DETAIL MODAL - opens on row click]    |  <- Modal overlay
// +----------------------------------------------+
// =============================================================================

import { useState, useEffect } from 'react';
import * as synthetic from '../data/synthetic';
import { fetchPortfolio } from '../services/api';
import {
  ScatterChart, Scatter, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid,
  PieChart, Pie, Cell, BarChart, Bar, ComposedChart, Line, Legend,
} from 'recharts';

const SECTOR_COLORS = {
  Technology: '#58A6FF',
  Communication: '#A371F7',
  Consumer: '#3FB950',
  Financial: '#D29922',
  Healthcare: '#F85149',
};

const renderSectorLabel = ({ cx, cy, midAngle, outerRadius, name, value, fill }) => {
  const RADIAN = Math.PI / 180;
  const radius = outerRadius + 18;
  const x = cx + radius * Math.cos(-midAngle * RADIAN);
  const y = cy + radius * Math.sin(-midAngle * RADIAN);
  const textAnchor = x > cx ? 'start' : 'end';

  return (
    <text x={x} y={y} fill={fill} textAnchor={textAnchor} dominantBaseline="central" fontSize={11}>
      {`${name} ${value}%`}
    </text>
  );
};

export default function Portfolio() {
  const [selectedStock, setSelectedStock] = useState(null);
  const [live, setLive] = useState(null);

  useEffect(() => {
    fetchPortfolio().then(setLive).catch(() => {});
  }, []);

  const stocks          = live?.stocks          ?? synthetic.stocks;
  const sectorBreakdown = live?.sectorBreakdown ?? synthetic.sectorBreakdown;
  const riskContribution = live?.riskContribution ?? synthetic.riskContribution;
  const efficientFrontier = live?.efficientFrontier ?? synthetic.efficientFrontier;
  const individualStocks  = live?.individualStocks  ?? synthetic.individualStocks;
  const currentPortfolio  = live?.currentPortfolio  ?? synthetic.currentPortfolio;
  const portfolioValue    = live?.portfolioValue    ?? synthetic.portfolioValue;
  const optMetrics        = live?.optimizationMetrics ?? {};

  const stockScatter = individualStocks.map(s => ({
    volatility: s.volatility,
    return: s.return,
    ticker: s.ticker,
  }));
  const currentPortfolioPoint = currentPortfolio?.volatility != null && currentPortfolio?.return != null
    ? [currentPortfolio]
    : [];
  const riskMap = Object.fromEntries(riskContribution.map((row) => [row.ticker, row.risk]));
  const allocationVsRisk = stocks.map((stock) => ({
    ticker: stock.ticker,
    weight: stock.weight,
    risk: riskMap[stock.ticker] ?? 0,
  }));
  const correlationData = stocks.map((stock) => ({
    ticker: stock.ticker,
    corr: stock.corrToPort ?? 0,
  }));
  const returnVolData = stocks.map((stock) => ({
    ticker: stock.ticker,
    return: stock.annReturn ?? 0,
    volatility: stock.volatility ?? 0,
  }));
  const topHolding = stocks[0];
  const concentration = stocks.reduce((sum, stock) => sum + (stock.weight / 100) ** 2, 0) * 100;
  const riskBudgetGap = allocationVsRisk.reduce((sum, row) => sum + Math.abs(row.weight - row.risk), 0) / 2;
  const allVolatility = [
    ...efficientFrontier.map(p => p.volatility),
    ...stockScatter.map(s => s.volatility),
    ...currentPortfolioPoint.map(p => p.volatility),
  ].filter(v => Number.isFinite(v));
  const allReturns = [
    ...efficientFrontier.map(p => p.return),
    ...stockScatter.map(s => s.return),
    ...currentPortfolioPoint.map(p => p.return),
  ].filter(v => Number.isFinite(v));

  const xMin = allVolatility.length ? Math.min(...allVolatility) : 0;
  const xMax = allVolatility.length ? Math.max(...allVolatility) : 1;
  const yMin = allReturns.length ? Math.min(...allReturns) : 0;
  const yMax = allReturns.length ? Math.max(...allReturns) : 1;
  const xPad = Math.max(0.5, (xMax - xMin) * 0.08);
  const yPad = Math.max(1, (yMax - yMin) * 0.1);

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-text-primary">Portfolio Distribution</h1>

      {/* ================================================================
          ROW 1: TREEMAP + EFFICIENT FRONTIER + OPTIMIZATION SUMMARY
          ================================================================ */}
      <div className="grid grid-cols-3 gap-4">

        {/* ALLOCATION TREEMAP
            COMPONENT: Portfolio Optimization
            PURPOSE: Visual representation of portfolio weight distribution.
                     Each block's size is proportional to the stock's weight.
                     Color indicates sector.
            DATA: stocks[] array -> ticker, weight, sector
            INTERACTION: Click a block to open the Stock Detail Modal.
            NOTE: This is a simplified CSS grid treemap. For a true treemap,
                  consider using a library like recharts-treemap or d3-treemap. */}
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Allocation Treemap</h2>
          <div className="grid grid-cols-4 gap-1 h-48">
            {stocks.map((s) => {
              const area = s.weight;
              const cols = area > 14 ? 2 : 1;
              const rows = area > 10 ? 2 : 1;
              return (
                <div
                  key={s.ticker}
                  className="rounded flex flex-col items-center justify-center text-xs cursor-pointer hover:opacity-80 transition-opacity"
                  style={{
                    backgroundColor: `${SECTOR_COLORS[s.sector] || '#8B949E'}22`,
                    border: `1px solid ${SECTOR_COLORS[s.sector] || '#8B949E'}44`,
                    gridColumn: `span ${cols}`,
                    gridRow: `span ${rows}`,
                  }}
                  onClick={() => setSelectedStock(s)}
                >
                  {/* TEMPLATE: "<ticker>" / "<weight>%" */}
                  <span className="font-semibold text-text-primary">{s.ticker}</span>
                  <span className="text-text-secondary">{s.weight}%</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* EFFICIENT FRONTIER CHART
            COMPONENT: Portfolio Optimization
            PURPOSE: Scatter plot showing the mean-variance efficient frontier.
                     Displays the tradeoff between risk (volatility) and return.
            DATA:
              - efficientFrontier[]: points along the frontier curve
                Fields: volatility (number), return (number)
              - individualStocks[]: each stock plotted as a gray dot
                Fields: volatility (number), return (number), ticker (string)
              - currentPortfolio: green diamond showing where current portfolio sits
                Fields: volatility (number), return (number)
            CHART TYPE: ScatterChart from Recharts
            LEGEND: Blue curve = frontier, Gray dots = individual stocks,
                    Green diamond = current portfolio position */}
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Efficient Frontier</h2>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 5, right: 12, bottom: 20, left: 8 }}>
                <CartesianGrid stroke="#30363D" strokeDasharray="3 3" vertical={false} />
                <XAxis
                  type="number"
                  dataKey="volatility"
                  name="Volatility"
                  domain={[Math.max(0, xMin - xPad), xMax + xPad]}
                  tickCount={6}
                  tick={{ fontSize: 10, fill: '#8B949E' }}
                  tickFormatter={v => `${v.toFixed(1)}`}
                  label={{ value: 'Volatility (%)', position: 'bottom', fontSize: 10, fill: '#8B949E' }}
                />
                <YAxis
                  type="number"
                  dataKey="return"
                  name="Return"
                  domain={[yMin - yPad, yMax + yPad]}
                  tickCount={6}
                  width={42}
                  tick={{ fontSize: 10, fill: '#8B949E' }}
                  tickFormatter={v => `${v.toFixed(1)}`}
                  label={{ value: 'Return (%)', angle: -90, position: 'insideLeft', fontSize: 10, fill: '#8B949E' }}
                />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1C2128', border: '1px solid #30363D', borderRadius: 8, fontSize: 12, color: '#E6EDF3' }}
                  formatter={(value, name) => [`${Number(value).toFixed(2)}%`, name === 'volatility' ? 'Volatility' : 'Return']}
                />
                {/* Blue frontier curve */}
                <Scatter name="Frontier" data={efficientFrontier} fill="#58A6FF" line={{ stroke: '#58A6FF', strokeWidth: 2 }} shape="circle" r={0} />
                {/* Gray dots = individual stock risk/return */}
                <Scatter name="Stocks" data={stockScatter} fill="#8B949E" r={4} />
                {/* Green diamond = current portfolio */}
                <Scatter name="Portfolio" data={currentPortfolioPoint} fill="#3FB950" r={7} shape="diamond" />
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* OPTIMIZATION SUMMARY
            COMPONENT: Portfolio Optimization
            PURPOSE: Key metrics from the optimizer output.
            DATA (all from optimizer):
              - target_sharpe:     {number} Sharpe ratio of optimized portfolio
              - expected_return:   {number} % annualized expected return
              - portfolio_vol:     {number} % annualized portfolio volatility
              - max_drawdown:      {number} % maximum historical drawdown
            TEMPLATE per metric: "<label>: <value>" */}
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Optimization Summary</h2>
          <div className="space-y-4">
            {[
              { label: 'Target Sharpe',      value: optMetrics.sharpe     != null ? optMetrics.sharpe.toFixed(2)     : '—',                    color: 'text-accent' },
              { label: 'Expected Return',    value: optMetrics.return     != null ? `${optMetrics.return.toFixed(1)}%`    : `${currentPortfolio.return}%`,   color: 'text-profit' },
              { label: 'Portfolio Volatility', value: optMetrics.volatility != null ? `${optMetrics.volatility.toFixed(1)}%` : `${currentPortfolio.volatility}%`, color: 'text-text-primary' },
              { label: 'Top Holding',        value: topHolding ? `${topHolding.ticker} ${topHolding.weight}%` : '—',    color: 'text-warning' },
              { label: 'Concentration (HHI)', value: `${concentration.toFixed(1)}`,                                      color: 'text-text-primary' },
              { label: 'Risk Budget Gap',    value: `${riskBudgetGap.toFixed(1)} pts`,                                   color: 'text-loss' },
            ].map(item => (
              <div key={item.label} className="flex justify-between items-center">
                <span className="text-text-secondary text-sm">{item.label}</span>
                <span className={`font-mono font-semibold text-lg ${item.color}`}>{item.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ================================================================
          ROW 2: ALLOCATION TABLE (full width)
          COMPONENT: Portfolio Optimization
          PURPOSE: Detailed table of all stock allocations with sortable columns.
          DATA: stocks[] array - one row per stock, plus totals row.
          COLUMNS:
            - Ticker:  stock symbol (string)
            - Name:    company name (string)
            - Weight:  portfolio weight % from optimizer (number)
            - Value:   dollar value = weight * portfolio_value (number)
            - Sector:  market sector, displayed as colored badge (string)
            - Price:   current market price from data feed (number)
            - Change:  today's price change %, green/red colored (number)
          INTERACTION: Click any row to open Stock Detail Modal.
          ================================================================ */}
      <div className="bg-bg-surface border border-border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-text-primary mb-3">Allocation Detail</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-border text-text-secondary text-xs">
                <th className="text-left py-2 px-3">Ticker</th>
                <th className="text-left py-2 px-3">Name</th>
                <th className="text-right py-2 px-3">Weight</th>
                <th className="text-right py-2 px-3">Value</th>
                <th className="text-left py-2 px-3">Sector</th>
                <th className="text-right py-2 px-3">Price</th>
                <th className="text-right py-2 px-3">Change</th>
              </tr>
            </thead>
            <tbody>
              {stocks.map(s => (
                <tr
                  key={s.ticker}
                  className="border-b border-border/30 hover:bg-bg-elevated cursor-pointer transition-colors"
                  onClick={() => setSelectedStock(s)}
                >
                  <td className="py-2.5 px-3 font-semibold text-text-primary">{s.ticker}</td>
                  <td className="py-2.5 px-3 text-text-secondary">{s.name}</td>
                  <td className="py-2.5 px-3 text-right font-mono text-text-primary">{s.weight}%</td>
                  <td className="py-2.5 px-3 text-right font-mono text-text-primary">${s.value.toLocaleString()}</td>
                  <td className="py-2.5 px-3">
                    <span className="px-2 py-0.5 rounded text-xs" style={{ backgroundColor: `${SECTOR_COLORS[s.sector]}22`, color: SECTOR_COLORS[s.sector] }}>
                      {s.sector}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-right font-mono text-text-primary">${s.price.toFixed(2)}</td>
                  <td className={`py-2.5 px-3 text-right font-mono ${s.change >= 0 ? 'text-profit' : 'text-loss'}`}>
                    {s.change >= 0 ? '+' : ''}{s.change}%
                  </td>
                </tr>
              ))}
              {/* Totals row */}
              <tr className="border-t-2 border-border font-semibold">
                <td className="py-2.5 px-3 text-text-primary">TOTAL</td>
                <td className="py-2.5 px-3" />
                <td className="py-2.5 px-3 text-right font-mono text-text-primary">100%</td>
                <td className="py-2.5 px-3 text-right font-mono text-text-primary">${portfolioValue.toLocaleString()}</td>
                <td colSpan={3} />
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      {/* ================================================================
          ROW 3: SECTOR BREAKDOWN (1/2) + RISK CONTRIBUTION (1/2)
          ================================================================ */}
      <div className="grid grid-cols-2 gap-4">

        {/* SECTOR BREAKDOWN PIE CHART
            COMPONENT: Portfolio Optimization
            PURPOSE: Shows portfolio weight aggregated by market sector.
            DATA: sectorBreakdown[] array with:
              - name (string): sector name
              - value (number): total weight % for that sector
              - color (string): hex color for the pie slice
            CHART TYPE: PieChart from Recharts */}
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Sector Breakdown</h2>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart margin={{ top: 8, right: 36, bottom: 8, left: 36 }}>
                <Pie
                  data={sectorBreakdown}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={72}
                  labelLine
                  label={renderSectorLabel}
                >
                  {sectorBreakdown.map((s, i) => (
                    <Cell key={i} fill={s.color} />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ backgroundColor: '#1C2128', border: '1px solid #30363D', borderRadius: 8, fontSize: 12, color: '#E6EDF3' }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* RISK CONTRIBUTION BAR CHART
            COMPONENT: Portfolio Optimization
            PURPOSE: Shows each stock's marginal contribution to total portfolio risk.
                     Note: NVDA/TSLA contribute disproportionate risk despite smaller weights
                     due to higher volatility. This is a key optimizer output.
            DATA: riskContribution[] array with:
              - ticker (string): stock symbol
              - risk (number): % contribution to total portfolio risk (sums to 100)
            CHART TYPE: Horizontal BarChart from Recharts */}
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Risk Contribution</h2>
          <div className="h-52">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={riskContribution} layout="vertical" margin={{ left: 40 }}>
                <XAxis type="number" tick={{ fontSize: 10, fill: '#8B949E' }} tickFormatter={v => `${v}%`} />
                <YAxis dataKey="ticker" type="category" tick={{ fontSize: 11, fill: '#E6EDF3' }} width={40} />
                <Tooltip contentStyle={{ backgroundColor: '#1C2128', border: '1px solid #30363D', borderRadius: 8, fontSize: 12, color: '#E6EDF3' }} formatter={v => [`${v}%`]} />
                <Bar dataKey="risk" fill="#58A6FF" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Weight vs Risk Budget</h2>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart data={allocationVsRisk} margin={{ top: 8, right: 12, bottom: 8, left: 4 }}>
                <CartesianGrid stroke="#30363D" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="ticker" tick={{ fontSize: 10, fill: '#8B949E' }} />
                <YAxis tick={{ fontSize: 10, fill: '#8B949E' }} tickFormatter={(v) => `${v}%`} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1C2128', border: '1px solid #30363D', borderRadius: 8, fontSize: 12, color: '#E6EDF3' }}
                  formatter={(value, name) => [`${Number(value).toFixed(1)}%`, name === 'weight' ? 'Weight' : 'Risk Contribution']}
                />
                <Legend wrapperStyle={{ fontSize: 11, color: '#8B949E' }} />
                <Bar dataKey="weight" fill="#58A6FF" radius={[4, 4, 0, 0]} name="weight" />
                <Line type="monotone" dataKey="risk" stroke="#F85149" strokeWidth={2} dot={{ r: 3 }} name="risk" />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-bg-surface border border-border rounded-lg p-4">
          <h2 className="text-sm font-semibold text-text-primary mb-3">Correlation to Portfolio</h2>
          <div className="h-60">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={correlationData} layout="vertical" margin={{ left: 28, right: 12 }}>
                <CartesianGrid stroke="#30363D" strokeDasharray="3 3" horizontal={false} />
                <XAxis type="number" domain={[-1, 1]} tick={{ fontSize: 10, fill: '#8B949E' }} />
                <YAxis dataKey="ticker" type="category" tick={{ fontSize: 11, fill: '#E6EDF3' }} width={40} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#1C2128', border: '1px solid #30363D', borderRadius: 8, fontSize: 12, color: '#E6EDF3' }}
                  formatter={(value) => [Number(value).toFixed(3), 'Correlation']}
                />
                <Bar dataKey="corr" radius={[0, 4, 4, 0]}>
                  {correlationData.map((row) => (
                    <Cell key={row.ticker} fill={row.corr >= 0 ? '#3FB950' : '#F85149'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      <div className="bg-bg-surface border border-border rounded-lg p-4">
        <h2 className="text-sm font-semibold text-text-primary mb-3">Stock Return vs Volatility</h2>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart data={returnVolData} margin={{ top: 8, right: 12, bottom: 8, left: 4 }}>
              <CartesianGrid stroke="#30363D" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="ticker" tick={{ fontSize: 10, fill: '#8B949E' }} />
              <YAxis yAxisId="left" tick={{ fontSize: 10, fill: '#8B949E' }} tickFormatter={(v) => `${v}%`} />
              <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10, fill: '#8B949E' }} tickFormatter={(v) => `${v}%`} />
              <Tooltip
                contentStyle={{ backgroundColor: '#1C2128', border: '1px solid #30363D', borderRadius: 8, fontSize: 12, color: '#E6EDF3' }}
                formatter={(value, name) => [`${Number(value).toFixed(2)}%`, name === 'return' ? 'Annualized Return' : 'Volatility']}
              />
              <Legend wrapperStyle={{ fontSize: 11, color: '#8B949E' }} />
              <Bar yAxisId="left" dataKey="return" fill="#3FB950" radius={[4, 4, 0, 0]} name="return" />
              <Line yAxisId="right" type="monotone" dataKey="volatility" stroke="#D29922" strokeWidth={2} dot={{ r: 3 }} name="volatility" />
            </ComposedChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ================================================================
          STOCK DETAIL MODAL (overlay)
          COMPONENT: Portfolio Optimization
          PURPOSE: Shows detailed info for a single stock when clicked from
                   the treemap or allocation table.
          DATA: Single stock object from stocks[] with all fields:
            - ticker, name, weight, value, shares, price
            - annReturn, volatility, beta, corrToPort
          INTERACTION: Click backdrop or X to close.
          TODO: Add 30-day price chart (requires historical price data)
          TODO: Add "View in Monitoring" and "Ask AI about" buttons
          ================================================================ */}
      {selectedStock && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={() => setSelectedStock(null)}>
          <div className="bg-bg-surface border border-border rounded-xl p-6 w-[480px] max-h-[80vh] overflow-y-auto" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-semibold text-text-primary">{selectedStock.ticker} - {selectedStock.name}</h2>
              <button onClick={() => setSelectedStock(null)} className="text-text-secondary hover:text-text-primary text-xl">&times;</button>
            </div>

            {/* Basic position info */}
            <div className="grid grid-cols-2 gap-4 text-sm mb-4">
              <div>
                <span className="text-text-secondary">Weight:</span>
                <span className="text-text-primary font-mono ml-2">{selectedStock.weight}%</span>
              </div>
              <div>
                <span className="text-text-secondary">Value:</span>
                <span className="text-text-primary font-mono ml-2">${selectedStock.value.toLocaleString()}</span>
              </div>
              <div>
                <span className="text-text-secondary">Shares:</span>
                <span className="text-text-primary font-mono ml-2">{selectedStock.shares}</span>
              </div>
              <div>
                <span className="text-text-secondary">Price:</span>
                <span className="text-text-primary font-mono ml-2">${selectedStock.price.toFixed(2)}</span>
              </div>
            </div>

            {/* Risk/return metrics from optimizer */}
            <div className="border-t border-border pt-4 space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-text-secondary">Annualized Return</span>
                <span className="text-profit font-mono">+{selectedStock.annReturn}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Volatility</span>
                <span className="text-text-primary font-mono">{selectedStock.volatility}%</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Beta</span>
                <span className="text-text-primary font-mono">{selectedStock.beta}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-text-secondary">Correlation to Portfolio</span>
                <span className="text-text-primary font-mono">{selectedStock.corrToPort}</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
